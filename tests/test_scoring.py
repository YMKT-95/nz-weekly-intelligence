"""Scoring tests use synthetic evidence and never claim a live six-component index."""

import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.extraction import extract_evidence
from src.models import ResearchBatch
from src.research import save_research
from src.scoring import (
    WEIGHTS, build_score, calculate_index, compare_scores, save_score, score_evidence, WeeklyScore,
)


@pytest.fixture
def evidence(tmp_path, make_stats_document, make_seek_document, make_mbie_document):
    docs = [make_stats_document(), make_stats_document("stats_cpi"), make_seek_document(), make_mbie_document()]
    now = docs[0].retrieved_at
    batch = ResearchBatch(report_week="2026-W37", week_start=date(2026, 9, 7), week_end=date(2026, 9, 13),
                          started_at=now, completed_at=now, documents=docs)
    path = save_research(batch, tmp_path / "research")
    weekly = extract_evidence(path, project_root=tmp_path)

    def write(changes=None, omit=(), week="2026-W37"):
        # Change accepted-fact fixtures to isolate scoring semantics; upstream
        # source matching is tested separately by the extraction suites.
        data = weekly.model_dump(mode="json")
        data["facts"] = [fact for fact in data["facts"] if fact["metric"] not in omit]
        for fact in data["facts"]:
            fact.update((changes or {}).get(fact["metric"], {}))
        monday = date.fromisoformat(week + "-1")
        data.update(report_week=week, week_start=str(monday), week_end=str(monday + timedelta(days=6)),
                    collected_at=datetime.combine(monday + timedelta(days=5), datetime.min.time(),
                                                  ZoneInfo("Pacific/Auckland")).isoformat())
        destination = tmp_path / "evidence" / (week + ".json")
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(data))
        return destination

    return write


def parts(card):
    return {c.name: c for c in card.components}


def test_weighted_sum_and_explicit_round_half_up():
    scores = dict(job_availability=6, graduate_availability=4, competition=3.5,
                  economy=6, it_demand=7, automation_pressure=6.5)
    assert calculate_index(scores) == 5.3  # Weighted total 5.25.
    assert calculate_index(dict.fromkeys(WEIGHTS, 0)) == 0
    assert calculate_index(dict.fromkeys(WEIGHTS, 10)) == 10
    assert calculate_index(dict.fromkeys(WEIGHTS, 6.25)) == 6.3


@pytest.mark.parametrize("bad", [True, "6", -0.01, 10.01, float("nan"), float("inf")])
def test_invalid_scores_are_rejected_even_when_another_is_missing(bad):
    scores = dict.fromkeys(WEIGHTS, 6)
    scores["economy"] = bad
    scores["competition"] = None
    with pytest.raises(ValueError):
        calculate_index(scores)


def test_missing_components_never_use_zero_neutral_or_reweighted_average():
    scores = dict.fromkeys(WEIGHTS, 10)
    scores["automation_pressure"] = None
    assert calculate_index(scores) is None
    assert calculate_index(dict.fromkeys(WEIGHTS, None)) is None
    del scores["automation_pressure"]
    with pytest.raises(ValueError, match="six"):
        calculate_index(scores)


@pytest.mark.parametrize("value", [True, "25", 0, -1, 26, float("nan")])
def test_bad_weights_are_rejected(value):
    weights = {**WEIGHTS, "job_availability": value}
    with pytest.raises(ValueError):
        calculate_index(dict.fromkeys(WEIGHTS, 6), weights)


def test_supported_components_provenance_and_overall_unavailability(evidence):
    path = evidence()
    card = build_score(path)
    components = parts(card)
    assert components["job_availability"].score == 2.7  # Synthetic SEEK -2.3% m/m.
    assert components["competition"].score == 4.3  # Synthetic +1.4% m/m.
    assert components["economy"].score == 6.75  # Synthetic unemployment 5.6%.
    assert card.status == "insufficient_evidence" and card.overall_score is None
    assert card.covered_weight_percent == 60
    assert len([c for c in card.components if c.status == "unavailable"]) == 3
    assert card.interpretation == "provisional_heuristic"
    assert card.current_file.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert WeeklyScore.model_validate_json(card.model_dump_json()) == card
    for component in card.components:
        for observation in component.evidence:
            original = json.loads(path.read_text())["facts"][int(observation.pointer.split("/")[-1])]
            assert observation.fact.model_dump(mode="json") == original
    assert len(components["economy"].evidence) == 1  # No double-counting unemployment or CPI.


