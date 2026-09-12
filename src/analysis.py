"""Compare saved evidence without treating recollection as a new observation."""

import calendar
import hashlib
import os
import re
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models import WeeklyData, WeeklyFact


class EvidenceFile(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_week: str


class Observation(BaseModel):
    """The exact accepted fact and its array location in the referenced file."""

    pointer: str = Field(pattern=r"^/facts/\d+$")
    fact: WeeklyFact


class ComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)

    series: dict[str, str]
    current: list[Observation] = Field(default_factory=list)
    previous: list[Observation] = Field(default_factory=list)
    status: Literal["baseline", "new_series", "missing_current", "unchanged_observation",
                    "revised_observation", "new_observation", "older_observation", "not_comparable"]
    reason: str
    delta: float | None = None
    delta_unit: Literal["percentage_points", "people"] | None = None
    movement: Literal["increased", "decreased", "unchanged"] | None = None
    review_threshold: float | None = None
    review_worthy: bool | None = None


class WeeklyComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    stage: Literal["comparison"] = "comparison"
    rule_version: Literal["comparison_v1"] = "comparison_v1"
    current_file: EvidenceFile
    previous_file: EvidenceFile | None = None
    weeks_apart: int | None = None
    history_notes: list[str] = Field(default_factory=list)
    items: list[ComparisonItem] = Field(default_factory=list)
    labour_direction: Literal["improving", "stable", "deteriorating", "mixed", "insufficient_data"] = "insufficient_data"
    direction_reason: str


# Editable MVP review thresholds in delta units. These are analytical choices,
# not statistical significance tests, scores, or estimates of hiring probability.
REVIEW_RULES = {
    # metric: (publisher, source unit, supported comparisons, delta threshold)
    "unemployment_rate": ("Stats NZ", "percent", {"level"}, 0.2),
    "unemployment_rate_change": ("Stats NZ", "percentage_points", {"quarter_on_quarter"}, 0.2),
    "unemployed_people": ("Stats NZ", "people", {"level"}, 5000),
    "cpi_annual_change": ("Stats NZ", "percent", {"year_on_year"}, 0.5),
    "seek_job_ads_change": ("SEEK NZ", "percent", {"month_on_month", "year_on_year"}, 1.0),
    "seek_applications_per_ad_change": ("SEEK NZ", "percent", {"month_on_month", "year_on_year"}, 1.0),
    "mbie_job_ads_annual_change": ("MBIE", "percent", {"year_on_year"}, 2.0),
}
# Theme and favourable numeric direction. Avoid counting the three Stats NZ
# unemployment measurements as three separate labour-market signals.
LABOUR_SIGNALS = {
    "unemployment_rate": ("unemployment", -1),
    "seek_job_ads_change": ("availability", 1),
    "mbie_job_ads_annual_change": ("availability", 1),
    "seek_applications_per_ad_change": ("competition", -1),
}
SERIES_FIELDS = ("source", "category", "metric", "unit", "comparison_basis", "geography", "scope", "adjustment")


def _read(path: Path) -> tuple[WeeklyData, EvidenceFile]:
    raw = path.read_bytes()
    data = WeeklyData.model_validate_json(raw)
    expected = date.fromisoformat(data.report_week + "-1")
    if data.week_start != expected or data.week_end != expected + timedelta(days=6):
        raise ValueError("Report week and calendar boundaries disagree")
    if not data.week_start <= data.collected_at.date() <= data.week_end:
        raise ValueError("Collection timestamp is outside the labelled report week")
    if any(f.retrieved_at > data.collected_at for f in data.facts):
        raise ValueError("Fact retrieval is after evidence collection")
    return data, EvidenceFile(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                              report_week=data.report_week)


def _history(directory: Path, current: WeeklyData):
    """Select only a canonical earlier week, never a current-week run archive."""
    notes, choices = [], []
    for path in sorted(directory.glob("*.json")):
        if not re.fullmatch(r"\d{4}-W\d{2}", path.stem):
            continue
        try:
            start = date.fromisoformat(path.stem + "-1")
        except ValueError:
            notes.append(f"Skipped {path.name}: invalid ISO week")
            continue
        if start < current.week_start:
            choices.append((start, path))
    for _, path in sorted(choices, reverse=True):
        try:
            previous, reference = _read(path)
            if previous.report_week != path.stem:
                raise ValueError("Filename and report week disagree")
            if not previous.facts:
                raise ValueError("No accepted facts")
            if previous.collected_at >= current.collected_at:
                raise ValueError("Historical evidence was collected after the current run")
            return previous, reference, notes
        except (OSError, ValueError) as exc:
            # Avoid including full validation errors, which can dump source text.
            notes.append(f"Skipped {path.name}: invalid or unreadable weekly evidence ({type(exc).__name__})")
    notes.append("No usable earlier weekly evidence; this run establishes a baseline.")
    return None, None, notes


def _group(data):
    grouped = {}
    for index, fact in enumerate(data.facts if data else []):
        key = tuple(str(getattr(fact, field)) for field in SERIES_FIELDS)
        grouped.setdefault(key, []).append(Observation(pointer=f"/facts/{index}", fact=fact))
    return grouped


