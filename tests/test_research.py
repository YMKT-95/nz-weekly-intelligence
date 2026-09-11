"""Synthetic responses exercise collection, access rules, and failure handling."""

import hashlib
import html
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.config import Settings
from src import research
from src.models import ResearchBatch
from src.research import (
    DirectFetcher, Source, SourceUnavailable, collect_research, parse_document, save_research,
)

NOW = datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("Pacific/Auckland"))
SOURCE = Source("test", "Fixture source", "NZ Labour Market",
                "https://example.com/report", "job advertisements")
REPORT_HTML = """<html><head><title>Synthetic labour report</title>
<meta property="article:published_time" content="2026-08-12">
</head><body><header>Navigation to remove</header><main>
<h1>Synthetic labour report</h1><p>Job advertisements changed during July 2026.
Applications per advertisement refer to June 2026, with a one-month lag.</p>
<table><tr><th>Period</th><th>Change</th></tr><tr><td>July 2026</td><td>-0.8%</td></tr></table>
<a href="/download.csv">Download data</a><a href="/download.csv">Duplicate</a>
<script>invented metric: 999</script></main><footer>Footer to remove</footer></body></html>"""


def settings(tmp_path):
    return Settings(data_dir=tmp_path / "weekly", reports_dir=tmp_path / "reports",
                    research_dir=tmp_path / "research", timezone=ZoneInfo("Pacific/Auckland"))


def run_collection(tmp_path, handler, sources=(SOURCE,)):
    return collect_research(settings(tmp_path), "2026-W37", date(2026, 9, 7), date(2026, 9, 13),
                            sources=sources, transport=httpx.MockTransport(handler))


def html_response(text=REPORT_HTML):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=text)


def test_html_retains_periods_tables_and_provenance():
    document = parse_document(SOURCE, SOURCE.url, REPORT_HTML, NOW)
    assert "July 2026 | -0.8%" in document.text
    assert "June 2026" in document.text
    assert "Navigation to remove" not in document.text
    assert "999" not in document.text
    assert "Footer to remove" not in document.text
    assert document.published_at_raw == "2026-08-12"
    assert document.retrieved_at == NOW
    assert str(document.source_url) == SOURCE.url
    assert len(document.links) == 1
    assert str(document.links[0].url) == "https://example.com/download.csv"
    assert document.content_sha256 == hashlib.sha256(document.text.encode()).hexdigest()


def test_missing_publication_date_is_not_replaced_with_retrieval_date():
    content = REPORT_HTML.replace('<meta property="article:published_time" content="2026-08-12">', "")
    document = parse_document(SOURCE, SOURCE.url, content, NOW)
    assert document.published_at_raw is None
    assert document.updated_at_raw is None


def test_stats_embedded_data_retains_labels_and_omits_cms_metadata():
    source = replace(SOURCE, parser="stats", expected_text="unemployment")
    payload = {
        "Title": "Unemployment rate", "FeaturedText": "<p>Synthetic indicator fixture.</p>",
        "PageDate": "2018-01-01", "PageBlocks": [
            {"ClassName": "IndicatorBlock", "Name": "Unemployment rate", "Value": "5.6%",
             "Period": "June 2026 quarter", "Description": "Quarterly",
             "Value2": "+0.2pp", "Period2": "June 2026 quarter",
             "Description2": "Quarterly change, percentage points",
             "LastUpdatedDate": "5 August 2026", "NextUpdatedDate": "4 November 2026",
             "DesiredPublishDate": "2018-02-01"},
            {"ClassName": "TextBlock", "Content": "<p>The series is seasonally adjusted.</p>"},
            {"ClassName": "GraphTableBlock", "Title": "Historical observations",
             "SeriesData": [{"GraphCsvData": "Quarter,Rate\nJune 2026,5.6"}]},
        ],
    }
    content = ('<title>Unemployment rate</title><div id="pageViewData" data-value="'
               + html.escape(json.dumps(payload), quote=True) + '"></div>')
    document = parse_document(source, source.url, content, NOW)
    assert "Value: 5.6%" in document.text
    assert "Period: June 2026 quarter" in document.text
    assert "Description2: Quarterly change, percentage points" in document.text
    assert "Quarter,Rate\nJune 2026,5.6" in document.text
    assert "2018" not in document.text
    assert document.updated_at_raw == "5 August 2026"
    assert document.published_at_raw is None
    assert document.collection_method == "embedded_page_json"


