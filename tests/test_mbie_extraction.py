"""Validate MBIE's annual change without confusing indices, counts, or quarters."""

from datetime import date

import pytest
from pydantic import HttpUrl

from src.extraction import extract_evidence, validate_fact
from src.models import ResearchBatch, WeeklyData
from src.research import save_research


def extract(tmp_path, *documents):
    now = documents[0].retrieved_at
    batch = ResearchBatch(report_week="2026-W37", week_start=date(2026, 9, 7), week_end=date(2026, 9, 13),
                          started_at=now, completed_at=now, documents=list(documents))
    return extract_evidence(save_research(batch, tmp_path / "research"), project_root=tmp_path)


def test_annual_change_keeps_quarter_scope_adjustment_and_update_date(tmp_path, make_mbie_document):
    document = make_mbie_document()
    result = extract(tmp_path, document)
    fact, = result.facts
    assert not result.rejected and not result.skipped
    assert (fact.metric, fact.value, fact.unit, fact.comparison_basis) == (
        "mbie_job_ads_annual_change", 8.2, "percent", "year_on_year")
    assert (fact.period_start, fact.period_end) == (date(2026, 4, 1), date(2026, 6, 30))
    assert fact.adjustment == "unadjusted" and fact.scope == "all"
    assert fact.publication_date is None
    assert fact.source_updated_date == date(2026, 8, 14)
    assert WeeklyData.model_validate_json(result.model_dump_json()) == result
    for span in fact.evidence.spans:
        assert document.text[span.start:span.end] == span.quote
    assert validate_fact(fact.model_dump(), document, fact.evidence.snapshot_file,
                         fact.evidence.snapshot_sha256) == fact


@pytest.mark.parametrize("old,new,reason", [
    ("grew by 8.2 per cent", "grew by 8.2", "units or meaning"),
    ("grew by 8.2 per cent", "grew by 8.2 percentage points", "units or meaning"),
    ("grew by 8.2 per cent", "grew to 108.2 index points", "units or meaning"),
    ("grew by 8.2 per cent", "are expected to grow by 8.2 per cent", "units or meaning"),
    ("grew by 8.2 per cent", "fell by 101 per cent", "100 percent"),
    ("grew by 8.2 per cent", "grew by NaN per cent", "units or meaning"),
    ("in the year to the June", "in the quarter to the June", "units or meaning"),
    ("in the year to the June", "in the year to the March", "periods disagree"),
    ("Year ended June 2026", "Year ended June", "overview heading"),
    ("June 2026", "May 2026", "overview heading"),
    ("June 2026", "December 2026", "future"),
    ("All the quarterly data series are no longer being seasonally adjusted.", "Adjustment unspecified.", "adjustment context"),
    ("Jobs Online monitors changes in an index", "Jobs Online monitors counts", "index/quarterly"),
    ("14 August 2026", "tomorrow", "Unrecognised MBIE date"),
    ("14 August 2026", "14 August 2027", "future"),
])
def test_invalid_or_ambiguous_observation_is_rejected(
        tmp_path, make_mbie_html, make_mbie_document, old, new, reason):
    result = extract(tmp_path, make_mbie_document(make_mbie_html().replace(old, new)))
    assert not result.facts
    assert reason in result.rejected[0].reason


@pytest.mark.parametrize("direction,expected", [("fell", -8.2), ("decreased", -8.2), ("increased", 8.2)])
def test_sign_is_derived_from_observed_direction(tmp_path, make_mbie_html, make_mbie_document, direction, expected):
    result = extract(tmp_path, make_mbie_document(make_mbie_html().replace("grew by", direction + " by")))
    assert result.facts[0].value == expected


def test_zero_is_valid_and_missing_dates_stay_unknown(tmp_path, make_mbie_html, make_mbie_document):
    html = make_mbie_html().replace("8.2", "0").replace("<p>Last updated: 14 August 2026</p>", "")
    fact, = extract(tmp_path, make_mbie_document(html)).facts
    assert fact.value == 0
    assert fact.publication_date is fact.source_updated_date is None


def test_conflicting_national_statements_and_update_metadata(tmp_path, make_mbie_html, make_mbie_document):
    html = make_mbie_html().replace("</main>", "<p>Online job advertisements fell by 2 per cent in the year to the June 2026 quarter.</p></main>")
    doc = make_mbie_document(html)
    result = extract(tmp_path, doc)
    assert not result.facts and "Conflicting national statements" in result.rejected[0].reason


def test_page_update_is_not_report_publication_date(tmp_path, make_mbie_document):
    doc = make_mbie_document().model_copy(update={"published_at_raw": "2026-07-31", "updated_at_raw": "2026-08-14"})
    fact, = extract(tmp_path, doc).facts
    assert fact.publication_date == date(2026, 7, 31)
    assert fact.source_updated_date == date(2026, 8, 14)


def test_conflicting_update_dates_rejected(tmp_path, make_mbie_document):
    doc = make_mbie_document().model_copy(update={"updated_at_raw": "2026-08-15"})
    result = extract(tmp_path, doc)
    assert not result.facts and "Conflicting page update dates" in result.rejected[0].reason


@pytest.mark.parametrize("changes,reason", [
    ({"text": "Tampered source"}, "checksum"),
    ({"source_url": HttpUrl("https://example.com/")}, "official MBIE"),
    ({"source": "SEEK NZ"}, "identity"),
    ({"collection_method": "embedded_page_json"}, "collection method"),
])
def test_source_identity_and_integrity(tmp_path, make_mbie_document, changes, reason):
    result = extract(tmp_path, make_mbie_document().model_copy(update=changes))
    assert not result.facts and reason in result.rejected[0].reason


@pytest.mark.parametrize("field,value", [
    ("value", 9.1), ("unit", "people"), ("comparison_basis", "quarter_on_quarter"),
    ("adjustment", "trend"), ("period_start", date(2025, 7, 1)), ("publication_date", date(2026, 8, 14)),
])
def test_candidate_metadata_must_match_source(tmp_path, make_mbie_document, field, value):
    doc = make_mbie_document()
    fact, = extract(tmp_path, doc).facts
    candidate = fact.model_dump()
    candidate[field] = value
    with pytest.raises(ValueError, match="does not match"):
        validate_fact(candidate, doc, fact.evidence.snapshot_file, fact.evidence.snapshot_sha256)


def test_mbie_failure_does_not_discard_stats_facts(tmp_path, make_mbie_document, make_stats_document):
    mbie = make_mbie_document().model_copy(update={"text": "Tampered"})
    result = extract(tmp_path, mbie, make_stats_document())
    assert len(result.facts) == 3 and len(result.rejected) == 1


def test_quote_and_offset_tampering_cannot_validate(tmp_path, make_mbie_document):
    doc = make_mbie_document()
    fact, = extract(tmp_path, doc).facts
    candidate = fact.model_dump()
    candidate["evidence"]["spans"][0]["start"] += 1
    candidate["evidence"]["spans"][0]["end"] += 1
    with pytest.raises(ValueError, match="does not match"):
        validate_fact(candidate, doc, fact.evidence.snapshot_file, fact.evidence.snapshot_sha256)
