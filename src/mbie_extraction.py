"""Bounded extraction of the national annual Jobs Online quarterly change.

This handles the official HTML overview, not its downloadable time series.
No result can be produced from a challenge page or a search-engine snippet.
"""

import calendar
import hashlib
import re
from datetime import date, datetime
from urllib.parse import urlsplit

from src.models import SourceDocument, TextSpan, WeeklyFact

SOURCE_PATH = ("/business-and-employment/employment-and-skills/"
               "labour-market-reports-data-and-analysis/jobs-online")
MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
QUARTER = r"(March|June|September|December) (\d{4})"
HEADING = re.compile(r"Overview of key results\s*[–—-]\s*Year ended " + QUARTER + r" quarter", re.I)
STATEMENT = re.compile(
    r"Online job advertisements (grew|increased|fell|decreased) by (\d+(?:\.\d+)?) "
    r"(?:per cent|percent) in the year to the " + QUARTER + r" quarter\.(?: |$)", re.I)
INDEX_CONTEXT = ("Jobs Online monitors changes in an index of online job advertisements, "
                 "not the number of actual online job advertisements.")
ADJUSTMENT_CONTEXT = "All the quarterly data series are no longer being seasonally adjusted."


def _lines(text):
    offset = 0
    for line in text.splitlines(keepends=True):
        quote = line.strip()
        if quote:
            yield offset + line.index(quote), quote
        offset += len(line)


def _span(line, role):
    offset, quote = line
    return TextSpan(role=role, start=offset, end=offset + len(quote), quote=quote)


def _date(raw):
    if not raw:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return date.fromisoformat(raw)
    if "T" in raw:
        return datetime.fromisoformat(raw).date()
    match = re.fullmatch(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", raw)
    if match and match[2].lower() in MONTHS:
        return date(int(match[3]), MONTHS[match[2].lower()], int(match[1]))
    raise ValueError("Unrecognised MBIE date; retrieval time is not a substitute")


def _check_document(document):
    if (document.source_id != "mbie_jobs_online" or document.source != "MBIE"
            or document.collection_method != "html"):
        raise ValueError("Unsupported MBIE source identity or collection method")
    for url in (document.requested_url, document.source_url):
        parts = urlsplit(str(url))
        if (parts.scheme != "https" or parts.netloc != "www.mbie.govt.nz"
                or parts.path.rstrip("/") != SOURCE_PATH or parts.query or parts.fragment):
            raise ValueError("Source URL does not match the official MBIE Jobs Online page")
    if document.content_sha256 != hashlib.sha256(document.text.encode("utf-8")).hexdigest():
        raise ValueError("Collected source text does not match its saved checksum")


def extract_mbie(document: SourceDocument, snapshot_file: str, snapshot_hash: str) -> WeeklyFact:
    """Require the national overview, meaning, adjustment, period and exact value."""
    _check_document(document)
    lines = list(_lines(document.text))
    headings = [(index, HEADING.fullmatch(line[1])) for index, line in enumerate(lines)
                if HEADING.fullmatch(line[1])]
    if len(headings) != 1:
        raise ValueError("Expected one explicit MBIE national quarterly overview heading")
    index, heading = headings[0]
    # In the supported layout the national total is the first result. Never search
    # through regional/industry results or previous reports for a convenient value.
    if index + 1 >= len(lines):
        raise ValueError("Missing national quarterly observation")
    observation = lines[index + 1]
    match = STATEMENT.match(observation[1])
    if match is None:
        raise ValueError("Unrecognised national annual-change statement; units or meaning require review")
    if (match[3].lower(), match[4]) != (heading[1].lower(), heading[2]):
        raise ValueError("National statement and overview data periods disagree")
    # Keep an additional supported total from silently contradicting the first.
    totals = [STATEMENT.match(line[1]) for line in lines]
    for total in filter(None, totals):
        if (total[1].lower(), total[2], total[3].lower(), total[4]) != (
                match[1].lower(), match[2], match[3].lower(), match[4]):
            raise ValueError("Conflicting national statements require review")
    index_lines = [line for line in lines if line[1].startswith(INDEX_CONTEXT)]
    adjustment_lines = [line for line in lines if line[1].startswith(ADJUSTMENT_CONTEXT)]
    if len(index_lines) != 1 or len(adjustment_lines) != 1:
        raise ValueError("Missing or ambiguous index/quarterly adjustment context")
    month, year = MONTHS[match[3].lower()], int(match[4])
    value = float(match[2]) * (-1 if match[1].lower() in {"fell", "decreased"} else 1)
    if value < -100:
        raise ValueError("A percentage decline cannot exceed 100 percent")
    spans = [_span(lines[index], "report_period"), _span(observation, "statement"),
             _span(index_lines[0], "methodology"), _span(adjustment_lines[0], "methodology")]
    # A page update is not necessarily the quarterly report's publication date.
    updates = [line for line in lines if line[1].startswith("Last updated:")]
    dates = {_date(line[1].removeprefix("Last updated:").strip()) for line in updates}
    if document.updated_at_raw:
        dates.add(_date(document.updated_at_raw))
    if len(dates) > 1:
        raise ValueError("Conflicting page update dates require review")
    updated = next(iter(dates), None)
    # Keep the exact visible update date in the evidence as well as the metadata.
    spans.extend(_span(line, "source_date") for line in updates)
    return WeeklyFact(
        category="NZ Labour Market", metric="mbie_job_ads_annual_change", value=value,
        unit="percent", comparison_basis="year_on_year", adjustment="unadjusted",
        period=f"{calendar.month_name[month]} {year} quarter",
        period_start=date(year, month - 2, 1), period_end=date(year, month, calendar.monthrange(year, month)[1]),
        source=document.source, source_url=document.source_url, retrieved_at=document.retrieved_at,
        publication_date=_date(document.published_at_raw), source_updated_date=updated,
        extraction_method="mbie_jobs_online_v1",
        confidence_reason="Recognised MBIE national annual change matched to saved overview, quarter, and unadjusted index context.",
        evidence={"kind": "text", "snapshot_file": snapshot_file, "snapshot_sha256": snapshot_hash,
                  "source_id": document.source_id, "document_sha256": document.content_sha256, "spans": spans},
    )


def validate_mbie_fact(candidate, document, snapshot_file, snapshot_hash):
    fact = WeeklyFact.model_validate(candidate)
    if fact != extract_mbie(document, snapshot_file, snapshot_hash):
        raise ValueError("Candidate does not match the source value, meaning, dates, or provenance")
    return fact
