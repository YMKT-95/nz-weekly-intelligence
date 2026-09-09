"""Verify meaning, source matching, auditability, and persistence with synthetic data."""

import hashlib
import json
from datetime import date, timedelta

import pytest
from pydantic import HttpUrl

from src.extraction import extract_evidence, save_evidence, validate_fact
from src.models import ResearchBatch, WeeklyData, WeeklyFact
from src.research import save_research


def snapshot(tmp_path, documents):
    now = documents[0].retrieved_at
    batch = ResearchBatch(report_week="2026-W37", week_start=date(2026, 9, 7), week_end=date(2026, 9, 13),
                          started_at=now, completed_at=now, documents=documents)
    return save_research(batch, tmp_path / "data" / "research")


def extract(tmp_path, *documents):
    return extract_evidence(snapshot(tmp_path, list(documents)), project_root=tmp_path)


def test_four_observations_keep_units_periods_and_provenance(tmp_path, make_stats_document):
    unemployment = make_stats_document()
    cpi = make_stats_document("stats_cpi")
    path = snapshot(tmp_path, [unemployment, cpi])
    result = extract_evidence(path, project_root=tmp_path)
    assert len(result.facts) == 4
    assert not result.rejected
    facts = {fact.metric: fact for fact in result.facts}
    rate = facts["unemployment_rate"]
    change = facts["unemployment_rate_change"]
    count = facts["unemployed_people"]
    inflation = facts["cpi_annual_change"]
    assert (rate.value, rate.unit, rate.comparison_basis) == (5.6, "percent", "level")
    assert (change.value, change.unit, change.comparison_basis) == (0.2, "percentage_points", "quarter_on_quarter")
    assert (count.value, count.unit) == (171000, "people")
    assert (inflation.value, inflation.comparison_basis) == (4.1, "year_on_year")
    assert rate.period == "June 2026 quarter"
    assert (rate.period_start, rate.period_end) == (date(2026, 4, 1), date(2026, 6, 30))
    assert inflation.period == "June 2026 year"
    assert (inflation.period_start, inflation.period_end) == (date(2025, 7, 1), date(2026, 6, 30))
    assert rate.publication_date is None
    assert rate.source_updated_date == date(2026, 8, 5)
    assert rate.evidence.raw_fields["Value"] == "5.6%"
    assert change.evidence.json_pointer == "/PageBlocks/0/Value2"
    for fact in result.facts:
        assert (tmp_path / fact.evidence.snapshot_file).is_file()
        assert fact.evidence.snapshot_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert fact.period_end < fact.retrieved_at.date()


def test_collector_preserves_original_field_positions_and_values(make_stats_document):
    doc = make_stats_document(extra_blocks=[{"ClassName": "IndicatorBlock", "Name": "Extra",
                                          "Value": "1%", "Period": "June 2026 quarter"}])
    blocks = doc.structured_data["PageBlocks"]
    assert blocks[0]["Value2"] == "+0.2pp"
    assert blocks[1] is None
    assert blocks[2]["Name"] == "Extra"
    assert doc.structured_sha256 is not None


@pytest.mark.parametrize("changes, reason", [
    ({"Value": None}, "Value must"),
    ({"Value": ""}, "units cannot"),
    ({"Value": "NaN%"}, "units cannot"),
    ({"Value": "inf%"}, "units cannot"),
    ({"Value": True}, "original source string"),
    ({"Value": "5.6"}, "units cannot"),
    ({"Value": "5.6pp"}, "units cannot"),
    ({"Value": "-1%"}, "between 0 and 100"),
    ({"Value": "101%"}, "between 0 and 100"),
    ({"Period": None}, "Missing data period"),
    ({"Period": "June 2026 year"}, "followed by 'quarter'"),
    ({"Period": "May 2026 quarter"}, "Quarter period must end"),
    ({"Period": "December 2026 quarter"}, "future"),
    ({"Description": "Annual change"}, "description"),
    ({"Description": None}, "description"),
    ({"LastUpdatedDate": "not a date"}, "Unrecognised source date"),
    ({"LastUpdatedDate": "5 August 2027"}, "future"),
])
def test_bad_candidate_is_rejected_without_discarding_other_valid_slots(tmp_path, make_stats_document, changes, reason):
    result = extract(tmp_path, make_stats_document(changes=changes))
    assert "unemployment_rate" not in {fact.metric for fact in result.facts}
    assert any(reason in issue.reason for issue in result.rejected)
    if "LastUpdatedDate" not in changes:
        assert len(result.facts) == 2


@pytest.mark.parametrize("raw", ["-1", "17,10", "171000.5", "171000 people"])
def test_invalid_people_counts_are_rejected(tmp_path, make_stats_document, raw):
    result = extract(tmp_path, make_stats_document(changes={"Value3": raw}))
    assert "unemployed_people" not in {fact.metric for fact in result.facts}
    assert len(result.rejected) == 1


def test_negative_inflation_and_zero_are_valid(tmp_path, make_stats_document):
    result = extract(tmp_path, make_stats_document(changes={"Value": "0%", "Value2": "\u22120.2pp", "Value3": "0"}),
                     make_stats_document("stats_cpi", changes={"Value": "-0.5%"}))
    assert [fact.value for fact in result.facts] == [0.0, -0.2, 0, -0.5]


def test_publication_and_update_dates_remain_distinct(tmp_path, make_stats_document):
    result = extract(tmp_path, make_stats_document(published="2026-08-04T10:45:00+12:00"))
    assert result.facts[0].publication_date == date(2026, 8, 4)
    assert result.facts[0].source_updated_date == date(2026, 8, 5)
    assert result.facts[0].retrieved_at.date() == date(2026, 9, 10)


