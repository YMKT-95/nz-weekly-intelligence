"""Verify command orchestration and exit status without live sources."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from src.analysis import WeeklyComparison
from src.scoring import WeeklyScore
from src.config import Settings, load_settings
from src.models import ResearchBatch, SourceFailure, WeeklyData
from src.extraction import extract_evidence


@pytest.fixture(autouse=True)
def use_temporary_project_root(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "extract_evidence", lambda path: extract_evidence(path, project_root=tmp_path))


def test_all_sources_unavailable_saves_diagnostics_and_exits_nonzero(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)

    def collect(settings, report_week, week_start, week_end):
        now = datetime.now(settings.timezone)
        return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                             started_at=now, completed_at=now, failures=[
                                 SourceFailure(source_id="fixture", source="Fixture", source_url="https://example.com/",
                                               attempted_at=now, reason="Synthetic unavailable source")])

    monkeypatch.setattr(main, "collect_research", collect)
    assert main.main() == 1
    saved = list(settings.research_dir.glob("*/*.json"))
    assert len(saved) == 1
    assert ResearchBatch.model_validate_json(saved[0].read_text()).status == "unavailable"
    assert not list(settings.reports_dir.iterdir())
    assert not list(settings.data_dir.glob("*.json"))
    assert len(list(settings.data_dir.glob("runs/*/*.json"))) == 1


@pytest.mark.parametrize("value", ["0", "-1", "121", "nan", "inf", "invalid"])
def test_invalid_timeout_is_rejected(monkeypatch, value):
    monkeypatch.setenv("REPORT_TIMEZONE", "Pacific/Auckland")
    monkeypatch.setenv("RESEARCH_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="RESEARCH_TIMEOUT_SECONDS"):
        load_settings()


@pytest.mark.parametrize("partial", [False, True])
def test_supported_evidence_is_saved_and_exits_successfully(tmp_path, monkeypatch, partial, make_stats_document):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)

    def collect(settings, report_week, week_start, week_end):
        document = make_stats_document()
        now = document.retrieved_at
        failures = [SourceFailure(source_id="failed", source="Failed fixture", source_url="https://example.com/down",
                                  attempted_at=now, reason="Synthetic failure")] if partial else []
        return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                             started_at=now, completed_at=now, documents=[document], failures=failures)

    monkeypatch.setattr(main, "collect_research", collect)
    assert main.main() == 0
    saved = list(settings.research_dir.glob("*/*.json"))
    assert len(saved) == 1
    batch = ResearchBatch.model_validate_json(saved[0].read_text())
    assert batch.status == ("partial" if partial else "complete")
    report_path, = settings.reports_dir.glob("*.md")
    assert "insufficient evidence for all six components" in report_path.read_text()
    assert len(list(settings.reports_dir.glob("runs/*/*.md"))) == 1
    assert len(list(settings.data_dir.glob("*.json"))) == 1
    comparison_path, = (settings.data_dir / "comparisons").glob("*.json")
    comparison = WeeklyComparison.model_validate_json(comparison_path.read_text())
    assert comparison.previous_file is None
    assert all(item.status == "baseline" for item in comparison.items)
    score_path, = (settings.data_dir / "scores").glob("*.json")
    score = WeeklyScore.model_validate_json(score_path.read_text())
    assert score.status == "insufficient_evidence" and score.overall_score is None
    assert score.covered_weight_percent == 15
    assert score.current_file.sha256 == comparison.current_file.sha256


def test_mixed_evidence_and_seek_rejection_are_saved_by_command(
        tmp_path, monkeypatch, make_stats_document, make_seek_document):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    seek = make_seek_document(make_seek_document().text.replace(
        "Job ads fell 2.3% in July", "Job ads fell 2.3% in June"))

    def collect(settings, report_week, week_start, week_end):
        return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                             started_at=seek.retrieved_at, completed_at=seek.retrieved_at,
                             documents=[make_stats_document(), make_stats_document("stats_cpi"), seek])

    monkeypatch.setattr(main, "collect_research", collect)
    assert main.main() == 0
    path, = settings.data_dir.glob("*.json")
    weekly = WeeklyData.model_validate_json(path.read_text())
    assert len(weekly.facts) == 5
    assert "data period disagrees" in weekly.rejected[0].reason
    assert weekly.facts[-1].metric == "seek_applications_per_ad_change"
    assert len(list(settings.data_dir.glob("runs/*/*.json"))) == 1
    report_path, = settings.reports_dir.glob("*.md")
    assert "Rejected candidate" in report_path.read_text()
    assert "SEEK national job-ad change:" not in report_path.read_text()


def test_comparison_save_failure_leaves_evidence_and_exits_nonzero(
        tmp_path, monkeypatch, make_stats_document):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    doc = make_stats_document()

    def collect(settings, report_week, week_start, week_end):
        return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                             started_at=doc.retrieved_at, completed_at=doc.retrieved_at, documents=[doc])

    def fail(*args):
        raise OSError("Synthetic comparison write failure")

    monkeypatch.setattr(main, "collect_research", collect)
    monkeypatch.setattr(main, "save_comparison", fail)
    assert main.main() == 1
    assert len(list(settings.data_dir.glob("*.json"))) == 1
    assert len(list(settings.data_dir.glob("runs/*/*.json"))) == 1


def test_score_save_failure_preserves_evidence_and_comparison(tmp_path, monkeypatch, make_stats_document):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    doc = make_stats_document()

    def collect(settings, report_week, week_start, week_end):
        return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                             started_at=doc.retrieved_at, completed_at=doc.retrieved_at, documents=[doc])

    def fail(*args):
        raise OSError("Synthetic scoring write failure")

    monkeypatch.setattr(main, "collect_research", collect)
    monkeypatch.setattr(main, "save_score", fail)
    assert main.main() == 1
    assert len(list(settings.data_dir.glob("*.json"))) == 1
    assert len(list((settings.data_dir / "comparisons").glob("*.json"))) == 1


@pytest.mark.parametrize("stage", ["build_report", "save_report"])
def test_report_failure_preserves_saved_stages(tmp_path, monkeypatch, make_stats_document, stage):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    doc = make_stats_document()

    def collect(settings, report_week, week_start, week_end):
        return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                             started_at=doc.retrieved_at, completed_at=doc.retrieved_at, documents=[doc])

    def fail(*args):
        raise OSError("Synthetic report failure")

    monkeypatch.setattr(main, "collect_research", collect)
    monkeypatch.setattr(main, stage, fail)
    assert main.main() == 1
    for directory in (settings.data_dir, settings.data_dir / "comparisons", settings.data_dir / "scores"):
        assert len(list(directory.glob("*.json"))) == 1
    assert not list(settings.reports_dir.glob("*.md"))
