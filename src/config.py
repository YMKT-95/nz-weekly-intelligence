"""Project-relative paths and optional API configuration."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    reports_dir: Path
    timezone: ZoneInfo
    research_dir: Path
    research_timeout_seconds: float = 20.0
    llm_api_key: str = field(default="", repr=False)
    llm_model: str = ""
    search_api_key: str = field(default="", repr=False)


def load_settings() -> Settings:
    # Existing shell environment variables take precedence over the local file.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    timezone_name = os.getenv("REPORT_TIMEZONE", "Pacific/Auckland").strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Invalid REPORT_TIMEZONE: {timezone_name!r}") from exc

    try:
        timeout = float(os.getenv("RESEARCH_TIMEOUT_SECONDS", "20"))
    except ValueError as exc:
        raise ValueError("RESEARCH_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("RESEARCH_TIMEOUT_SECONDS must be greater than 0 and at most 120")

    return Settings(
        data_dir=PROJECT_ROOT / "data" / "weekly",
        reports_dir=PROJECT_ROOT / "reports",
        timezone=timezone,
        research_dir=PROJECT_ROOT / "data" / "research",
        research_timeout_seconds=timeout,
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        search_api_key=os.getenv("SEARCH_API_KEY", "").strip(),
    )
