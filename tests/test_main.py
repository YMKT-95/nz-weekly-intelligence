"""Verify command orchestration and exit status without live sources."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from src.config import Settings, load_settings
from src.models import ResearchBatch, SourceFailure
from src.research import Source, parse_document


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
    assert not list(settings.data_dir.iterdir())


@pytest.mark.parametrize("value", ["0", "-1", "121", "nan", "inf", "invalid"])
def test_invalid_timeout_is_rejected(monkeypatch, value):
    monkeypatch.setenv("REPORT_TIMEZONE", "Pacific/Auckland")
    monkeypatch.setenv("RESEARCH_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="RESEARCH_TIMEOUT_SECONDS"):
        load_settings()


@pytest.mark.parametrize("partial", [False, True])
def test_usable_research_is_saved_and_exits_successfully(tmp_path, monkeypatch, partial):
    settings = Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                        research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(main, "load_settings", lambda: settings)

    def collect(settings, report_week, week_start, week_end):
        now = datetime.now(settings.timezone)
        source = Source("fixture", "Fixture", "NZ Economy", "https://example.com/report", "fixture")
        content = '<title>Fixture report</title><main>' + 'Fixture source material. ' * 10 + '</main>'
        document = parse_document(source, source.url, content, now)
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
    assert not list(settings.reports_dir.iterdir())
