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