@pytest.mark.parametrize("metric,value,component,score", [
    ("unemployment_rate", 3, "economy", 10), ("unemployment_rate", 7, "economy", 5),
    ("unemployment_rate", 11, "economy", 0), ("unemployment_rate", 12, "economy", 0),
    ("seek_job_ads_change", -5, "job_availability", 0), ("seek_job_ads_change", 5, "job_availability", 10),
    ("seek_job_ads_change", 15, "job_availability", 10), ("seek_job_ads_change", 0, "job_availability", 5),
    ("seek_applications_per_ad_change", -10, "competition", 10),
    ("seek_applications_per_ad_change", 10, "competition", 0),
    ("seek_applications_per_ad_change", 0, "competition", 5),
])
def test_documented_mapping_anchors_and_clipping(evidence, metric, value, component, score):
    card = build_score(evidence({metric: {"value": value}}))
    assert parts(card)[component].score == score


def test_mbie_fallback_has_its_own_annual_mapping(evidence):
    card = build_score(evidence({"mbie_job_ads_annual_change": {"value": 8}}, omit=["seek_job_ads_change"]))
    job = parts(card)["job_availability"]
    assert job.score == 7 and job.rule["id"] == "mbie_annual_growth_v1"
    assert "no accepted evidence" in job.issues[0]


@pytest.mark.parametrize("change", [
    {"unit": "percentage_points"}, {"comparison_basis": "year_on_year"}, {"adjustment": "trend"},
    {"source": "Another publisher"}, {"category": "NZ Economy"}, {"value": -101},
    {"period_start": "2026-05-01"},
])
def test_incompatible_evidence_is_not_scored(evidence, change):
    card = build_score(evidence({"seek_applications_per_ad_change": change}))
    assert parts(card)["competition"].score is None
    assert parts(card)["competition"].issues


def test_data_age_uses_period_end_not_retrieval_or_update_date(evidence):
    path = evidence(week="2026-W45")
    card = build_score(path)
    assert parts(card)["competition"].score is None
    assert "days past period end" in parts(card)["competition"].issues[0]
    assert parts(card)["economy"].score is not None  # Longer quarterly age allowance.


def test_age_limit_is_inclusive(evidence):
    # June applications have a 100-day limit: October 8 qualifies, October 9 does not.
    path = evidence(week="2026-W41")
    data = json.loads(path.read_text())
    data["collected_at"] = "2026-10-08T12:00:00+12:00"
    path.write_text(json.dumps(data))
    assert parts(build_score(path))["competition"].score == 4.3
    data["collected_at"] = "2026-10-09T12:00:00+12:00"
    path.write_text(json.dumps(data))
    assert parts(build_score(path))["competition"].score is None


def test_latest_conflict_never_selects_an_older_convenient_value(evidence):
    path = evidence()
    data = json.loads(path.read_text())
    observation = next(f for f in data["facts"] if f["metric"] == "unemployment_rate")
    data["facts"].append({**observation, "value": 5.7})
    data["facts"].append({**observation, "value": 4, "period_start": "2026-01-01", "period_end": "2026-03-31"})
    path.write_text(json.dumps(data))
    component = parts(build_score(path))["economy"]
    assert component.score is None and "conflicting latest" in component.issues[0]


def complete_fixture(card, value=6):
    """Artificial six-component card for calculator/history plumbing, not live scoring."""
    data = card.model_dump()
    template = parts(card)["economy"]
    for component in data["components"]:
        component.update(status="scored", score=value, rule={"id": "synthetic_" + component["name"]},
                         evidence=[o.model_dump() for o in template.evidence], data_age_days=template.data_age_days,
                         reason="Synthetic complete-card fixture; not a supported live evidence mapping.")
    data.update(status="complete", overall_score=calculate_index(dict.fromkeys(WEIGHTS, value)), covered_weight_percent=100)
    return WeeklyScore.model_validate(data)


