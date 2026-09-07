"""Minimal validated evidence and weekly data structures."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

NonEmptyText = Annotated[str, Field(min_length=1)]


class WeeklyFact(BaseModel):
    """A numerical observation or qualitative statement with its provenance.

    Numeric observations use a float value; qualitative facts use text.
    Validation checks structure, not whether a source actually supports a claim.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )

    category: NonEmptyText
    metric: NonEmptyText
    value: float | NonEmptyText
    unit: NonEmptyText | None = None
    period: NonEmptyText
    source: NonEmptyText
    source_url: HttpUrl
    publication_date: date | None = None
    retrieved_at: AwareDatetime
    confidence: Literal["high", "medium", "low"]


class WeeklyData(BaseModel):
    """Container for evidence gathered during one report week."""

    model_config = ConfigDict(extra="forbid")

    report_week: str = Field(pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
    week_start: date
    week_end: date
    collected_at: AwareDatetime
    facts: list[WeeklyFact] = Field(default_factory=list)
