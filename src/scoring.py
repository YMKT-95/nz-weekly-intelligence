"""Provisional evidence-backed components and a strict six-component calculator."""

import hashlib
import json
import os
import re
import tempfile
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from src.analysis import EvidenceFile, Observation, SERIES_FIELDS, _read, _shape

WEIGHTS = {"job_availability": 25, "graduate_availability": 20, "competition": 20,
           "economy": 15, "it_demand": 10, "automation_pressure": 10}
RULE_VERSION = "provisional_v1"
ComponentName = Literal["job_availability", "graduate_availability", "competition", "economy",
                        "it_demand", "automation_pressure"]

# Ordered alternatives: use the first eligible source; never blend publishers or
# apply the monthly mapping to an annual percentage change. All anchors and ages
# are provisional engineering choices, not empirically calibrated cut-offs.
RULES = {
    "job_availability": [
        dict(id="seek_monthly_growth_v1", metric="seek_job_ads_change", source="SEEK NZ",
             basis="month_on_month", adjustment="trend", category="NZ Labour Market",
             method="seek_article_v1", months=1, max_age_days=75, intercept="5", slope="1",
             minimum="-100", maximum=None),
        dict(id="mbie_annual_growth_v1", metric="mbie_job_ads_annual_change", source="MBIE",
             basis="year_on_year", adjustment="unadjusted", category="NZ Labour Market",
             method="mbie_jobs_online_v1", months=3, max_age_days=150, intercept="5", slope="0.25",
             minimum="-100", maximum=None),
    ],
    "competition": [
        dict(id="seek_applications_growth_v1", metric="seek_applications_per_ad_change", source="SEEK NZ",
             basis="month_on_month", adjustment="not_stated", category="NZ Labour Market",
             method="seek_article_v1", months=1, max_age_days=100, intercept="5", slope="-0.5",
             minimum="-100", maximum=None),
    ],
    "economy": [
        dict(id="unemployment_proxy_v1", metric="unemployment_rate", source="Stats NZ",
             basis="level", adjustment="not_stated", category="NZ Labour Market",
             method="stats_indicator_v1", months=3, max_age_days=150, intercept="13.75", slope="-1.25",
             minimum="0", maximum="100"),
    ],
}
LIMITATIONS = {
    "job_availability": "National job-ad growth measures momentum, not vacancy levels or graduate availability. Alternative sources have different coverage and periods.",
    "competition": "National applications-per-ad growth is a momentum proxy, not the competition level for junior IT applicants. Slower growth does not establish fewer applicants.",
    "economy": "Unemployment alone is a narrow economic proxy. CPI, OCR, GDP and other conditions are not represented; lower CPI is not automatically favourable.",
    "graduate_availability": "No supported graduate/junior-specific evidence and scoring rule are implemented.",
    "it_demand": "No supported IT-specific hiring evidence and scoring rule are implemented.",
    "automation_pressure": "No defensible automation-pressure evidence mapping is implemented; AI mentions alone do not establish job displacement.",
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Scores and weights must be numeric, not booleans or numeric strings")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Scores and weights must be finite")
    return number


