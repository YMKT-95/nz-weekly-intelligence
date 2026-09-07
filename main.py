"""Local entry point for the NZ graduate weekly intelligence script."""

import logging
from datetime import datetime, timedelta

from src.config import load_settings
from src.models import WeeklyData

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logger.info("Starting weekly intelligence script (Phase 1 foundation)")

    try:
        settings = load_settings()
        now = datetime.now(settings.timezone)
        week_start = now.date() - timedelta(days=now.weekday())
        iso_year, iso_week, _ = week_start.isocalendar()
        weekly_data = WeeklyData(
            report_week=f"{iso_year}-W{iso_week:02d}",
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            collected_at=now,
        )

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        logger.error("Could not initialise the project: %s", exc)
        return 1

    logger.info("Report week: %s", weekly_data.report_week)
    logger.info("Report period: %s -> %s", weekly_data.week_start, weekly_data.week_end)
    logger.info("Run time: %s (%s)", now.isoformat(timespec="seconds"), settings.timezone)
    logger.info("Weekly data directory: %s", settings.data_dir)
    logger.info("Report directory: %s", settings.reports_dir)
    logger.info("Foundation ready. Research and report generation are not yet connected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
