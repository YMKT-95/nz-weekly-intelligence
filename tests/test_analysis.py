"""Offline comparisons of synthetic evidence, with explicit temporal semantics."""

import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.analysis import compare_evidence, save_comparison, WeeklyComparison
from src.models import WeeklyData, WeeklyFact
from src.extraction import extract_evidence
from src.models import ResearchBatch
from src.research import save_research


@pytest.fixture
def factory(tmp_path, make_stats_document, make_seek_document):
    docs = [make_stats_document(), make_stats_document("stats_cpi"), make_seek_document()]
    now = docs[0].retrieved_at
    batch = ResearchBatch(report_week="2026-W37", week_start=date(2026, 9, 7), week_end=date(2026, 9, 13),
                          started_at=now, completed_at=now, documents=docs)
    path = save_research(batch, tmp_path / "research")
    templates = {f.metric: f for f in extract_evidence(path, project_root=tmp_path).facts}

    def fact(metric="unemployment_rate", value=5.6, start="2026-04-01", end="2026-06-30", **changes):
        # These are synthetic accepted-evidence fixtures, not real historical releases.
        fields = templates[metric].model_dump()
        fields.update(value=value, period_start=date.fromisoformat(start), period_end=date.fromisoformat(end),
                      retrieved_at=datetime(2026, 9, 1, tzinfo=ZoneInfo("Pacific/Auckland")))
        fields.update(changes)
        return WeeklyFact.model_validate(fields)

    def write(week, facts, name=None):
        start = date.fromisoformat(week + "-1")
        collected = datetime.combine(start + timedelta(days=5), datetime.min.time(), ZoneInfo("Pacific/Auckland"))
        # Give each synthetic run internally consistent evidence timestamps.
        facts = [f.model_copy(update={"retrieved_at": min(f.retrieved_at, collected)}) for f in facts]
        weekly = WeeklyData(report_week=week, week_start=start, week_end=start + timedelta(days=6),
                            collected_at=collected, research_snapshot="synthetic.json", research_status="partial", facts=facts)
        destination = tmp_path / (name or week + ".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(weekly.model_dump_json(indent=2))
        return destination

    return fact, write


def compare(tmp_path, factory, now, old=None):
    _, write = factory
    if old is not None:
        write("2026-W36", old)
    path = write("2026-W37", now)
    return compare_evidence(path, tmp_path)


def test_first_run_has_no_invented_change(factory, tmp_path):
    fact, _ = factory
    result = compare(tmp_path, factory, [fact()])
    assert result.previous_file is None and result.weeks_apart is None
    assert result.items[0].status == "baseline"
    assert result.items[0].delta is result.items[0].review_worthy is None
    assert result.labour_direction == "insufficient_data"


@pytest.mark.parametrize("old,new,delta,movement,flag", [
    (5.4, 5.6, 0.2, "increased", True),
    (5.6, 5.4, -0.2, "decreased", True),
    (5.5, 5.6, 0.1, "increased", False),
    (5.6, 5.6, 0, "unchanged", False),
])
def test_new_period_changes_use_percentage_points(factory, tmp_path, old, new, delta, movement, flag):
    fact, _ = factory
    result = compare(tmp_path, factory, [fact(value=new)], [fact(value=old, start="2026-01-01", end="2026-03-31")])
    item, = result.items
    assert item.status == "new_observation"
    assert item.delta == delta and item.delta_unit == "percentage_points"
    assert item.movement == movement and item.review_worthy is flag
    assert item.review_threshold == 0.2


def test_recollection_is_not_a_new_observation_or_stable_market(factory, tmp_path):
    fact, _ = factory
    result = compare(tmp_path, factory, [fact()], [fact()])
    item, = result.items
    assert item.status == "unchanged_observation"
    assert item.delta is item.movement is item.review_worthy is None
    assert result.labour_direction == "insufficient_data"


def test_same_period_difference_is_a_revision(factory, tmp_path):
    fact, _ = factory
    item, = compare(tmp_path, factory, [fact(value=5.9)], [fact(value=5.4)]).items
    assert item.status == "revised_observation" and item.delta == 0.5
    assert item.review_worthy is None and item.review_threshold is None


def test_missing_and_new_series_are_not_zero(factory, tmp_path):
    fact, _ = factory
    result = compare(tmp_path, factory, [fact()], [fact(metric="unemployed_people", value=171000)])
    assert {item.status for item in result.items} == {"missing_current", "new_series"}
    assert all(item.delta is None for item in result.items)


@pytest.mark.parametrize("metadata", [
    {"adjustment": "trend"}, {"unit": "percentage_points"}, {"source": "Another publisher"},
    {"comparison_basis": "year_on_year"}, {"category": "Another category"},
])
def test_incompatible_series_metadata_is_never_subtracted(factory, tmp_path, metadata):
    fact, _ = factory
    result = compare(tmp_path, factory, [fact(**metadata)], [fact(value=5.4)])
    assert len(result.items) == 2
    assert {item.status for item in result.items} == {"missing_current", "new_series"}
    assert all(item.delta is None for item in result.items)


def test_people_deltas_are_counts_and_percent_growth_deltas_are_points(factory, tmp_path):
    fact, _ = factory
    current = [fact(metric="unemployed_people", value=171000),
               fact(metric="seek_job_ads_change", value=3.2, start="2026-07-01", end="2026-07-31")]
    previous = [fact(metric="unemployed_people", value=165000, start="2026-01-01", end="2026-03-31"),
                fact(metric="seek_job_ads_change", value=1.2, start="2026-06-01", end="2026-06-30")]
    items = {item.series["metric"]: item for item in compare(tmp_path, factory, current, previous).items}
    assert items["unemployed_people"].delta == 6000
    assert items["unemployed_people"].delta_unit == "people"
    assert items["seek_job_ads_change"].delta == 2
    assert items["seek_job_ads_change"].delta_unit == "percentage_points"


@pytest.mark.parametrize("start,end,status", [
    ("2026-01-01", "2026-03-31", "older_observation"),
    ("2026-01-01", "2026-06-30", "not_comparable"),
    ("2026-05-01", "2026-06-30", "not_comparable"),
])
def test_older_or_changed_period_definitions_not_subtracted(factory, tmp_path, start, end, status):
    fact, _ = factory
    item, = compare(tmp_path, factory, [fact(start=start, end=end)], [fact()]).items
    assert item.status == status and item.delta is None


def test_overlapping_annual_windows_can_be_compared(factory, tmp_path):
    fact, _ = factory
    now = fact(metric="cpi_annual_change", value=4.1, start="2025-07-01", end="2026-06-30")
    old = fact(metric="cpi_annual_change", value=3.5, start="2025-04-01", end="2026-03-31")
    item, = compare(tmp_path, factory, [now], [old]).items
    assert item.status == "new_observation" and item.delta == 0.6 and item.review_worthy


def test_calendar_month_lengths_do_not_make_periods_incompatible(factory, tmp_path):
    fact, _ = factory
    now = fact(metric="seek_job_ads_change", value=2, start="2026-03-01", end="2026-03-31")
    old = fact(metric="seek_job_ads_change", value=1, start="2026-02-01", end="2026-02-28")
    assert compare(tmp_path, factory, [now], [old]).items[0].status == "new_observation"


def test_nearest_available_week_and_provenance(factory, tmp_path):
    fact, write = factory
    old_path = write("2026-W35", [fact()])
    write("2026-W34", [fact(value=4)])
    write("2026-W38", [fact(value=9)])
    write("2026-W36", [fact(value=8)], name="runs/2026-W36/ignored.json")
    path = write("2026-W37", [fact()])
    result = compare_evidence(path, tmp_path)
    assert result.previous_file.report_week == "2026-W35" and result.weeks_apart == 2
    assert result.previous_file.sha256 == hashlib.sha256(old_path.read_bytes()).hexdigest()
    assert result.current_file.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.items[0].previous[0].pointer == "/facts/0"
    assert WeeklyComparison.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("broken", ["invalid_json", "empty", "mismatch", "future_collection", "retrieval", "calendar", "schema"])
def test_invalid_nearest_history_falls_back_with_audit(factory, tmp_path, broken):
    fact, write = factory
    write("2026-W35", [fact()])
    invalid = write("2026-W36", [] if broken == "empty" else [fact()])
    data = json.loads(invalid.read_text())
    if broken == "mismatch":
        data["report_week"] = "2026-W35"
    elif broken == "future_collection":
        data["collected_at"] = "2026-09-14T12:00:00+12:00"
    elif broken == "retrieval":
        data["facts"][0]["retrieved_at"] = "2026-09-14T12:00:00+12:00"
    elif broken == "calendar":
        data["week_end"] = "2026-09-20"
    elif broken == "schema":
        data["schema_version"] = 999
    invalid.write_text("not json" if broken == "invalid_json" else json.dumps(data))
    result = compare_evidence(write("2026-W37", [fact()]), tmp_path)
    assert result.previous_file.report_week == "2026-W35"
    assert any("Skipped 2026-W36.json" in note for note in result.history_notes)


def test_iso_year_boundary_and_invalid_iso_week(factory, tmp_path):
    fact, write = factory
    old = fact(start="2025-04-01", end="2025-06-30", source_updated_date=None)
    write("2025-W52", [old])
    (tmp_path / "2025-W53.json").write_text("{}")
    result = compare_evidence(write("2026-W01", [old]), tmp_path)
    assert result.weeks_apart == 1 and result.previous_file.report_week == "2025-W52"
    assert any("invalid ISO week" in note for note in result.history_notes)


def test_invalid_current_file_is_an_error_not_baseline(factory, tmp_path):
    fact, write = factory
    current = write("2026-W37", [fact()])
    data = json.loads(current.read_text())
    data["week_start"] = "2026-09-08"
    current.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="calendar boundaries"):
        compare_evidence(current, tmp_path)