@pytest.mark.parametrize("content", [
    '<html><head><script src="/challenge.js"></script></head><body></body></html>',
    '<title>Just a moment...</title><main>' + 'job advertisements ' * 20 + '</main>',
    '<title>Unrelated page</title><main>' + 'Unrelated text ' * 20 + '</main>',
])
def test_challenges_and_irrelevant_pages_are_not_successes(content):
    with pytest.raises(SourceUnavailable):
        parse_document(SOURCE, SOURCE.url, content, NOW)


@pytest.mark.parametrize("payload", ["not JSON", "[]", '{"PageBlocks": []}'])
def test_changed_stats_payload_is_reported_unavailable(payload):
    content = '<title>Stats fixture</title><div id="pageViewData" data-value="' + html.escape(payload) + '"></div>'
    with pytest.raises(SourceUnavailable):
        parse_document(replace(SOURCE, parser="stats"), SOURCE.url, content, NOW)


def test_partial_failure_does_not_stop_other_sources(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(503) if request.url.path == "/down" else html_response()

    failed = replace(SOURCE, id="failed", url="https://example.com/down")
    batch = run_collection(tmp_path, handler, (failed, SOURCE))
    assert batch.status == "partial"
    assert len(batch.documents) == len(batch.failures) == 1
    assert batch.documents[0].source_id == SOURCE.id
    assert "503" in batch.failures[0].reason


@pytest.mark.parametrize("robots_status", [401, 403, 429, 500])
def test_unavailable_robots_prevents_page_requests(tmp_path, robots_status):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(robots_status)

    batch = run_collection(tmp_path, handler, (SOURCE, replace(SOURCE, id="second")))
    assert batch.status == "unavailable"
    assert len(batch.failures) == 2
    assert requested == ["/robots.txt"]  # Failure cached for this run.


def test_robots_wildcards_are_respected(tmp_path):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /*report$")

    batch = run_collection(tmp_path, handler)
    assert batch.status == "unavailable"
    assert "disallowed" in batch.failures[0].reason
    assert requested == ["/robots.txt"]


@pytest.mark.parametrize("status", [404, 410])
def test_absent_robots_allows_collection(tmp_path, status):
    batch = run_collection(tmp_path, lambda request: httpx.Response(status)
                           if request.url.path == "/robots.txt" else html_response())
    assert batch.status == "complete"


def test_html_challenge_at_robots_is_unavailable(tmp_path):
    batch = run_collection(tmp_path, lambda request: html_response())
    assert batch.status == "unavailable"
    assert "robots.txt returned HTML" in batch.failures[0].reason


def test_crawl_delay_is_applied_and_robots_are_cached(tmp_path, monkeypatch):
    delays = []
    requested = []
    monkeypatch.setattr(research.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(research.time, "sleep", delays.append)

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 10\nDisallow:")
        return html_response()

    batch = run_collection(tmp_path, handler, (SOURCE, replace(SOURCE, id="second")))
    assert len(batch.documents) == 2
    assert requested.count("/robots.txt") == 1
    assert delays == [10.0, 10.0]


def test_redirect_target_is_checked_against_robots(tmp_path):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(302, headers={"location": "/private"})

    batch = run_collection(tmp_path, handler)
    assert batch.status == "unavailable"
    assert requested == ["/robots.txt", "/report"]


def test_same_origin_redirect_preserves_requested_and_final_urls(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if request.url.path == "/report":
            return httpx.Response(301, headers={"location": "/new-report"})
        return html_response()

    batch = run_collection(tmp_path, handler)
    assert str(batch.documents[0].requested_url) == SOURCE.url
    assert str(batch.documents[0].source_url) == "https://example.com/new-report"


def test_cross_origin_redirect_is_not_followed(tmp_path):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        return httpx.Response(302, headers={"location": "https://other.example/report"})

    batch = run_collection(tmp_path, handler)
    assert batch.status == "unavailable"
    assert all("other.example" not in url for url in requested)


def test_timeout_is_a_recorded_failure(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("Synthetic timeout", request=request)

    batch = run_collection(tmp_path, handler)
    assert batch.status == "unavailable"
    assert "timeout" in batch.failures[0].reason


def test_non_html_response_is_not_collected(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    batch = run_collection(tmp_path, handler)
    assert batch.status == "unavailable"
    assert "Unsupported content type" in batch.failures[0].reason


def test_oversized_response_is_rejected(monkeypatch):
    monkeypatch.setattr(research, "MAX_RESPONSE_BYTES", 32)
    with httpx.Client(transport=httpx.MockTransport(lambda request: html_response())) as client:
        with pytest.raises(SourceUnavailable, match="collection limit"):
            DirectFetcher(client)._request(SOURCE.url)


def test_newsroom_follows_one_employment_report_only(tmp_path):
    source = replace(SOURCE, id="seek_newsroom", parser="seek_newsroom")
    newsroom = REPORT_HTML.replace('</main>', '''
        <a href="http://other.example/">External link</a>
        <a href="/about/news/article/salary-report">Salary report</a>
        <a href="/about/news/article/employment-report-july26">July report</a>
        <a href="/about/news/article/employment-report-june26">June report</a></main>''')
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return html_response(newsroom if request.url.path == "/report" else REPORT_HTML)

    batch = run_collection(tmp_path, handler, (source,))
    assert batch.status == "complete"
    assert [doc.source_id for doc in batch.documents] == ["seek_newsroom", "seek_employment_report"]
    assert requested == ["/robots.txt", "/report", "/about/news/article/employment-report-july26"]


def test_missing_report_link_records_partial_discovery(tmp_path):
    batch = run_collection(tmp_path, lambda request: httpx.Response(404)
                           if request.url.path == "/robots.txt" else html_response(),
                           (replace(SOURCE, parser="seek_newsroom"),))
    assert batch.status == "partial"
    assert len(batch.documents) == 1
    assert "no discoverable" in batch.failures[0].reason


def test_snapshots_round_trip_and_do_not_overwrite(tmp_path):
    batch = run_collection(tmp_path, lambda request: httpx.Response(404)
                           if request.url.path == "/robots.txt" else html_response())
    destination = save_research(batch, tmp_path / "research")
    loaded = ResearchBatch.model_validate_json(destination.read_text())
    assert loaded == batch
    assert destination.parent.name == "2026-W37"
    assert json.loads(destination.read_text())["status"] == "complete"
    with pytest.raises(FileExistsError):
        save_research(batch, tmp_path / "research")
    assert ResearchBatch.model_validate_json(destination.read_text()) == batch


def test_deferred_rbnz_makes_no_http_requests_and_preserves_other_coverage(tmp_path):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        assert request.url.host == "example.com"
        return httpx.Response(404) if request.url.path == "/robots.txt" else html_response()

    rbnz = next(s for s in research.SOURCES if s.id == "rbnz_ocr")
    batch = run_collection(tmp_path, handler, (rbnz, SOURCE))
    assert batch.status == "partial" and len(batch.documents) == 1
    failure, = batch.failures
    assert failure.kind == "deferred"
    assert "prior written permission" in failure.reason
    assert len(requested) == 2
    assert ResearchBatch.model_validate_json(batch.model_dump_json()) == batch


def test_mbie_collection_extraction_and_rbnz_deferral(tmp_path, make_mbie_html):
    from src.extraction import extract_evidence, save_evidence
    from src.models import WeeklyData

    def handler(request):
        assert request.url.host == "www.mbie.govt.nz"
        return httpx.Response(404) if request.url.path == "/robots.txt" else html_response(make_mbie_html())

    sources = tuple(s for s in research.SOURCES if s.id in {"mbie_jobs_online", "rbnz_ocr"})
    batch = run_collection(tmp_path, handler, sources)
    weekly = extract_evidence(save_research(batch, tmp_path / "research"), project_root=tmp_path)
    assert len(weekly.facts) == 1 and not weekly.rejected
    assert weekly.collection_failures[0].kind == "deferred"
    archive, canonical = save_evidence(weekly, tmp_path / "weekly")
    assert archive.read_bytes() == canonical.read_bytes()
    assert WeeklyData.model_validate_json(canonical.read_text()) == weekly


def test_failed_rerun_preserves_successful_snapshot(tmp_path):
    batch = run_collection(tmp_path, lambda request: httpx.Response(404)
                           if request.url.path == "/robots.txt" else html_response())
    destination = save_research(batch, tmp_path / "research")
    original = destination.read_bytes()
    later = batch.model_copy(update={"started_at": batch.started_at + timedelta(minutes=1),
                                     "completed_at": batch.completed_at + timedelta(minutes=1),
                                     "documents": []})
    later_destination = save_research(later, tmp_path / "research")
    assert destination != later_destination
    assert destination.read_bytes() == original
    assert ResearchBatch.model_validate_json(later_destination.read_text()).status == "unavailable"
