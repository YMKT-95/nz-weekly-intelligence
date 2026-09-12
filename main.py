"""Local entry point for the NZ graduate weekly intelligence script."""

import logging
from datetime import datetime, timedelta

from src.config import load_settings
from src.extraction import extract_evidence, save_evidence
from src.research import collect_research, save_research
from src.analysis import compare_evidence, save_comparison
from src.scoring import score_evidence, save_score
from src.reporting import build_report, save_report

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.info("Starting weekly intelligence script (Phase 6 evidence-led report)")

    try:
        settings = load_settings()
        now = datetime.now(settings.timezone)
        week_start = now.date() - timedelta(days=now.weekday())
        iso_year, iso_week, _ = week_start.isocalendar()
        report_week = f"{iso_year}-W{iso_week:02d}"
        week_end = week_start + timedelta(days=6)

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        logger.error("Could not initialise the project: %s", exc)
        return 1

    logger.info("Report week: %s", report_week)
    logger.info("Report period: %s -> %s", week_start, week_end)
    logger.info("Run time: %s (%s)", now.isoformat(timespec="seconds"), settings.timezone)
    logger.info("Weekly data directory: %s", settings.data_dir)
    logger.info("Report directory: %s", settings.reports_dir)
    batch = collect_research(settings, report_week, week_start, week_end)
    try:
        destination = save_research(batch, settings.research_dir)
    except OSError as exc:
        logger.error("Could not save research: %s", exc)
        return 1
    logger.info("Research %s: %d documents, %d unavailable targets, %d deferred targets",
                batch.status, len(batch.documents),
                sum(failure.kind == "unavailable" for failure in batch.failures),
                sum(failure.kind == "deferred" for failure in batch.failures))
    logger.info("Research saved: %s", destination)
    try:
        weekly = extract_evidence(destination)
        archive, evidence_path = save_evidence(weekly, settings.data_dir)
    except (OSError, ValueError) as exc:
        logger.error("Could not extract or save evidence: %s", exc)
        return 1
    logger.info("Validated %d facts; rejected %d candidates; skipped %d source documents",
                len(weekly.facts), len(weekly.rejected), len(weekly.skipped))
    logger.info("Extraction audit saved: %s", archive)
    for issue in weekly.rejected:
        logger.warning("%s: %s", issue.source_id, issue.reason)
    if evidence_path is None:
        logger.error("No validated facts. Existing weekly evidence was preserved.")
        return 1
    logger.info("Weekly evidence saved: %s", evidence_path)
    try:
        comparison = compare_evidence(archive, settings.data_dir)
        comparison_archive, comparison_path = save_comparison(comparison, settings.data_dir / "comparisons", archive.name)
    except (OSError, ValueError) as exc:
        logger.error("Evidence saved, but comparison failed: %s", exc)
        return 1
    for note in comparison.history_notes:
        logger.info("History: %s", note)
    logger.info("Comparison saved: %s", comparison_path)
    logger.info("Changes flagged for review: %d; national labour direction: %s",
                sum(item.review_worthy is True for item in comparison.items), comparison.labour_direction)
    try:
        score = score_evidence(archive, settings.data_dir / "scores")
        score_archive, score_path = save_score(score, settings.data_dir / "scores", archive.name)
    except (OSError, ValueError) as exc:
        logger.error("Evidence and comparison saved, but scoring failed: %s", exc)
        return 1
    logger.info("Scoring saved: %s", score_path)
    if score.overall_score is None:
        logger.info("Index unavailable: insufficient evidence for all six components (%d%% of component weight covered, not a confidence estimate).",
                    score.covered_weight_percent)
    else:
        logger.info("Provisional Job Search Index: %.1f / 10", score.overall_score)
    try:
        report = build_report(archive, comparison_archive, score_archive, settings)
        _, report_path = save_report(report, settings.reports_dir)
    except (OSError, ValueError) as exc:
        logger.error("Evidence, comparison and scoring saved, but report failed: %s", exc)
        return 1
    logger.info("Weekly Markdown report saved: %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