@pytest.mark.parametrize("field,value", [("overall_score", 8), ("covered_weight_percent", 100), ("status", "complete")])
def test_inconsistent_saved_aggregates_are_rejected(evidence, field, value):
    data = build_score(evidence()).model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        WeeklyScore.model_validate(data)


def test_index_comparison_requires_complete_compatible_indices(evidence):
    partial = build_score(evidence())
    complete = complete_fixture(partial)
    assert compare_scores(partial, None).status == "unavailable"
    assert compare_scores(complete, partial).status == "unavailable"
    assert compare_scores(complete, None).status == "no_history"
    assert compare_scores(complete, complete).status == "unchanged_evidence"
    assert compare_scores(complete, complete).delta == 0
    changed = complete.model_copy(update={"policy_sha256": "0" * 64})
    assert compare_scores(changed, complete).status == "incompatible_rules"
    changed = complete.model_copy(update={"rule_version": "different"})
    assert compare_scores(changed, complete).delta is None


def test_method_switches_and_same_period_revisions_are_not_trends(evidence):
    complete = complete_fixture(build_score(evidence()))
    changed = complete.model_copy(deep=True)
    changed.components[0].rule = {"id": "alternative_source"}
    assert compare_scores(changed, complete).status == "incompatible_rules"
    changed = complete.model_copy(deep=True)
    changed.components[0].evidence[0].fact.value = 5.9
    assert compare_scores(changed, complete).status == "revised_evidence"
    assert compare_scores(changed, complete).delta is None


def test_complete_indices_with_later_periods_have_a_delta(evidence):
    current = complete_fixture(build_score(evidence()), value=6.5)
    previous = complete_fixture(build_score(evidence()), value=6)
    for component in previous.components:
        component.evidence[0].fact.period_start = date(2026, 1, 1)
        component.evidence[0].fact.period_end = date(2026, 3, 31)
    assert compare_scores(current, previous).status == "comparable"
    assert compare_scores(current, previous).delta == 0.5
    assert compare_scores(previous, current).status == "incompatible_inputs"


def test_partial_history_is_not_skipped_to_find_an_older_complete_score(evidence, tmp_path):
    directory = tmp_path / "scores"
    old = build_score(evidence(week="2026-W37"))
    save_score(complete_fixture(old), directory, "older.json")
    latest = build_score(evidence(week="2026-W38"))
    save_score(latest, directory, "latest.json")
    result = score_evidence(evidence(week="2026-W40"), directory)
    assert result.comparison.status == "unavailable" and result.comparison.delta is None
    assert result.comparison.previous_file.report_week == "2026-W38"
    assert result.comparison.weeks_apart == 2


def test_invalid_history_fallback_current_and_future_weeks_ignored(evidence, tmp_path):
    directory = tmp_path / "scores"
    old = build_score(evidence())
    save_score(old, directory, "first.json")
    (directory / "2026-W38.json").write_text("invalid")
    (directory / "2026-W40.json").write_text("ignored current")
    (directory / "2026-W41.json").write_text("ignored future")
    result = score_evidence(evidence(week="2026-W40"), directory)
    assert result.comparison.previous_file.report_week == "2026-W37"
    assert len(result.history_notes) == 1 and "2026-W38" in result.history_notes[0]


def test_incomplete_new_result_replaces_old_index_and_archives_are_preserved(evidence, tmp_path):
    partial = build_score(evidence())
    directory = tmp_path / "scores"
    old_archive, view = save_score(complete_fixture(partial), directory, "old.json")
    original = old_archive.read_bytes()
    archive, view = save_score(partial, directory, "new.json")
    assert WeeklyScore.model_validate_json(view.read_text()).overall_score is None
    assert old_archive.read_bytes() == original
    assert archive.read_bytes() == view.read_bytes()
    with pytest.raises(FileExistsError):
        save_score(partial, directory, "new.json")


def test_failed_atomic_write_preserves_old_score(evidence, tmp_path, monkeypatch):
    import src.scoring as scoring
    score = build_score(evidence())
    directory = tmp_path / "scores"
    _, view = save_score(score, directory, "first.json")
    original = view.read_bytes()

    def fail(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(scoring.os, "replace", fail)
    with pytest.raises(OSError, match="Synthetic disk failure"):
        save_score(score, directory, "second.json")
    assert view.read_bytes() == original and not list(directory.glob(".score-*.tmp"))