def test_unknown_dates_are_left_empty(tmp_path, make_stats_document):
    result = extract(tmp_path, make_stats_document(changes={"LastUpdatedDate": None}))
    assert len(result.facts) == 3
    assert all(fact.publication_date is None and fact.source_updated_date is None for fact in result.facts)


def test_meaning_comes_from_description_not_slot_number(tmp_path, make_stats_document):
    result = extract(tmp_path, make_stats_document(changes={
        "Description": "Number of unemployed people", "Value": "171,000",
        "Description3": "Quarterly", "Value3": "5.6%"}))
    rate = next(fact for fact in result.facts if fact.metric == "unemployment_rate")
    assert rate.value == 5.6
    assert rate.evidence.json_pointer.endswith("/Value3")


@pytest.mark.parametrize("change", [
    {"value": 8.8}, {"period": "March 2026 quarter"}, {"unit": "people"},
    {"comparison_basis": "year_on_year"}, {"metric": "graduate_opportunities"},
    {"source_url": "https://example.com/fabricated"}, {"source": "Other source"},
    {"source_updated_date": "2026-08-06"}, {"publication_date": "2026-08-05"},
])
def test_schema_valid_but_source_mismatched_candidate_is_rejected(tmp_path, make_stats_document, change):
    document = make_stats_document()
    path = snapshot(tmp_path, [document])
    fact = extract_evidence(path, project_root=tmp_path).facts[0]
    candidate = fact.model_dump(mode="json") | change
    with pytest.raises(ValueError, match="does not match"):
        validate_fact(candidate, document, fact.evidence.snapshot_file, fact.evidence.snapshot_sha256)


@pytest.mark.parametrize("field", ["source", "value", "period", "unit", "retrieved_at", "evidence"])
def test_required_fact_fields_are_enforced(tmp_path, make_stats_document, field):
    fact = extract(tmp_path, make_stats_document()).facts[0].model_dump()
    del fact[field]
    with pytest.raises(ValueError):
        WeeklyFact.model_validate(fact)


@pytest.mark.parametrize("value", [True, "5.6", float("nan"), float("inf")])
def test_strict_numeric_schema(tmp_path, make_stats_document, value):
    fact = extract(tmp_path, make_stats_document()).facts[0].model_dump()
    fact["value"] = value
    with pytest.raises(ValueError):
        WeeklyFact.model_validate(fact)


def test_tampered_document_is_not_used(tmp_path, make_stats_document):
    document = make_stats_document()
    document.structured_data["PageBlocks"][0]["Value"] = "9.9%"
    result = extract(tmp_path, document)
    assert not result.facts
    assert "checksum" in result.rejected[0].reason


def test_old_phase2_snapshot_requires_recollection(tmp_path, make_stats_document):
    document = make_stats_document().model_copy(update={"structured_data": None, "structured_sha256": None})
    path = snapshot(tmp_path, [document])
    data = json.loads(path.read_text())
    data["schema_version"] = 1
    for doc in data["documents"]:
        doc.pop("structured_data")
        doc.pop("structured_sha256")
    path.write_text(json.dumps(data))
    result = extract_evidence(path, project_root=tmp_path)
    assert not result.facts
    assert "run collection again" in result.rejected[0].reason


def test_conflicting_values_are_rejected_and_identical_values_deduplicated(tmp_path, make_stats_document):
    first = make_stats_document()
    second = make_stats_document(changes={"Value": "5.7%"})
    result = extract(tmp_path, first, second)
    assert len(result.facts) == 2  # Identical change and people-count observations.
    assert len(result.rejected) == 2
    assert all("Conflicting" in issue.reason for issue in result.rejected)


def test_wrong_source_url_and_changed_indicator_name_are_rejected(tmp_path, make_stats_document):
    wrong_url = make_stats_document().model_copy(update={"source_url": HttpUrl("https://example.com/")})
    wrong_name = make_stats_document("stats_cpi", changes={"Name": "A different price index"})
    result = extract(tmp_path, wrong_url, wrong_name)
    assert not result.facts
    assert len(result.rejected) == 2


def test_failed_extraction_preserves_previous_weekly_file(tmp_path, make_stats_document):
    good = extract(tmp_path, make_stats_document())
    archive, canonical = save_evidence(good, tmp_path / "data" / "weekly")
    assert WeeklyData.model_validate_json(canonical.read_text()) == good
    assert archive.read_bytes() == canonical.read_bytes()
    original = canonical.read_bytes()
    failed = good.model_copy(update={"facts": [], "collected_at": good.collected_at + timedelta(minutes=1)})
    later_archive, replacement = save_evidence(failed, tmp_path / "data" / "weekly")
    assert replacement is None
    assert later_archive.exists()
    assert canonical.read_bytes() == original


def test_atomic_write_failure_preserves_previous_weekly_file(tmp_path, make_stats_document, monkeypatch):
    import src.extraction as extraction
    good = extract(tmp_path, make_stats_document())
    _, canonical = save_evidence(good, tmp_path / "data" / "weekly")
    original = canonical.read_bytes()
    later = good.model_copy(update={"collected_at": good.collected_at + timedelta(minutes=1)})

    def fail_replace(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(extraction.os, "replace", fail_replace)
    with pytest.raises(OSError, match="Synthetic disk failure"):
        save_evidence(later, tmp_path / "data" / "weekly")
    assert canonical.read_bytes() == original
    assert not list(canonical.parent.glob(".evidence-*.tmp"))
