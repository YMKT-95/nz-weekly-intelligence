"""Render bounded, evidence-led Markdown without an external writing service."""

import hashlib
import html
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote

from src.analysis import WeeklyComparison, _read
from src.scoring import WeeklyScore
from src.config import Settings
from src.narration import narrate

logger = logging.getLogger(__name__)

METRICS = {
    "unemployment_rate": "Unemployment rate",
    "unemployment_rate_change": "Change in unemployment rate",
    "unemployed_people": "Unemployed people",
    "cpi_annual_change": "CPI annual change",
    "seek_job_ads_change": "SEEK national job-ad change",
    "seek_applications_per_ad_change": "SEEK national applications-per-ad change",
    "mbie_job_ads_annual_change": "MBIE national job-ad annual change",
}
LABOUR_METRICS = {"seek_job_ads_change", "seek_applications_per_ad_change", "mbie_job_ads_annual_change"}
ECONOMY_METRICS = set(METRICS) - LABOUR_METRICS
STATUSES = {
    "baseline": "Baseline; no earlier evidence for comparison",
    "new_series": "Newly covered series; not necessarily newly published",
    "missing_current": "Missing from this run; not zero",
    "unchanged_observation": "Same observation collected again; not evidence of a stable market",
    "revised_observation": "Same-period revision/correction; not new-period movement",
    "new_observation": "Later comparable data period; not necessarily released this week",
    "older_observation": "Older data period; no forward change calculated",
    "not_comparable": "Not comparable",
}


def _text(value) -> str:
    """Keep source-derived labels/diagnostics as text, not Markdown or HTML."""
    value = html.escape(" ".join(str(value).split()), quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+|>])", r"\\\1", value)


def _link(label, url) -> str:
    return f"[{_text(label)}](<{quote(str(url), safe=':/?#@!$&=;+,%')}>)"


def _number(value, signed=False) -> str:
    return format(value, "+,.10g" if signed else ",.10g")


def _value(fact) -> str:
    number = _number(fact.value, signed=fact.comparison_basis != "level")
    unit = {"percent": "%", "percentage_points": " percentage points", "people": " people"}[fact.unit]
    return number + unit


def _fact(index, fact) -> str:
    basis = fact.comparison_basis.replace("_", "-")
    adjustment = fact.adjustment.replace("_", " ")
    return (f"- **{_text(METRICS.get(fact.metric, fact.metric))}: {_value(fact)}** "
            f"({basis}; {_text(fact.period)}, {fact.period_start} to {fact.period_end}; "
            f"adjustment: {adjustment}). [F{index}]\n")


def _check_observations(observations, data):
    for observation in observations:
        index = int(observation.pointer.rsplit("/", 1)[1])
        if data is None or index >= len(data.facts) or observation.fact != data.facts[index]:
            raise ValueError("Report observation does not match its referenced evidence")


@dataclass(frozen=True)
class MarkdownReport:
    report_week: str
    run_name: str
    content: str
    narration: dict = field(default_factory=dict)


