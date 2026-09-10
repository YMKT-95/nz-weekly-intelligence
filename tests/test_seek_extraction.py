"""Source-text validation with synthetic national, regional, and industry claims."""

import hashlib
from datetime import date

import pytest
from pydantic import HttpUrl

from src.extraction import extract_evidence, validate_fact
from src.models import ResearchBatch, TextEvidenceReference, TextSpan, WeeklyData
from src.research import save_research


def extract(tmp_path, *documents):
    now = documents[0].retrieved_at
    batch = ResearchBatch(report_week="2026-W37", week_start=date(2026, 9, 7), week_end=date(2026, 9, 13),
                          started_at=now, completed_at=now, documents=list(documents))
    path = save_research(batch, tmp_path / "research")
    return extract_evidence(path, project_root=tmp_path)


def rewrite(make_seek_document, old, new):
    return make_seek_document(make_seek_document().text.replace(old, new))


def test_national_facts_have_exact_text_context_and_correct_lag(tmp_path, make_seek_document):
    doc = make_seek_document(published="2026-08-12T09:00:00+12:00")
    result = extract(tmp_path, doc)
    assert not result.rejected and not result.skipped
    assert result.schema_version == 3
    assert WeeklyData.model_validate_json(result.model_dump_json()) == result
    jobs, applications = result.facts
    assert (jobs.metric, jobs.value, jobs.period, jobs.adjustment) == (
        "seek_job_ads_change", -2.3, "July 2026", "trend")
    assert (applications.metric, applications.value, applications.period, applications.adjustment) == (
        "seek_applications_per_ad_change", 1.4, "June 2026", "not_stated")
    assert (applications.period_start, applications.period_end) == (date(2026, 6, 1), date(2026, 6, 30))
    for fact in result.facts:
        assert fact.comparison_basis == "month_on_month"
        assert fact.unit == "percent" and fact.scope == "all" and fact.geography == "New Zealand"
        assert fact.publication_date == date(2026, 8, 12)
        assert fact.source_updated_date is None
        assert isinstance(fact.evidence, TextEvidenceReference)
        assert len([span for span in fact.evidence.spans if span.role == "statement"]) == 2
        for span in fact.evidence.spans:
            assert doc.text[span.start:span.end] == span.quote
        assert fact.evidence.snapshot_sha256 == hashlib.sha256(
            (tmp_path / fact.evidence.snapshot_file).read_bytes()).hexdigest()
        assert validate_fact(fact.model_dump(), doc, fact.evidence.snapshot_file,
                             fact.evidence.snapshot_sha256) == fact
    assert "lag" in {span.role for span in applications.evidence.spans}


@pytest.mark.parametrize("old,new,reason,remaining", [
    ("Job ads fell 2.3% in July", "Job ads fell 2.3% in June", "data period disagrees", "seek_applications_per_ad_change"),
    ("June data.", "May data.", "one-month lag", "seek_job_ads_change"),
    ("one-month lag", "two-month lag", "reporting-lag note", "seek_job_ads_change"),
    ("rising 1.4% in June", "rising 1.4% in July", "data period disagrees", "seek_job_ads_change"),
    ("Job ads fell 2.3%", "Job ads are expected to fall 2.3%", "wording", "seek_applications_per_ad_change"),
    ("Job ads fell 2.3%", "Job ads fell 2.3 percentage points", "wording", "seek_applications_per_ad_change"),
    ("Job ads fell 2.3%", "Job ads fell 2.3% and rose 1.1%", "Multiple values", "seek_applications_per_ad_change"),
    ("Job ads fell 2.3% in July", "Job ads fell 2.3% compared to last year", "wording", "seek_applications_per_ad_change"),
    ("down 2.3%", "up 2.3%", "directions", "seek_applications_per_ad_change"),
    ("2.3%", "101%", "100 percent", "seek_applications_per_ad_change"),
])
def test_ambiguous_metric_is_withheld_without_losing_other_metric(
        tmp_path, make_seek_document, old, new, reason, remaining):
    doc = rewrite(make_seek_document, old, new)
    result = extract(tmp_path, doc)
    assert [f.metric for f in result.facts] == [remaining]
    assert reason in result.rejected[0].reason
    assert result.rejected[0].text_spans


@pytest.mark.parametrize("old,new,reason", [
    ("July 2025 to July 2026", "July to July", "explicit report year"),
    ("July 2025 to July 2026", "June 2025 to June 2026", "disagree"),
    ("July 2025 to July 2026", "July 2024 to July 2026", "disagree"),
])
def test_report_year_must_be_explicit_and_consistent(tmp_path, make_seek_document, old, new, reason):
    result = extract(tmp_path, rewrite(make_seek_document, old, new))
    assert not result.facts
    assert reason in result.rejected[0].reason


def test_january_applications_belong_to_previous_december(tmp_path, make_seek_document):
    text = make_seek_document().text.replace("July", "January").replace("June", "December")
    result = extract(tmp_path, make_seek_document(text))
    assert not result.rejected
    applications = next(f for f in result.facts if "applications" in f.metric)
    assert applications.period == "December 2025"
    assert applications.period_end == date(2025, 12, 31)