def _latest(observations):
    if not observations:
        return [], False
    latest_end = max(o.fact.period_end for o in observations)
    latest = [o for o in observations if o.fact.period_end == latest_end]
    identities = {(o.fact.period_start, o.fact.period_end, o.fact.value) for o in latest}
    return (latest if len(identities) > 1 else latest[:1]), len(identities) > 1


def _shape(fact):
    start, end = fact.period_start, fact.period_end
    if start.day == 1 and end.day == calendar.monthrange(end.year, end.month)[1]:
        return "months", (end.year - start.year) * 12 + end.month - start.month + 1
    return "days", (end - start).days + 1


def _item(key, current, previous, has_history):
    current, current_conflict = _latest(current)
    previous, previous_conflict = _latest(previous)
    item = ComparisonItem(series=dict(zip(SERIES_FIELDS, key)), current=current, previous=previous,
                          status="not_comparable", reason="Conflicting latest observations require review.")
    if current_conflict or previous_conflict:
        return item
    if not has_history:
        item.status, item.reason = "baseline", "No usable previous weekly file; no change is inferred."
        return item
    if not current:
        item.status, item.reason = "missing_current", "No matching current series; missing coverage or changed metadata is not a zero value."
        return item
    if not previous:
        item.status, item.reason = "new_series", "This series was not present in the selected earlier file; this does not establish a new release."
        return item
    now, old = current[0].fact, previous[0].fact
    same_period = (now.period_start, now.period_end) == (old.period_start, old.period_end)
    if same_period:
        if now.value == old.value:
            item.status, item.reason = "unchanged_observation", "The same observation was collected again; no new data-period movement."
            return item
        item.status, item.reason = "revised_observation", "The recorded value for the same period changed; treat as a revision/correction, not new-period movement."
    elif now.period_end < old.period_end and now.period_start < old.period_start:
        item.status, item.reason = "older_observation", "Current coverage contains an older observation; no backwards change is calculated."
        return item
    elif (_shape(now) != _shape(old) or now.period_start <= old.period_start or now.period_end <= old.period_end):
        item.reason = "Data-period definitions are incompatible; no numerical change is calculated."
        return item
    else:
        item.status, item.reason = "new_observation", "A later data period is available; the difference is between recorded periods, not a weekly growth rate."
    delta = Decimal(str(now.value)) - Decimal(str(old.value))
    item.delta = float(delta)
    item.delta_unit = "people" if now.unit == "people" else "percentage_points"
    item.movement = "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
    rule = REVIEW_RULES.get(now.metric)
    if (item.status == "new_observation" and rule and now.source == rule[0]
            and now.unit == rule[1] and now.comparison_basis in rule[2]):
        item.review_threshold = rule[3]
        item.review_worthy = abs(delta) >= Decimal(str(item.review_threshold))
    return item


def _direction(items):
    usable = [item for item in items if item.status == "new_observation"
              and item.series["metric"] in LABOUR_SIGNALS and item.review_worthy is not None]
    themes = {LABOUR_SIGNALS[item.series["metric"]][0] for item in usable}
    if len(themes) < 2:
        return "insufficient_data", "Need new-period observations across at least two labour themes; repeated, missing and revised data do not establish a direction."
    directions = {("improving" if item.delta * LABOUR_SIGNALS[item.series["metric"]][1] > 0 else "deteriorating")
                  for item in usable if item.review_worthy}
    direction = "mixed" if len(directions) > 1 else next(iter(directions), "stable")
    return direction, "Threshold-based interpretation of available national labour signals only; not statistical significance, a graduate outlook, or the Job Search Index."


def compare_evidence(current_path: Path, directory: Path) -> WeeklyComparison:
    """Compare immutable current evidence with the most recent usable earlier week."""
    current, current_reference = _read(current_path)
    previous, previous_reference, notes = _history(directory, current)
    current_groups, previous_groups = _group(current), _group(previous)
    items = [_item(key, current_groups.get(key, []), previous_groups.get(key, []), previous is not None)
             for key in sorted(current_groups.keys() | previous_groups.keys())]
    direction, reason = _direction(items)
    return WeeklyComparison(current_file=current_reference, previous_file=previous_reference,
                            weeks_apart=(current.week_start - previous.week_start).days // 7 if previous else None,
                            history_notes=notes, items=items, labour_direction=direction, direction_reason=reason)


def save_comparison(comparison: WeeklyComparison, directory: Path, run_name: str) -> tuple[Path, Path]:
    """Archive the comparison for an evidence run, then replace the weekly view."""
    if not re.fullmatch(r"[\w+-]+\.json", run_name):
        raise ValueError("Comparison run name must be a JSON filename")
    week = comparison.current_file.report_week
    date.fromisoformat(week + "-1")
    run_dir = directory / "runs" / week
    run_dir.mkdir(parents=True, exist_ok=True)
    archive = run_dir / run_name
    content = comparison.model_dump_json(indent=2) + "\n"
    with archive.open("x", encoding="utf-8") as file:
        file.write(content)
    destination = directory / f"{week}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".comparison-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return archive, destination
