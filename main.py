"""Local entry point for the NZ graduate weekly intelligence script."""

import logging
from datetime import datetime, timedelta

from src.config import load_settings
from src.extraction import extract_evidence, save_evidence
from src.research import collect_research, save_research

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.info("Starting weekly intelligence script (Phase 3 evidence extraction)")

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
    logger.info("Evidence extraction complete. Comparison, scoring, and reports are not yet connected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
