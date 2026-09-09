"""Deterministic Stats NZ extraction with source matching and an audit trail."""

import calendar
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from src.config import PROJECT_ROOT
from src.models import (
    ExtractionIssue, ResearchBatch, SourceDocument, WeeklyData, WeeklyFact,
)


@dataclass(frozen=True)
class IndicatorRule:
    metric: str
    unit: str
    basis: str
    period_kind: str


# Descriptions establish meaning; a field's position alone never does.
RULES = {
    "stats_unemployment": {
        "quarterly": IndicatorRule("unemployment_rate", "percent", "level", "quarter"),
        "quarterly change, percentage points": IndicatorRule(
            "unemployment_rate_change", "percentage_points", "quarter_on_quarter", "quarter"),
        "number of unemployed people": IndicatorRule("unemployed_people", "people", "level", "quarter"),
    },
    "stats_cpi": {
        "annual change": IndicatorRule("cpi_annual_change", "percent", "year_on_year", "year"),
    },
}
SOURCE_PATHS = {
    "stats_unemployment": "/indicators/unemployment-rate",
    "stats_cpi": "/indicators/consumers-price-index-cpi",
}
SOURCE_NAMES = {
    "stats_unemployment": {"unemployment rate"},
    "stats_cpi": {"consumers price index", "consumers price index (cpi)"},
}
MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}


def _normalise(value) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _structured_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _check_document(document: SourceDocument) -> list:
    if document.source_id not in RULES or document.source != "Stats NZ":
        raise ValueError("No supported Stats NZ source identity")
    for url in (document.requested_url, document.source_url):
        parts = urlsplit(str(url))
        if (parts.scheme != "https" or parts.netloc != "www.stats.govt.nz"
                or parts.path.rstrip("/") != SOURCE_PATHS[document.source_id]
                or parts.query or parts.fragment):
            raise ValueError("Source URL does not match the configured Stats NZ indicator")
    if document.collection_method != "embedded_page_json":
        raise ValueError("Stats NZ evidence requires embedded page JSON")
    if document.content_sha256 != hashlib.sha256(document.text.encode("utf-8")).hexdigest():
        raise ValueError("Collected source text does not match its saved checksum")
    data = document.structured_data
    if data is None:
        raise ValueError("Snapshot has no structured indicator fields; run collection again")
    if document.structured_sha256 != _structured_hash(data):
        raise ValueError("Structured source fields do not match their saved checksum")
    blocks = data.get("PageBlocks")
    if not isinstance(blocks, list):
        raise ValueError("Structured source has no PageBlocks array")
    return blocks


def _number(raw, unit: str) -> int | float:
    if not isinstance(raw, str):
        raise ValueError("Value must retain the original source string")
    value = raw.strip().replace("\u2212", "-")
    if unit == "people":
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", value):
            raise ValueError("People count must be a non-negative integer with valid grouping")
        return int(value.replace(",", ""))
    suffix = "%" if unit == "percent" else "pp"
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?" + re.escape(suffix), value):
        raise ValueError(f"Value must explicitly use {suffix}; units cannot be inferred")
    return float(value[:-len(suffix)])


def _period(raw, expected_kind: str) -> tuple[str, date, date]:
    if not isinstance(raw, str):
        raise ValueError("Missing data period")
    match = re.fullmatch(r"([A-Za-z]+) (\d{4}) (quarter|year)", raw.strip())
    if not match or match[3] != expected_kind or match[1].lower() not in MONTHS:
        raise ValueError(f"Expected an explicit month and year followed by '{expected_kind}'")
    month, year = MONTHS[match[1].lower()], int(match[2])
    end = date(year, month, calendar.monthrange(year, month)[1])
    if expected_kind == "quarter":
        if month not in (3, 6, 9, 12):
            raise ValueError("Quarter period must end in March, June, September, or December")
        start = date(year, month - 2, 1)
    else:
        start = date(year, 1, 1) if month == 12 else date(year - 1, month + 1, 1)
    return raw.strip(), start, end