def test_latest_period_selected_and_conflicts_preserved(factory, tmp_path):
    fact, _ = factory
    old = fact(value=5.4, start="2026-01-01", end="2026-03-31")
    result = compare(tmp_path, factory, [old, fact(), fact(value=5.7)], [old])
    assert result.items[0].status == "not_comparable"
    assert len(result.items[0].current) == 2 and result.items[0].delta is None


def test_duplicate_identical_latest_facts_do_not_conflict(factory, tmp_path):
    fact, _ = factory
    item, = compare(tmp_path, factory, [fact(), fact()], [fact()]).items
    assert item.status == "unchanged_observation" and len(item.current) == 1


def test_latest_observation_wins_over_earlier_rows(factory, tmp_path):
    fact, _ = factory
    old = fact(value=5.4, start="2026-01-01", end="2026-03-31")
    item, = compare(tmp_path, factory, [fact(), old], [old]).items
    assert item.status == "new_observation" and item.delta == 0.2
    assert item.current[0].pointer == "/facts/0"


def test_unrecognised_series_semantics_have_no_review_threshold(factory, tmp_path):
    fact, _ = factory
    now = fact(unit="people", value=100)
    old = fact(unit="people", value=50, start="2026-01-01", end="2026-03-31")
    item, = compare(tmp_path, factory, [now], [old]).items
    assert item.delta == 50 and item.review_worthy is None


