"""Conservative rules for national numerical statements in SEEK NZ reports.

Only recognised observed-change sentences are accepted. Unknown wording, period
disagreements, and missing context produce audit issues rather than guessed facts.
Offsets refer to saved plain text, not to HTML bytes or a subsequently edited page.
"""

import calendar
import hashlib
import re
from datetime import date, datetime
from urllib.parse import urlsplit

from src.models import ExtractionIssue, SourceDocument, TextSpan, WeeklyFact

MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
MONTH = "(?:" + "|".join(calendar.month_name[1:]) + ")"
NUMBER = r"(?P<number>\d+(?:\.\d+)?)%"
CHANGE = re.compile(
    r"(?P<direction>fell|rose|declined|increased|decreased|dropped|grew)"
    r"(?:(?: by)? | for (?:a|the) (?:first|second|third|fourth) "
    r"(?:consecutive )?month, (?P<echo>down|up) )" + NUMBER + r"(?P<tail>.*)", re.I)
PICKED_UP = re.compile(
    r"have picked up over the past two months, rising " + NUMBER + r"(?P<tail>.*)", re.I)
METRICS = {"Job ads": "seek_job_ads_change",
           "Applications per job ad": "seek_applications_per_ad_change"}


def _lines(document):
    position = 0
    for line in document.text.splitlines(keepends=True):
        quote = line.strip()
        if quote:
            start = position + line.index(quote)
            yield start, quote
        position += len(line)


def _span(line, role):
    start, quote = line
    return TextSpan(role=role, start=start, end=start + len(quote), quote=quote)


def _date(raw):
    if raw is None or raw == "":
        return None
    try:
        return datetime.fromisoformat(raw).date() if "T" in raw else date.fromisoformat(raw)
    except ValueError:
        raise ValueError("Unrecognised SEEK date metadata; retrieval time is not a substitute") from None


def _check_document(document):
    if (document.source_id != "seek_employment_report" or document.source != "SEEK NZ"
            or document.collection_method != "html"):
        raise ValueError("Unsupported SEEK source identity or collection method")
    for url in (document.requested_url, document.source_url):
        parts = urlsplit(str(url))
        if (parts.scheme != "https" or parts.netloc != "nz.seek.com"
                or not re.fullmatch(r"/about/news/article/seek-nz-employment-report-[a-z0-9-]+/?", parts.path)
                or parts.query or parts.fragment):
            raise ValueError("Source URL does not match an official SEEK NZ employment report")
    if document.content_sha256 != hashlib.sha256(document.text.encode("utf-8")).hexdigest():
        raise ValueError("Collected source text does not match its saved checksum")


def _report_period(lines):
    headings = [(line, re.fullmatch(r"SEEK NZ Employment Report\s*[-–—]\s*(" + MONTH
                                  + r")(?: (\d{4}))?", line[1], re.I)) for line in lines]
    headings = [(line, match) for line, match in headings if match]
    if len(headings) != 1:
        raise ValueError("Expected one explicit SEEK report heading")
    heading, match = headings[0]
    month = MONTHS[match[1].lower()]
    # A chart caption can establish the report year without guessing from the URL
    # or retrieval date. It does not supply values from the unseen chart image.
    captions = []
    for line in lines:
        caption = re.fullmatch(
            r"Figure \d+: National SEEK job ad percentage change m/m \((" + MONTH
            + r") (\d{4}) to (" + MONTH + r") (\d{4})\)", line[1], re.I)
        if caption:
            if (MONTHS[caption[1].lower()] != month or MONTHS[caption[3].lower()] != month
                    or int(caption[4]) != int(caption[2]) + 1):
                raise ValueError("Report heading and national monthly chart period disagree")
            captions.append((line, int(caption[4])))
    years = {year for _, year in captions}
    if match[2]:
        years.add(int(match[2]))
    if len(years) != 1:
        raise ValueError("Missing or conflicting explicit report year; URL and retrieval year are not evidence")
    spans = [_span(heading, "report_heading")]
    spans.extend(_span(line, "report_period") for line, _ in captions)
    return date(years.pop(), month, 1), spans, bool(captions)


def _lag_period(lines, report):
    notes = [line for line in lines if "one-month lag" in line[1].lower()]
    if len(notes) != 1:
        raise ValueError("Applications require one explicit, unambiguous reporting-lag note")
    match = re.fullmatch(
        r"Applications per job ad are recorded with a one-month lag\. "
        r"Data shown in this report refers to (" + MONTH + r")(?: (\d{4}))? data\.", notes[0][1], re.I)
    if not match:
        raise ValueError("Unrecognised applications reporting-lag note")
    expected = date(report.year - 1, 12, 1) if report.month == 1 else report.replace(month=report.month - 1)
    if (MONTHS[match[1].lower()] != expected.month
            or (match[2] and int(match[2]) != expected.year)):
        raise ValueError("Applications data period contradicts the stated one-month lag")
    return expected, _span(notes[0], "lag")