def calculate_index(scores: dict, weights: dict | None = None) -> float | None:
    """Validate all six inputs; missing components never trigger reweighting."""
    weights = WEIGHTS if weights is None else weights
    if set(scores) != set(WEIGHTS) or set(weights) != set(WEIGHTS):
        raise ValueError("Exactly the six specified components are required")
    numeric_weights = {key: _number(value) for key, value in weights.items()}
    if any(not 0 < value <= 100 for value in numeric_weights.values()) or sum(numeric_weights.values()) != 100:
        raise ValueError("Positive component weights must sum to 100 percent")
    numbers = {key: _number(value) if value is not None else None for key, value in scores.items()}
    if any(value is not None and not 0 <= value <= 10 for value in numbers.values()):
        raise ValueError("Component scores must be between 0 and 10")
    if any(value is None for value in numbers.values()):
        return None
    total = sum(numbers[key] * numeric_weights[key] / 100 for key in numbers)
    return float(total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


class ComponentScore(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: ComponentName
    weight: StrictInt = Field(gt=0, le=100)
    status: Literal["scored", "unavailable"]
    score: StrictFloat | StrictInt | None = Field(default=None, ge=0, le=10)
    rule: dict | None = None
    evidence: list[Observation] = Field(default_factory=list)
    data_age_days: StrictInt | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "scored":
            if self.score is None or not self.rule or not self.evidence or self.data_age_days is None:
                raise ValueError("Scored components require a score, rule, evidence and data age")
        elif self.score is not None or self.rule is not None:
            raise ValueError("Unavailable components cannot contain a score or selected rule")
        return self


class IndexComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    status: Literal["no_history", "unavailable", "incompatible_rules", "incompatible_inputs",
                    "unchanged_evidence", "revised_evidence", "comparable"]
    reason: str
    previous_file: EvidenceFile | None = None
    weeks_apart: int | None = None
    delta: float | None = None

    @model_validator(mode="after")
    def consistent(self):
        if (self.status in {"comparable", "unchanged_evidence"}) != (self.delta is not None):
            raise ValueError("Only comparable indices can contain a delta")
        if self.status == "unchanged_evidence" and self.delta != 0:
            raise ValueError("Unchanged evidence cannot have a nonzero index delta")
        return self


class WeeklyScore(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal[1] = 1
    stage: Literal["scoring"] = "scoring"
    rule_version: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation: Literal["provisional_heuristic"] = "provisional_heuristic"
    current_file: EvidenceFile
    as_of: AwareDatetime
    components: list[ComponentScore] = Field(min_length=6, max_length=6)
    status: Literal["complete", "insufficient_evidence"]
    overall_score: StrictFloat | StrictInt | None = Field(default=None, ge=0, le=10)
    covered_weight_percent: StrictInt = Field(ge=0, le=100)
    comparison: IndexComparison = Field(default_factory=lambda: IndexComparison(
        status="no_history", reason="No earlier scoring result selected."))
    history_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        if {c.name for c in self.components} != set(WEIGHTS):
            raise ValueError("Each component must appear exactly once")
        scores = {c.name: c.score for c in self.components}
        weights = {c.name: c.weight for c in self.components}
        if self.overall_score != calculate_index(scores, weights):
            raise ValueError("Overall score does not match the six weighted components")
        if (self.status == "complete") != (self.overall_score is not None):
            raise ValueError("Completion status does not match index availability")
        if self.covered_weight_percent != sum(c.weight for c in self.components if c.status == "scored"):
            raise ValueError("Coverage does not match available component weights")
        week_start = date.fromisoformat(self.current_file.report_week + "-1")
        if not week_start <= self.as_of.date() <= week_start + timedelta(days=6):
            raise ValueError("Scoring date is outside the labelled evidence week")
        if any(o.fact.retrieved_at > self.as_of for c in self.components for o in c.evidence):
            raise ValueError("Scoring evidence must not come from a later retrieval")
        for component in self.components:
            if component.status == "scored":
                age = max((self.as_of.date() - o.fact.period_end).days for o in component.evidence)
                if component.data_age_days != age:
                    raise ValueError("Recorded data age does not match the evidence period")
        return self


def _policy_hash():
    policy = dict(version=RULE_VERSION, weights=WEIGHTS, rules=RULES, limitations=LIMITATIONS,
                  formula="clamp(intercept+slope*value,0,10)", component_rounding="0.01 HALF_UP",
                  total_rounding="0.1 HALF_UP", missing="require_all_six")
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _matches(fact, rule):
    return (fact.metric == rule["metric"] and fact.source == rule["source"] and fact.unit == "percent"
            and fact.comparison_basis == rule["basis"] and fact.adjustment == rule["adjustment"]
            and fact.category == rule["category"] and fact.extraction_method == rule["method"]
            and fact.geography == "New Zealand" and fact.scope == "all")


def _component(name, weekly):
    issues = []
    reviewed = []
    for rule in RULES.get(name, []):
        candidates = [Observation(pointer=f"/facts/{index}", fact=fact) for index, fact in enumerate(weekly.facts)
                      if _matches(fact, rule)]
        if not candidates:
            issues.append(rule["id"] + ": no accepted evidence with the required source, unit, basis and adjustment.")
            continue
        latest_end = max(o.fact.period_end for o in candidates)
        latest = [o for o in candidates if o.fact.period_end == latest_end]
        reviewed.extend(latest)
        if len({(o.fact.period_start, o.fact.period_end, o.fact.value) for o in latest}) != 1:
            issues.append(rule["id"] + ": conflicting latest observations; no older value substituted.")
            continue
        observation = latest[0]
        fact = observation.fact
        age = (weekly.collected_at.date() - fact.period_end).days
        if age > rule["max_age_days"]:
            issues.append(f"{rule['id']}: data is {age} days past period end, beyond the {rule['max_age_days']}-day limit.")
            continue
        if _shape(fact) != ("months", rule["months"]):
            issues.append(rule["id"] + ": incompatible data-period definition.")
            continue
        value = Decimal(str(fact.value))
        if value < Decimal(rule["minimum"]) or (rule["maximum"] is not None and value > Decimal(rule["maximum"])):
            issues.append(rule["id"] + ": value outside the supported source range.")
            continue
        raw = Decimal(rule["intercept"]) + Decimal(rule["slope"]) * value
        score = float(max(Decimal(0), min(Decimal(10), raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return ComponentScore(name=name, weight=WEIGHTS[name], status="scored", score=score,
                              rule=rule, evidence=[observation], data_age_days=age,
                              reason="Provisional clipped linear mapping of the selected accepted observation; no Phase 4 review flag is used.",
                              limitations=[LIMITATIONS[name], "Formula anchors and age limits are not empirically calibrated."], issues=issues)
    return ComponentScore(name=name, weight=WEIGHTS[name], status="unavailable",
                          reason="Insufficient supported evidence or no implemented scoring rule.",
                          evidence=reviewed, limitations=[LIMITATIONS[name]], issues=issues)


def build_score(current_path: Path) -> WeeklyScore:
    """Score this saved run only; do not fill missing components from past runs."""
    weekly, reference = _read(current_path)
    components = [_component(name, weekly) for name in WEIGHTS]
    overall = calculate_index({c.name: c.score for c in components})
    return WeeklyScore(rule_version=RULE_VERSION, policy_sha256=_policy_hash(), current_file=reference,
                       as_of=weekly.collected_at, components=components, overall_score=overall,
                       status="complete" if overall is not None else "insufficient_evidence",
                       covered_weight_percent=sum(c.weight for c in components if c.status == "scored"))


def compare_scores(current: WeeklyScore, previous: WeeklyScore | None) -> IndexComparison:
    """Only complete, methodologically compatible indices receive a numeric delta."""
    if current.overall_score is None or (previous is not None and previous.overall_score is None):
        return IndexComparison(status="unavailable", reason="Both indices must have all six components; missing scores are not zero.")
    if previous is None:
        return IndexComparison(status="no_history", reason="No usable earlier scoring result.")
    old = {c.name: c for c in previous.components}
    if (current.rule_version != previous.rule_version or current.policy_sha256 != previous.policy_sha256
            or any(c.weight != old[c.name].weight or c.rule != old[c.name].rule for c in current.components)):
        return IndexComparison(status="incompatible_rules", reason="Scoring policy, weights or selected source mapping changed; no index trend inferred.")
    unchanged = True
    revised = False
    for component in current.components:
        now_inputs = component.evidence
        old_inputs = old[component.name].evidence
        if len(now_inputs) != len(old_inputs):
            return IndexComparison(status="incompatible_inputs", reason="Component input coverage changed.")
        for now, before in zip(now_inputs, old_inputs):
            a, b = now.fact, before.fact
            if (any(getattr(a, key) != getattr(b, key) for key in SERIES_FIELDS) or _shape(a) != _shape(b)
                    or a.period_start < b.period_start or a.period_end < b.period_end):
                return IndexComparison(status="incompatible_inputs", reason="Input series definitions changed or current inputs are older.")
            same_period = (a.period_start, a.period_end) == (b.period_start, b.period_end)
            revised |= same_period and a.value != b.value
            unchanged &= same_period and a.value == b.value
    if revised:
        return IndexComparison(status="revised_evidence", reason="At least one input was revised for the same period; no new-period index trend inferred.")
    delta = float(Decimal(str(current.overall_score)) - Decimal(str(previous.overall_score)))
    if unchanged:
        if delta:
            return IndexComparison(status="incompatible_rules", reason="Scores changed despite unchanged inputs; review the scoring policy.")
        return IndexComparison(status="unchanged_evidence", delta=0,
                               reason="Same underlying observations; recollection does not establish a stable labour market.")
    return IndexComparison(status="comparable", delta=delta,
                           reason="Difference between complete provisional indices with compatible methods; not a change in hiring probability.")


def score_evidence(current_path: Path, directory: Path) -> WeeklyScore:
    current = build_score(current_path)
    week_start = date.fromisoformat(current.current_file.report_week + "-1")
    paths = []
    for path in sorted(directory.glob("*.json")):
        if not re.fullmatch(r"\d{4}-W\d{2}", path.stem):
            continue
        try:
            start = date.fromisoformat(path.stem + "-1")
        except ValueError:
            current.history_notes.append(f"Skipped {path.name}: invalid ISO week.")
            continue
        if start < week_start:
            paths.append((start, path))
    previous = None
    reference = None
    for start, path in sorted(paths, reverse=True):
        try:
            raw = path.read_bytes()
            previous = WeeklyScore.model_validate_json(raw)
            if previous.current_file.report_week != path.stem or previous.as_of >= current.as_of:
                raise ValueError("Historical score week or timestamp mismatch")
            reference = EvidenceFile(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), report_week=path.stem)
            break
        except (ValueError, OSError):
            previous = None
            current.history_notes.append(f"Skipped {path.name}: invalid or unreadable scoring result.")
    current.comparison = compare_scores(current, previous)
    if reference:
        current.comparison.previous_file = reference
        current.comparison.weeks_apart = (week_start - date.fromisoformat(reference.report_week + "-1")).days // 7
    else:
        current.history_notes.append("No usable earlier scoring result.")
    return current


def save_score(score: WeeklyScore, directory: Path, run_name: str) -> tuple[Path, Path]:
    """Publish honest incomplete results too, so an old complete index is not reused."""
    score = WeeklyScore.model_validate(score.model_dump())
    if not re.fullmatch(r"[\w+-]+\.json", run_name):
        raise ValueError("Scoring run name must be a JSON filename")
    week = score.current_file.report_week
    run_dir = directory / "runs" / week
    run_dir.mkdir(parents=True, exist_ok=True)
    archive = run_dir / run_name
    content = score.model_dump_json(indent=2) + "\n"
    with archive.open("x", encoding="utf-8") as file:
        file.write(content)
    destination = directory / f"{week}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".score-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return archive, destination
