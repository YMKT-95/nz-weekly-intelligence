"""Minimal validated evidence and weekly data structures."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, computed_field

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


class SourceLink(BaseModel):
    label: str
    url: HttpUrl


class SourceDocument(BaseModel):
    """Retrieved source material, not yet extracted or verified as facts."""

    source_id: NonEmptyText
    source: NonEmptyText
    category: NonEmptyText
    requested_url: HttpUrl
    source_url: HttpUrl
    title: NonEmptyText
    text: NonEmptyText
    retrieved_at: AwareDatetime
    published_at_raw: str | None = None
    updated_at_raw: str | None = None
    collection_method: Literal["html", "embedded_page_json"]
    content_sha256: str
    links: list[SourceLink] = Field(default_factory=list)


class SourceFailure(BaseModel):
    source_id: NonEmptyText
    source: NonEmptyText
    source_url: HttpUrl
    attempted_at: AwareDatetime
    reason: NonEmptyText


class ResearchBatch(BaseModel):
    """A collection snapshot, kept separate from validated weekly evidence."""

    schema_version: Literal[1] = 1
    stage: Literal["research"] = "research"
    report_week: str = Field(pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
    week_start: date
    week_end: date
    started_at: AwareDatetime
    completed_at: AwareDatetime
    documents: list[SourceDocument] = Field(default_factory=list)
    failures: list[SourceFailure] = Field(default_factory=list)

    @computed_field
    @property
    def status(self) -> Literal["complete", "partial", "unavailable"]:
        # "Complete" describes configured collection targets, not the MVP report.
        if not self.documents:
            return "unavailable"
        return "partial" if self.failures else "complete"
