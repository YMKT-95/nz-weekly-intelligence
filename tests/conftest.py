"""All automated tests run without contacting live websites."""

import httpx
import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from src import research


@pytest.fixture(autouse=True)
def offline_tests(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("Live HTTP is not allowed in automated tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(research.time, "sleep", lambda seconds: None)


@pytest.fixture
def make_stats_document():
    """Build synthetic evidence through the real public-page parser."""
    def make(source_id="stats_unemployment", changes=None, extra_blocks=None, published=None):
        source = next(source for source in research.SOURCES if source.id == source_id)
        if source_id == "stats_unemployment":
            block = {
                "ClassName": "IndicatorBlock", "Name": "Unemployment rate",
                "Description": "Quarterly", "Value": "5.6%", "Period": "June 2026 quarter",
                "Description2": "Quarterly change, percentage points", "Value2": "+0.2pp",
                "Period2": "June 2026 quarter", "Description3": "Number of unemployed people",
                "Value3": "171,000", "Period3": "June 2026 quarter",
                "LastUpdatedDate": "5 August 2026", "NextUpdatedDate": "4 November 2026",
            }
        else:
            block = {
                "ClassName": "IndicatorBlock", "Name": "Consumers price index",
                "Description": "Annual change", "Value": "+4.1%", "Period": "June 2026 year",
                "LastUpdatedDate": "21 July 2026", "NextUpdatedDate": "22 October 2026",
            }
        block.update(changes or {})
        payload = {"Title": "Synthetic " + block["Name"],
                   "FeaturedText": "<p>Synthetic source data for automated tests only.</p>",
                   "PageBlocks": [block, {"ClassName": "TextBlock", "Content": "<p>Fixture context.</p>"}]
                                 + (extra_blocks or [])}
        metadata = f'<meta property="article:published_time" content="{html.escape(published)}">' if published else ""
        content = ('<title>Stats NZ synthetic indicator fixture</title>' + metadata
                   + '<div id="pageViewData" data-value="'
                   + html.escape(json.dumps(payload), quote=True) + '"></div>')
        return research.parse_document(source, source.url, content,
                                       datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("Pacific/Auckland")))
    return make


@pytest.fixture
def make_seek_document():
    """Synthetic values in the supported article layout, parsed through collection."""
    def make(text=None, published=None):
        source = research.Source(
            "seek_employment_report", "SEEK NZ", "NZ Labour Market",
            "https://nz.seek.com/about/news/article/seek-nz-employment-report-july26", "job ad")
        if text is None:
            text = "\n".join([
                "SEEK NZ Employment Report - July",
                "Applications per job ad are recorded with a one-month lag. Data shown in this report refers to June data.",
                "AI Insights:",
                "Job ads referencing AI rose 7.7% in July.",
                "National Insights:",
                "Job ads fell for a third consecutive month, down 2.3% in July.",
                "Applications per job ad rose for a second month, up 1.4%, as opportunities fell.",
                "Region Insights:",
                "Job ads rose 8.8% in July.",
                "National Insights",
                "Job ads fell 2.3% in July, marking three months of decline.",
                "Figure 3: National SEEK job ad percentage change m/m (July 2025 to July 2026)",
                "Applications per job ad have picked up over the past two months, rising 1.4% in June, as opportunities fell.",
                "Industry Insights",
                "Job ads rose 9.9% in July.",
                "About the SEEK Employment Report",
                "Methodology includes reporting on trend estimates rather than seasonally adjusted estimates from August 2025 onwards.",
                "Synthetic article for automated tests; these numbers are not real observations.",
            ])
        meta = f'<meta property="article:published_time" content="{html.escape(published)}">' if published else ""
        content = ('<title>SEEK synthetic employment report</title>' + meta + '<article>'
                   + ''.join('<p>' + html.escape(line) + '</p>' for line in text.splitlines()) + '</article>')
        return research.parse_document(source, source.url, content,
                                       datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("Pacific/Auckland")))
    return make


@pytest.fixture
def make_mbie_html():
    """Synthetic numbers in the official page's supported overview layout."""
    def make():
        return """<title>Synthetic MBIE Jobs Online</title><main>
<h1>Jobs Online</h1>
<p>All the quarterly data series are no longer being seasonally adjusted. Users are recommended to do annual comparisons to avoid seasonal effects.</p>
<h2>Jobs Online quarterly release</h2>
<h3>Overview of key results – Year ended June 2026 quarter</h3>
<ul><li>Online job advertisements grew by 8.2 per cent in the year to the June 2026 quarter. This is a synthetic observation for testing.</li>
<li>Online job advertisements grew across 7 out of 9 industries over the year.</li></ul>
<h3>Download the latest quarterly report</h3>
<h2>About Jobs Online</h2>
<p>Jobs Online monitors changes in an index of online job advertisements, not the number of actual online job advertisements.</p>
<p>Last updated: 14 August 2026</p>
</main>"""
    return make


@pytest.fixture
def make_mbie_document(make_mbie_html):
    def make(content=None):
        source = next(s for s in research.SOURCES if s.id == "mbie_jobs_online")
        return research.parse_document(source, source.url, content or make_mbie_html(),
                                       datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("Pacific/Auckland")))
    return make


@pytest.fixture
def report_inputs(tmp_path, make_stats_document, make_seek_document):
    """Saved synthetic pipeline outputs, including exact source extraction."""
    from datetime import date
    from src.models import ResearchBatch
    from src.research import save_research
    from src.extraction import extract_evidence, save_evidence
    from src.analysis import compare_evidence, save_comparison
    from src.scoring import score_evidence, save_score

    docs = [make_stats_document(), make_stats_document('stats_cpi'), make_seek_document()]
    batch = ResearchBatch(report_week='2026-W37', week_start=date(2026, 9, 7), week_end=date(2026, 9, 13),
                          started_at=docs[0].retrieved_at, completed_at=docs[0].retrieved_at, documents=docs)
    snapshot = save_research(batch, tmp_path / 'research')
    weekly = extract_evidence(snapshot, project_root=tmp_path)
    archive, _ = save_evidence(weekly, tmp_path / 'weekly')
    comparison = compare_evidence(archive, tmp_path / 'weekly')
    comparison_path, _ = save_comparison(comparison, tmp_path / 'comparisons', archive.name)
    score = score_evidence(archive, tmp_path / 'scores')
    score_path, _ = save_score(score, tmp_path / 'scores', archive.name)
    return archive, comparison_path, score_path