def test_more_applications_growth_is_an_adverse_competition_signal(factory, tmp_path):
    fact, _ = factory
    now = [fact(value=5.9), fact(metric="seek_applications_per_ad_change", value=3, start="2026-06-01", end="2026-06-30")]
    old = [fact(value=5.4, start="2026-01-01", end="2026-03-31"),
           fact(metric="seek_applications_per_ad_change", value=1, start="2026-05-01", end="2026-05-31")]
    assert compare(tmp_path, factory, now, old).labour_direction == "deteriorating"


@pytest.mark.parametrize("unemployment,ads,direction", [
    (5.1, 3.2, "improving"), (5.9, -3.2, "deteriorating"),
    (5.9, 3.2, "mixed"), (5.5, 0.2, "stable"),
])
def test_labour_direction_is_a_limited_multi_theme_interpretation(factory, tmp_path, unemployment, ads, direction):
    fact, _ = factory
    now = [fact(value=unemployment), fact(metric="seek_job_ads_change", value=ads, start="2026-07-01", end="2026-07-31")]
    old = [fact(value=5.4, start="2026-01-01", end="2026-03-31"),
           fact(metric="seek_job_ads_change", value=0, start="2026-06-01", end="2026-06-30")]
    result = compare(tmp_path, factory, now, old)
    assert result.labour_direction == direction
    assert "not statistical significance" in result.direction_reason


def test_save_preserves_archives_and_previous_view_on_failure(factory, tmp_path, monkeypatch):
    import src.analysis as analysis
    fact, _ = factory
    result = compare(tmp_path, factory, [fact()])
    directory = tmp_path / "comparisons"
    archive, view = save_comparison(result, directory, "first.json")
    original = view.read_bytes()
    assert archive.read_bytes() == original
    with pytest.raises(FileExistsError):
        save_comparison(result, directory, "first.json")

    def fail(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(analysis.os, "replace", fail)
    with pytest.raises(OSError, match="Synthetic disk failure"):
        save_comparison(result, directory, "second.json")
    assert view.read_bytes() == original
    assert (archive.parent / "second.json").exists()
    assert not list(directory.glob(".comparison-*.tmp"))
