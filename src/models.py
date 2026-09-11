"""Minimal validated evidence and weekly data structures."""

from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, JsonValue,
    StrictFloat, StrictInt, computed_field, model_validator,
)

NonEmptyText = Annotated[str, Field(min_length=1)]


class EvidenceReference(BaseModel):
    """Location and exact supporting fields in a saved research snapshot."""

    model_config = ConfigDict(extra="forbid")

    snapshot_file: NonEmptyText
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: NonEmptyText
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    json_pointer: str = Field(pattern=r"^/PageBlocks/\d+/Value[2-6]?$")
    raw_fields: dict[str, JsonValue]


class TextSpan(BaseModel):
    """Exact Unicode character offsets into a SourceDocument's saved text."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["statement", "section", "report_heading", "report_period", "lag", "methodology", "source_date"]
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    quote: NonEmptyText

    @model_validator(mode="after")
    def check_length(self):
        if self.end - self.start != len(self.quote):
            raise ValueError("Text span length must match its exact quotation")
        return self


class TextEvidenceReference(BaseModel):
    """Supporting passages in saved article text, including necessary context."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    snapshot_file: NonEmptyText
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: NonEmptyText
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    spans: list[TextSpan] = Field(min_length=1)


class WeeklyFact(BaseModel):
    """A supported numerical observation; source matching is checked separately."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )

    category: NonEmptyText
    metric: NonEmptyText
    value: StrictInt | StrictFloat
    unit: Literal["percent", "percentage_points", "people"]
    comparison_basis: Literal["level", "month_on_month", "quarter_on_quarter", "year_on_year"]
    period: NonEmptyText
    period_start: date
    period_end: date
    geography: Literal["New Zealand"] = "New Zealand"
    scope: Literal["all"] = "all"
    adjustment: Literal["not_stated", "trend", "seasonally_adjusted", "unadjusted"] = "not_stated"
    source: NonEmptyText
    source_url: HttpUrl
    publication_date: date | None = None
    source_updated_date: date | None = None
    retrieved_at: AwareDatetime
    confidence: Literal["high"] = "high"
    confidence_reason: NonEmptyText
    extraction_method: Literal["stats_indicator_v1", "seek_article_v1", "mbie_jobs_online_v1"] = "stats_indicator_v1"
    evidence: EvidenceReference | TextEvidenceReference

    @model_validator(mode="after")
    def check_dates(self):
        if (self.extraction_method != "stats_indicator_v1") != isinstance(self.evidence, TextEvidenceReference):
            raise ValueError("Evidence reference type must match the extraction method")
        if self.period_start > self.period_end:
            raise ValueError("Data period start must not follow its end")
        for value in (self.period_end, self.publication_date, self.source_updated_date):
            if value is not None and value > self.retrieved_at.date():
                raise ValueError("Observed data and release dates must not be in the future")
        return self


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
    structured_data: dict[str, JsonValue] | None = None
    structured_sha256: str | None = None


class SourceFailure(BaseModel):
    source_id: NonEmptyText
    source: NonEmptyText
    source_url: HttpUrl
    attempted_at: AwareDatetime
    reason: NonEmptyText
    kind: Literal["unavailable", "deferred"] = "unavailable"


class ResearchBatch(BaseModel):
    """A collection snapshot, kept separate from validated weekly evidence."""

    schema_version: Literal[1, 2] = 2
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


class ExtractionIssue(BaseModel):
    source_id: NonEmptyText
    reason: NonEmptyText
    json_pointer: str | None = None
    raw_fields: dict[str, JsonValue] = Field(default_factory=dict)
    text_spans: list[TextSpan] = Field(default_factory=list)


class WeeklyData(BaseModel):
    """Accepted facts and a separate audit of rejected or unprocessed evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2, 3] = 3
    stage: Literal["evidence"] = "evidence"
    report_week: str = Field(pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
    week_start: date
    week_end: date
    collected_at: AwareDatetime
    research_snapshot: NonEmptyText
    research_status: Literal["complete", "partial", "unavailable"]
    facts: list[WeeklyFact] = Field(default_factory=list)
    rejected: list[ExtractionIssue] = Field(default_factory=list)
    skipped: list[ExtractionIssue] = Field(default_factory=list)
    collection_failures: list[SourceFailure] = Field(default_factory=list)