def build_report(evidence_path: Path, comparison_path: Path, score_path: Path,
                 settings: Settings | None = None) -> MarkdownReport:
    """Read saved stage outputs and reject mixed runs or mismatched fact pointers.

    These are trusted local pipeline outputs, not arbitrary source documents.
    This boundary checks provenance; it does not repeat extraction or recalibrate
    the comparison/scoring policies.
    """
    weekly, reference = _read(evidence_path)
    if not weekly.facts:
        raise ValueError("Cannot report without accepted evidence")
    comparison_raw, score_raw = comparison_path.read_bytes(), score_path.read_bytes()
    comparison = WeeklyComparison.model_validate_json(comparison_raw)
    score = WeeklyScore.model_validate_json(score_raw)
    if comparison.current_file != reference or score.current_file != reference:
        raise ValueError("Report inputs must reference the same evidence run and checksum")
    if score.as_of != weekly.collected_at:
        raise ValueError("Report score timestamp does not match evidence collection")
    previous = None
    if comparison.previous_file:
        previous, previous_ref = _read(Path(comparison.previous_file.path))
        if previous_ref != comparison.previous_file:
            raise ValueError("Historical evidence changed after comparison")
    for item in comparison.items:
        _check_observations(item.current, weekly)
        _check_observations(item.previous, previous)
    for component in score.components:
        _check_observations(component.evidence, weekly)
    previous_score = None
    if score.comparison.previous_file:
        prior_ref = score.comparison.previous_file
        prior_raw = Path(prior_ref.path).read_bytes()
        previous_score = WeeklyScore.model_validate_json(prior_raw)
        if (hashlib.sha256(prior_raw).hexdigest() != prior_ref.sha256
                or previous_score.current_file.report_week != prior_ref.report_week):
            raise ValueError("Historical scoring changed after comparison")
    narration = narrate(settings, weekly, comparison, score)
    logger.info("Report narration: %s", narration.reason)

    lines = ["# 🇳🇿 NZ Economy & IT Graduate Weekly Intelligence Report\n",
             f"**Week: {weekly.week_start:%d %B %Y}–{weekly.week_end:%d %B %Y} ({weekly.report_week})**\n",
             f"Evidence as of: {weekly.collected_at.isoformat(timespec='seconds')}. "
             f"{_text(narration.reason)} The week label is a collection window, not a release date.\n",
             "## Executive Summary\n",
             f"- Accepted numerical observations: {len(weekly.facts)}; "
             f"rejected candidates: {len(weekly.rejected)}; unavailable/deferred targets: {len(weekly.collection_failures)}. "
             "Coverage is limited to the evidence listed below.\n",
             "- National indicators provide context; they do not directly measure IT graduate hiring prospects.\n",
             f"- Overall index: {'unavailable — insufficient evidence for all six components' if score.overall_score is None else f'{score.overall_score:.1f} / 10 (provisional heuristic)'}.\n",
             "- Older observation periods remain explicit. Recollection does not establish new developments this week.\n",
             "## 🇳🇿 NZ Economy\n", "### Key Indicators\n"]
    economy = [(i, f) for i, f in enumerate(weekly.facts, 1) if f.metric in ECONOMY_METRICS]
    lines.extend(_fact(i, f) for i, f in economy)
    if not economy:
        lines.append("No supported economic indicators in this run.\n")
    lines.append("### What Changed\n")
    if comparison.previous_file:
        lines.append(f"Compared with saved evidence for {comparison.previous_file.report_week} "
                     f"({comparison.weeks_apart} week(s) apart). Differences below concern data periods, not weekly growth.\n")
    else:
        lines.append("No usable earlier weekly evidence: this is a baseline, and week-to-week change is unavailable.\n")
    for item in comparison.items:
        if item.status == "baseline":
            continue  # The baseline paragraph already covers every unchanged lack of history.
        label = METRICS.get(item.series.get("metric"), item.series.get("metric", "Unknown series"))
        links = " ".join(f"[F{int(o.pointer.rsplit('/', 1)[1]) + 1}]" for o in item.current)
        detail = ""
        if item.previous:
            old = item.previous[0].fact
            detail += (f" Earlier: {_value(old)} ({_text(old.period)}; {old.period_start} to {old.period_end}), "
                       f"{_link(old.source, old.source_url)}.")
        if item.delta is not None:
            unit = (item.delta_unit or "").replace("_", " ")
            detail += f" Recorded difference: {_number(item.delta, signed=True)} {unit}."
        if item.review_worthy is not None and item.review_threshold is not None:
            detail += (f" {'Flagged for review' if item.review_worthy else 'Below review threshold'} "
                       f"(threshold: {_number(item.review_threshold)} {(item.delta_unit or '').replace('_', ' ')}).")
        lines.append(f"- **{_text(label)}**: {STATUSES[item.status]}. {links}{detail} {_text(item.reason)}\n")
    lines.append("Review thresholds are heuristic review aids, not statistical significance tests.\n")
    lines.extend(["## 💼 NZ Labour Market\n",
                  f"**Interpretation — national labour direction: {comparison.labour_direction.replace('_', ' ')}.** "
                  f"{_text(comparison.direction_reason)}\n"])
    labour = [(i, f) for i, f in enumerate(weekly.facts, 1) if f.metric in LABOUR_METRICS]
    lines.extend(_fact(i, f) for i, f in labour)
    if not labour:
        lines.append("No supported job-ad or applications-per-ad observations in this run.\n")
    other = [(i, f) for i, f in enumerate(weekly.facts, 1) if f.metric not in METRICS]
    if other:
        lines.append("### Other accepted observations (unmapped)\n")
        lines.extend(_fact(i, f) for i, f in other)
    lines.extend(["## 💻 NZ IT Graduate Job Market\n", "### Current Job-Market Signals\n",
                  "The national observations above are broad context. IT-specific demand and vacancy coverage are unavailable.\n",
                  "### Graduate / Entry-Level Situation\n",
                  "No supported graduate or entry-level vacancy evidence in this run. National job-ad or competition changes "
                  "cannot establish graduate availability, experience requirements, or an individual's chance of employment.\n",
                  "## 🌎 Global Context\n", "No supported international evidence in this run; this does not mean no relevant developments occurred.\n",
                  "## 📈 NZX / Business Signals\n", "No supported NZX or business-event evidence in this run.\n",
                  "## 🎯 Personal Job Search Index\n"])
    lines.append("**Unavailable — insufficient evidence for all six components.**\n" if score.overall_score is None
                 else f"**{score.overall_score:.1f} / 10 — provisional heuristic.**\n")
    lines.append(f"Scored component weight: {score.covered_weight_percent}%. This is not confidence, "
                 "a partial index, or a hiring probability. Missing components are not filled or reweighted.\n")
    if score.comparison.previous_file:
        lines.append(f"Earlier scoring record: {score.comparison.previous_file.report_week} "
                     f"({score.comparison.weeks_apart} week(s) apart).\n")
    earlier_value = (f"{previous_score.overall_score:.1f} / 10 (provisional)"
                     if previous_score and previous_score.overall_score is not None else "unavailable")
    lines.append(f"Earlier index: {earlier_value}.\n")
    if score.comparison.status == "comparable":
        lines.append(f"Index change: {_number(score.comparison.delta, signed=True)} points across comparable data periods.\n")
    elif score.comparison.status == "unchanged_evidence":
        lines.append("Index unchanged because the same observations were collected again; this is not a stable-market conclusion.\n")
    else:
        lines.append("Index trend: unavailable.\n")
    lines.extend([f"{_text(score.comparison.reason)}\n", "### Why\n"])
    for component in score.components:
        value = "unavailable" if component.score is None else f"{_number(component.score)} / 10 (provisional)"
        support = " ".join(f"[F{int(o.pointer.rsplit('/', 1)[1]) + 1}]" for o in component.evidence)
        age = f" Data age: {component.data_age_days} days from period end." if component.status == "scored" else ""
        label = "IT demand" if component.name == "it_demand" else component.name.replace('_', ' ').capitalize()
        lines.append(f"- **{label} ({component.weight}%): {value}.** "
                     f"{_text(component.reason)} {support}{age} "
                     f"Limitations: {_text(' '.join(component.limitations))} "
                     f"{_text(' '.join(component.issues))}\n")
    if narration.insights:
        lines.extend(["### LLM Interpretation — Review Required\n",
                      "These notes are generated interpretation, not validated facts. References identify supplied evidence; "
                      "automated checks do not prove that it supports every claim. Review the sources before relying on the prose.\n"])
        for insight in narration.insights:
            links = " ".join(f"[{fact_id}]" for fact_id in insight.fact_ids)
            lines.append(f"- {_text(insight.text)} {links}\n")
    lines.extend(["## 🎓 What This Means for an IT Graduate\n",
                  "**Interpretation:** these observations can inform questions about the wider market. "
                  "They do not establish which roles you can obtain or predict your employment outcome. "
                  "Use vacancy requirements and your own application results to judge your situation.\n",
                  "## ✅ Recommended Actions\n",
                  "General process suggestions, not conclusions inferred from unavailable graduate data:\n",
                  "1. Check current graduate and entry-level vacancies directly; record dates, location, skills, and experience requirements.\n",
                  "2. Track applications, responses, and interviews to build evidence about your own search.\n",
                  "3. Read the linked sources and their data periods before changing your job-search approach.\n",
                  "## Evidence Coverage and Sources\n",
                  "Facts above are accepted extraction results, not independent verification of publisher accuracy. "
                  "Publication, page update, retrieval, and observation dates have different meanings.\n"])
    for i, fact in enumerate(weekly.facts, 1):
        lines.append(f"- **F{i}** — {_link(fact.source, fact.source_url)}; "
                     f"publication: {fact.publication_date or 'unknown'}; page updated: {fact.source_updated_date or 'unknown'}; "
                     f"retrieved: {fact.retrieved_at.isoformat(timespec='seconds')}; evidence pointer: `/facts/{i - 1}`.\n")
    for failure in weekly.collection_failures:
        lines.append(f"- **{_text(failure.source)} — {failure.kind}:** {_text(failure.reason)}\n")
    for kind, issues in (("Rejected candidate", weekly.rejected), ("Skipped source document", weekly.skipped)):
        for issue in issues:
            lines.append(f"- **{kind} ({_text(issue.source_id)}):** {_text(issue.reason)}\n")
    for note in comparison.history_notes + score.history_notes:
        lines.append(f"- History note: {_text(note)}\n")
    lines.extend(["### Run provenance\n",
                  f"Report renderer: `template_v1`. Narration: {_text(narration.status)}. "
                  f"Model: {_text(narration.model or 'none')}. Evidence run: {_text(evidence_path.name)}. "
                  f"Comparison policy: {comparison.rule_version}. Scoring policy: {_text(score.rule_version)}.\n",
                  f"- Evidence SHA-256: `{reference.sha256}`\n",
                  f"- Comparison SHA-256: `{hashlib.sha256(comparison_raw).hexdigest()}`\n",
                  f"- Scoring SHA-256: `{hashlib.sha256(score_raw).hexdigest()}`\n",
                  f"- Scoring policy SHA-256: `{score.policy_sha256}`\n"])
    # Reference-style links keep every displayed current fact adjacent to its source.
    lines.extend(f"[F{i}]: <{quote(str(f.source_url), safe=':/?#@!$&=;+,%')}>\n"
                 for i, f in enumerate(weekly.facts, 1))
    return MarkdownReport(weekly.report_week, evidence_path.stem + ".md", "\n".join(lines), narration.audit())


def save_report(report: MarkdownReport, directory: Path) -> tuple[Path, Path]:
    """Preserve each report and atomically replace the week's latest report."""
    if not re.fullmatch(r"\d{4}-W\d{2}", report.report_week):
        raise ValueError("Report requires an ISO week")
    date.fromisoformat(report.report_week + "-1")
    if not re.fullmatch(r"[\w+-]+\.md", report.run_name):
        raise ValueError("Report run name must be a Markdown filename")
    if not report.content.strip():
        raise ValueError("Cannot save an empty report")
    run_dir = directory / "runs" / report.report_week
    run_dir.mkdir(parents=True, exist_ok=True)
    archive = run_dir / report.run_name
    with archive.open("x", encoding="utf-8") as file:
        file.write(report.content)
    with archive.with_suffix(".json").open("x", encoding="utf-8") as file:
        json.dump(dict(report_week=report.report_week, report_sha256=hashlib.sha256(report.content.encode()).hexdigest(),
                       narration=report.narration), file, indent=2)
        file.write("\n")
    destination = directory / f"{report.report_week}.md"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".report-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(report.content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return archive, destination