def _date(raw) -> date | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ValueError("Source date must be text")
    value = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    if "T" in value:
        return datetime.fromisoformat(value).date()
    match = re.fullmatch(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", value)
    if match and match[2].lower() in MONTHS:
        return date(int(match[3]), MONTHS[match[2].lower()], int(match[1]))
    raise ValueError("Unrecognised source date; it must not be replaced with retrieval time")


def _candidate(document: SourceDocument, block: dict, index: int, suffix: str,
               snapshot_file: str, snapshot_hash: str) -> dict:
    if block.get("ClassName") != "IndicatorBlock":
        raise ValueError("Evidence location is not an IndicatorBlock")
    if _normalise(block.get("Name")) not in SOURCE_NAMES[document.source_id]:
        raise ValueError("Indicator name does not match the supported metric")
    description = _normalise(block.get("Description" + suffix))
    rule = RULES[document.source_id].get(description)
    if rule is None:
        raise ValueError("Unknown or missing indicator description; metric meaning is ambiguous")
    value = _number(block.get("Value" + suffix), rule.unit)
    if rule.metric == "unemployment_rate" and not 0 <= value <= 100:
        raise ValueError("Unemployment rate must be between 0 and 100 percent")
    if rule.metric == "unemployment_rate_change" and not -100 <= value <= 100:
        raise ValueError("Rate change is outside the possible percentage-point range")
    if rule.metric == "cpi_annual_change" and value < -100:
        raise ValueError("An annual price change cannot be below -100 percent")
    period, start, end = _period(block.get("Period" + suffix), rule.period_kind)
    corrected = _date(block.get("CorrectedDate"))
    if corrected is not None and corrected > document.retrieved_at.date():
        raise ValueError("Source correction date is in the future")
    keys = ("Name", "Description" + suffix, "Value" + suffix, "Period" + suffix,
            "LastUpdatedDate", "CorrectedDate")
    return {
        "category": "NZ Labour Market" if document.source_id == "stats_unemployment" else "NZ Economy",
        "metric": rule.metric, "value": value, "unit": rule.unit, "comparison_basis": rule.basis,
        "period": period, "period_start": start, "period_end": end,
        "source": document.source, "source_url": document.source_url,
        "publication_date": _date(document.published_at_raw),
        "source_updated_date": _date(block.get("LastUpdatedDate")),
        "retrieved_at": document.retrieved_at,
        "confidence_reason": "Direct mapping of supported Stats NZ fields; source and field values matched.",
        "evidence": {
            "snapshot_file": snapshot_file, "snapshot_sha256": snapshot_hash,
            "document_sha256": document.content_sha256,
            "structured_sha256": document.structured_sha256,
            "source_id": document.source_id, "json_pointer": f"/PageBlocks/{index}/Value{suffix}",
            "raw_fields": {key: block[key] for key in keys if key in block},
        },
    }


def validate_fact(candidate: dict, document: SourceDocument,
                  snapshot_file: str, snapshot_hash: str) -> WeeklyFact:
    """Check schema and compare every candidate field with its source mapping."""
    fact = WeeklyFact.model_validate(candidate)
    blocks = _check_document(document)
    match = re.fullmatch(r"/PageBlocks/(\d+)/Value([2-6]?)", fact.evidence.json_pointer)
    if match is None:
        raise ValueError("Unsupported evidence pointer")
    index, suffix = int(match[1]), match[2]
    if index >= len(blocks) or not isinstance(blocks[index], dict):
        raise ValueError("Evidence pointer does not identify a saved indicator block")
    expected = WeeklyFact.model_validate(_candidate(
        document, blocks[index], index, suffix, snapshot_file, snapshot_hash,
    ))
    if fact != expected:
        raise ValueError("Candidate does not match the source value, meaning, dates, or provenance")
    return fact


def extract_evidence(snapshot_path: Path, *, project_root: Path = PROJECT_ROOT) -> WeeklyData:
    """Read persisted evidence; never infer structured facts from old flattened text."""
    raw = snapshot_path.read_bytes()
    batch = ResearchBatch.model_validate_json(raw)
    reference = snapshot_path.resolve().relative_to(project_root.resolve()).as_posix()
    snapshot_hash = hashlib.sha256(raw).hexdigest()
    weekly = WeeklyData(
        report_week=batch.report_week, week_start=batch.week_start, week_end=batch.week_end,
        collected_at=batch.completed_at, research_snapshot=reference, research_status=batch.status,
        collection_failures=batch.failures,
    )
    candidates = []
    for document in batch.documents:
        if document.source_id not in RULES:
            weekly.skipped.append(ExtractionIssue(
                source_id=document.source_id, reason="No deterministic extractor for this source yet"))
            continue
        try:
            if document.retrieved_at > batch.completed_at:
                raise ValueError("Document retrieval timestamp is after snapshot completion")
            blocks = _check_document(document)
        except ValueError as exc:
            weekly.rejected.append(ExtractionIssue(source_id=document.source_id, reason=str(exc)))
            continue
        found = False
        for index, block in enumerate(blocks):
            if block is None:
                continue
            if not isinstance(block, dict):
                weekly.rejected.append(ExtractionIssue(source_id=document.source_id,
                    json_pointer=f"/PageBlocks/{index}", reason="Malformed indicator block"))
                continue
            for suffix in ("", "2", "3", "4", "5", "6"):
                if all(block.get(key + suffix) in (None, "") for key in ("Description", "Value", "Period")):
                    continue
                found = True
                try:
                    candidate = _candidate(document, block, index, suffix, reference, snapshot_hash)
                    candidates.append(validate_fact(candidate, document, reference, snapshot_hash))
                except ValueError as exc:
                    reason = ("Schema validation failed: " + "; ".join(error["msg"] for error in exc.errors())
                              if isinstance(exc, ValidationError) else str(exc))
                    weekly.rejected.append(ExtractionIssue(
                        source_id=document.source_id, json_pointer=f"/PageBlocks/{index}/Value{suffix}",
                        reason=reason, raw_fields=block))
        if not found:
            weekly.rejected.append(ExtractionIssue(source_id=document.source_id,
                                                   reason="No populated indicator observations found"))
    # Keep distinct periods/bases separate. Reject conflicting observations rather than averaging.
    grouped = {}
    for fact in candidates:
        key = (fact.metric, fact.unit, fact.comparison_basis, fact.period_start, fact.period_end, fact.geography)
        grouped.setdefault(key, []).append(fact)
    for group in grouped.values():
        if len({fact.value for fact in group}) > 1:
            for fact in group:
                weekly.rejected.append(ExtractionIssue(
                    source_id=fact.evidence.source_id, json_pointer=fact.evidence.json_pointer,
                    reason="Conflicting values for the same metric and data period; manual review required",
                    raw_fields=fact.evidence.raw_fields))
        else:
            weekly.facts.append(group[0])
    return weekly


def save_evidence(weekly: WeeklyData, directory: Path) -> tuple[Path, Path | None]:
    """Archive every extraction, then atomically publish non-empty weekly evidence."""
    run_dir = directory / "runs" / weekly.report_week
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = weekly.collected_at.strftime("%Y%m%dT%H%M%S%f%z")
    archive = run_dir / f"{stamp}.json"
    content = weekly.model_dump_json(indent=2) + "\n"
    with archive.open("x", encoding="utf-8") as file:
        file.write(content)
    if not weekly.facts:
        return archive, None
    destination = directory / f"{weekly.report_week}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".evidence-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return archive, destination