def _statement(text, subject, expected, monthly_context):
    body = text[len(subject):].strip()
    match = CHANGE.fullmatch(body)
    picked = PICKED_UP.fullmatch(body) if subject == "Applications per job ad" else None
    if not match and not picked:
        raise ValueError("Unrecognised observed-change wording; numerical meaning requires review")
    direction = match["direction"].lower() if match else "rose"
    sign = -1 if direction in {"fell", "declined", "decreased", "dropped"} else 1
    if match and match["echo"] and (match["echo"].lower() == "down") != (sign == -1):
        raise ValueError("Conflicting change directions in supporting statement")
    match = match or picked
    tail = match["tail"]
    if re.search(r"%|percentage points|\b(?:forecast|expected|projected|would|could|will)\b", tail, re.I):
        raise ValueError("Multiple values, incompatible units, or forward-looking wording requires review")
    if not re.fullmatch(
        r"(?: (?:m/m|y/y|month-on-month|year-on-year))?"
        r"(?: in " + MONTH + r"(?: \d{4})?)?(?:\.|, (?:as|marking) [^.!?]+\.)", tail, re.I
    ):
        raise ValueError("Unrecognised comparison or period wording requires review")
    annual = bool(re.search(r"\b(?:y/y|year-on-year)\b", tail, re.I))
    monthly = bool(re.search(r"\b(?:m/m|month-on-month)\b", tail, re.I))
    if annual and monthly:
        raise ValueError("Conflicting comparison bases")
    if not annual and not monthly and not monthly_context:
        raise ValueError("No explicit monthly or annual comparison context")
    periods = re.findall(r"\b(" + MONTH + r")(?: (\d{4}))?\b", tail, re.I)
    for month, year in periods:
        if MONTHS[month.lower()] != expected.month or (year and int(year) != expected.year):
            raise ValueError("Statement data period disagrees with the report month or reporting lag")
    value = sign * float(match["number"])
    if value < -100:
        raise ValueError("A percentage decline cannot exceed 100 percent")
    return value, "year_on_year" if annual else "month_on_month"


def extract_seek(document: SourceDocument, snapshot_file: str, snapshot_hash: str
                 ) -> tuple[list[WeeklyFact], list[ExtractionIssue]]:
    """Map supported national statements, withholding a metric if its context conflicts."""
    _check_document(document)
    lines = list(_lines(document))
    report, context, monthly_context = _report_period(lines)
    published, updated = _date(document.published_at_raw), _date(document.updated_at_raw)
    observations = {subject: [] for subject in METRICS}
    section = None
    for line in lines:
        if line[1].rstrip(":").casefold() == "national insights":
            section = line
            continue
        if re.fullmatch(r".+ Insights:?|NOTES|ENDS", line[1], re.I):
            section = None
        if section:
            for subject in METRICS:
                if line[1].casefold().startswith(subject.casefold() + " "):
                    observations[subject].append((line, section))
    facts, issues = [], []
    for subject, metric in METRICS.items():
        supporting = list(context)
        metric_facts = []
        try:
            if not observations[subject]:
                raise ValueError("No supported national statement found for " + metric)
            period = report
            if subject == "Applications per job ad":
                period, lag = _lag_period(lines, report)
                supporting.append(lag)
            adjustment = "not_stated"
            if subject == "Job ads" and report >= date(2025, 8, 1):
                for line in lines:
                    if "reporting on trend estimates rather than seasonally adjusted estimates from August 2025 onwards" in line[1]:
                        adjustment = "trend"
                        supporting.append(_span(line, "methodology"))
            for line, section in observations[subject]:
                supporting.extend([_span(section, "section"), _span(line, "statement")])
            # All statements for a metric are supplied as context, including duplicates.
            supporting = list({(s.role, s.start, s.end): s for s in supporting}.values())
            for line, _ in observations[subject]:
                value, basis = _statement(line[1], subject, period, monthly_context)
                metric_facts.append(WeeklyFact(
                    category="NZ Labour Market", metric=metric, value=value, unit="percent",
                    comparison_basis=basis, period=period.strftime("%B %Y"), period_start=period,
                    period_end=date(period.year, period.month, calendar.monthrange(period.year, period.month)[1]),
                    adjustment=adjustment, source=document.source, source_url=document.source_url,
                    publication_date=published, source_updated_date=updated, retrieved_at=document.retrieved_at,
                    extraction_method="seek_article_v1",
                    confidence_reason="Recognised national SEEK statement matched to saved text, report period, and comparison context.",
                    evidence={"kind": "text", "snapshot_file": snapshot_file, "snapshot_sha256": snapshot_hash,
                              "document_sha256": document.content_sha256, "source_id": document.source_id,
                              "spans": supporting},
                ))
            facts.extend(metric_facts)
        except ValueError as exc:
            # Include the statements even when period/lag validation failed first.
            audit = supporting + [_span(line, "statement") for line, _ in observations[subject]]
            audit = list({(s.role, s.start, s.end): s for s in audit}.values())
            issues.append(ExtractionIssue(source_id=document.source_id,
                                          reason=f"{metric}: {exc}", text_spans=audit))
    return facts, issues


def validate_seek_fact(candidate, document, snapshot_file, snapshot_hash):
    """Recompute the mapping; a matching number alone cannot validate a candidate."""
    fact = WeeklyFact.model_validate(candidate)
    expected, _ = extract_seek(document, snapshot_file, snapshot_hash)
    # Conflicting values within one article must not pass independent validation.
    matching = [item for item in expected if (item.metric, item.comparison_basis)
                == (fact.metric, fact.comparison_basis)]
    if len({item.value for item in matching}) > 1 or fact not in matching:
        raise ValueError("Candidate does not match the source value, meaning, dates, or provenance")
    return fact