def test_monthly_and_annual_changes_are_separate(tmp_path, make_seek_document):
    doc = rewrite(make_seek_document, "Job ads fell 2.3% in July, marking three months of decline.",
                  "Job ads rose 4.5% year-on-year in July.")
    result = extract(tmp_path, doc)
    assert not result.rejected
    jobs = [f for f in result.facts if f.metric == "seek_job_ads_change"]
    assert {(f.value, f.comparison_basis) for f in jobs} == {(-2.3, "month_on_month"), (4.5, "year_on_year")}


def test_conflicting_values_reject_the_series(tmp_path, make_seek_document):
    doc = rewrite(make_seek_document, "Job ads fell 2.3%", "Job ads fell 3.4%")
    result = extract(tmp_path, doc)
    assert [f.metric for f in result.facts] == ["seek_applications_per_ad_change"]
    assert len(result.rejected) == 2
    assert all("Conflicting values" in issue.reason and issue.text_spans for issue in result.rejected)


@pytest.mark.parametrize("field,value", [
    ("value", 8.8), ("period", "July 2026"), ("comparison_basis", "year_on_year"),
    ("publication_date", "2026-08-12"), ("adjustment", "trend"),
    ("metric", "graduate_hiring_change"), ("source", "MBIE"),
])
def test_candidate_metadata_cannot_be_changed(tmp_path, make_seek_document, field, value):
    doc = make_seek_document()
    fact = extract(tmp_path, doc).facts[1]
    candidate = fact.model_dump()
    candidate[field] = value
    with pytest.raises(ValueError, match="does not match"):
        validate_fact(candidate, doc, fact.evidence.snapshot_file, fact.evidence.snapshot_sha256)


@pytest.mark.parametrize("change", ["offset", "quote", "hash", "snapshot", "remove_context"])
def test_text_evidence_tampering_is_rejected(tmp_path, make_seek_document, change):
    doc = make_seek_document()
    fact = extract(tmp_path, doc).facts[0]
    candidate = fact.model_dump()
    evidence = candidate["evidence"]
    if change == "offset":
        evidence["spans"][0]["start"] += 1
        evidence["spans"][0]["end"] += 1
    elif change == "quote":
        evidence["spans"][0]["quote"] = "x" * len(evidence["spans"][0]["quote"])
    elif change == "hash":
        evidence["document_sha256"] = "a" * 64
    elif change == "snapshot":
        evidence["snapshot_file"] = "another.json"
    else:
        evidence["spans"].pop()
    with pytest.raises(ValueError, match="does not match"):
        validate_fact(candidate, doc, fact.evidence.snapshot_file, fact.evidence.snapshot_sha256)


@pytest.mark.parametrize("changes,reason", [
    ({"text": "Tampered source text"}, "checksum"),
    ({"source_url": HttpUrl("https://example.com/about/news/article/seek-nz-employment-report-july26")}, "official SEEK"),
    ({"requested_url": HttpUrl("https://nz.seek.com/about/news/article/seek-nz-employment-report-july26?other=1")}, "official SEEK"),
    ({"source": "Another publisher"}, "identity"),
    ({"published_at_raw": "2027-08-12"}, "future"),
    ({"published_at_raw": "yesterday"}, "date metadata"),
])
def test_source_and_date_validation(tmp_path, make_seek_document, changes, reason):
    result = extract(tmp_path, make_seek_document().model_copy(update=changes))
    assert not result.facts
    assert reason in result.rejected[0].reason


def test_missing_national_scope_never_uses_industry_or_region_numbers(tmp_path, make_seek_document):
    doc = rewrite(make_seek_document, "National Insights", "Graduate Insights")
    result = extract(tmp_path, doc)
    assert not result.facts
    assert len(result.rejected) == 2
    assert all("No supported national statement" in issue.reason for issue in result.rejected)


def test_mixed_sources_and_old_evidence_remain_readable(tmp_path, make_seek_document, make_stats_document):
    result = extract(tmp_path, make_stats_document(), make_stats_document("stats_cpi"), make_seek_document())
    assert len(result.facts) == 6
    assert not result.rejected
    assert WeeklyData.model_validate_json(result.model_dump_json()) == result
    legacy = result.model_dump()
    legacy["schema_version"] = 2
    legacy["facts"] = legacy["facts"][:4]
    for fact in legacy["facts"]:
        fact.pop("scope")
        fact.pop("adjustment")
    assert len(WeeklyData.model_validate(legacy).facts) == 4


def test_text_span_offsets_are_strict_and_match_quote_length():
    with pytest.raises(ValueError):
        TextSpan(role="statement", start=True, end=4, quote="abc")
    with pytest.raises(ValueError, match="length"):
        TextSpan(role="statement", start=0, end=4, quote="abc")


def test_monthly_basis_cannot_be_inferred_from_month_alone(tmp_path, make_seek_document):
    text = make_seek_document().text.replace("Report - July", "Report - July 2026")
    text = text.replace("Figure 3: National SEEK job ad percentage change m/m (July 2025 to July 2026)", "")
    result = extract(tmp_path, make_seek_document(text))
    assert not result.facts
    assert all("comparison context" in issue.reason for issue in result.rejected)


def test_unicode_offsets_and_missing_publication_date(tmp_path, make_seek_document):
    doc = make_seek_document("Synthetic introduction: Māori text — 😀\n" + make_seek_document().text)
    result = extract(tmp_path, doc)
    assert len(result.facts) == 2
    for fact in result.facts:
        assert fact.publication_date is None
        for span in fact.evidence.spans:
            assert doc.text[span.start:span.end] == span.quote
