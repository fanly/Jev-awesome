from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"


class ResourceKind(StrEnum):
    OFFICIAL_DOC = "official_doc"
    SDK = "sdk"
    TUTORIAL = "tutorial"
    APPLICATION = "application"
    EVALUATION = "evaluation"
    RESEARCH = "research"
    ALTERNATIVE = "alternative"
    NEWS = "news"
    OTHER = "other"
    UNRELATED = "unrelated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PrimaryCategory(StrEnum):
    OFFICIAL = "official"
    GETTING_STARTED = "getting_started"
    APPLICATIONS = "applications"
    SDK_INTEGRATIONS = "sdk_integrations"
    EVALS_LIMITS = "evals_limits"
    RESEARCH_ALTS = "research_alts"


class JevRelationship(StrEnum):
    OFFICIAL = "official"
    CALLS_OFFICIAL_API = "calls_official_api"
    COMMUNITY_SDK = "community_sdk"
    INSPIRED_INDEPENDENT = "inspired_independent"
    MENTION_ONLY = "mention_only"
    UNCLEAR = "unclear"
    NOT_RELATED = "not_related"


class OfficialStatus(StrEnum):
    OFFICIAL = "official"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


class EditorialStatus(StrEnum):
    PENDING = "pending"
    PROPOSED = "proposed"
    CURATED = "curated"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class VerificationLevel(StrEnum):
    DISCOVERED = "discovered"
    SOURCE_CHECKED = "source_checked"
    CODE_LOCATED = "code_located"
    REPRODUCED = "reproduced"
    BENCHMARKED = "benchmarked"


class LicenseStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    UNLICENSED = "unlicensed"


class ClassifierMode(StrEnum):
    RULES = "rules"
    AUTO = "auto"
    TYPESAFE = "typesafe"


class FlexibleDate(BaseModel):
    """Date with known precision. Never invent time-of-day."""

    model_config = ConfigDict(extra="forbid")

    value: date | datetime | None = None
    precision: Literal["unknown", "year", "month", "day", "datetime"] = "unknown"
    raw: str | None = None
    source: str | None = None

    @model_validator(mode="after")
    def _consistency(self) -> FlexibleDate:
        if self.value is None and self.precision != "unknown":
            raise ValueError("precision cannot be set when value is None")
        if self.value is not None and self.precision == "unknown":
            raise ValueError("precision must be set when value is present")
        if isinstance(self.value, datetime) and self.value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return self


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    source_type: str
    checked_at: datetime
    supports: str
    excerpt: str | None = None
    code_location: str | None = None
    commit_sha: str | None = None

    @field_validator("checked_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware")
        return v


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str | None = None
    reviewed_at: datetime | None = None
    decision: str | None = None
    reason: str | None = None
    identity_note: str = (
        "reviewer is audit metadata only; not an authorization credential"
    )


class ClassifierSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ClassifierMode
    relevant: bool | None = None
    relevance_probability: float | None = None
    resource_kind: ResourceKind | None = None
    jev_relationship: JevRelationship | None = None
    primary_category: PrimaryCategory | None = None
    priority_score: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    model_name: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Resource(BaseModel):
    """Authoritative catalog entry. Editorial fields are protected from collectors."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    id: str
    resource_kind: ResourceKind
    primary_category: PrimaryCategory | None = None
    tags: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    canonical_url: str
    related_links: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)

    source_identity: str | None = None
    author_or_org: str | None = None
    official_status: OfficialStatus = OfficialStatus.UNKNOWN
    jev_relationship: JevRelationship = JevRelationship.UNCLEAR

    original_title: str
    summary_zh: str | None = None
    summary_en: str | None = None
    developer_value: str | None = None
    jev_role: str | None = None
    prerequisites: str | None = None
    limitations: str | None = None

    published_at: FlexibleDate = Field(default_factory=FlexibleDate)
    first_discovered_at: datetime
    last_material_change_at: datetime | None = None

    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    license_identifier: str | None = None
    license_evidence: str | None = None

    editorial_status: EditorialStatus = EditorialStatus.PENDING
    verification_level: VerificationLevel = VerificationLevel.DISCOVERED
    evidence: list[EvidenceItem] = Field(default_factory=list)
    review_record: ReviewRecord = Field(default_factory=ReviewRecord)

    # Machine suggestions — never overwrite editorial fields above
    suggestion: ClassifierSuggestion | None = None
    content_hash: str | None = None
    github_repo_id: int | None = None
    github_full_name: str | None = None

    @field_validator("first_discovered_at", "last_material_change_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return v

    @model_validator(mode="after")
    def _verification_gates(self) -> Resource:
        if self.verification_level == VerificationLevel.REPRODUCED:
            has_run = any(
                e.code_location or (e.supports and "reproduc" in e.supports.lower())
                for e in self.evidence
            )
            if not has_run:
                raise ValueError(
                    "verification_level=reproduced requires run evidence "
                    "(code_location or supports mentioning reproduction)"
                )
        if self.verification_level == VerificationLevel.BENCHMARKED:
            has_bench = any(
                e.supports and "benchmark" in e.supports.lower() for e in self.evidence
            )
            if not has_bench:
                raise ValueError(
                    "verification_level=benchmarked requires benchmark evidence"
                )
        if self.verification_level == VerificationLevel.CODE_LOCATED:
            if not any(e.code_location for e in self.evidence):
                raise ValueError(
                    "verification_level=code_located requires evidence.code_location"
                )
        return self


class Observation(BaseModel):
    """Machine-observed facts. Safe to refresh from collectors."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str
    observed_at: datetime
    source_id: str
    github_repo_id: int | None = None
    full_name: str | None = None
    stars: int | None = None
    default_branch: str | None = None
    archived: bool | None = None
    latest_release: str | None = None
    content_hash: str | None = None
    link_health: Literal["ok", "redirect", "broken", "unknown"] = "unknown"
    etag: str | None = None
    last_modified: str | None = None
    raw_title: str | None = None
    raw_url: str | None = None
    raw_snippet: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return v


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    decision: Literal["rejected", "merged", "archived", "restored"]
    reason: str
    decided_at: datetime
    content_hash: str | None = None
    merged_into: str | None = None
    actor: str | None = None


class CatalogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_type: Literal[
        "first_discovered",
        "human_accepted",
        "new_version",
        "doc_change",
        "verification_update",
        "withdrawn",
        "archived",
        "suggestion_only",
    ]
    resource_id: str
    occurred_at: datetime
    summary: str
    material: bool = True


class SourceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    status: Literal["success", "failed", "skipped", "degraded"]
    discovered: int = 0
    duplicates: int = 0
    candidates: int = 0
    requests: int = 0
    coverage_gaps: list[str] = Field(default_factory=list)
    error: str | None = None
    time_range: str | None = None


class RunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    mode: str
    classifier: ClassifierMode
    dry_run: bool
    write_local: bool
    sources: list[SourceResult] = Field(default_factory=list)
    model_calls: int = 0
    overall: Literal["success", "degraded", "failed"] = "success"
    notes: list[str] = Field(default_factory=list)


CATEGORY_META: dict[PrimaryCategory, dict[str, str]] = {
    PrimaryCategory.OFFICIAL: {
        "slug": "official",
        "title_zh": "官方与变更",
        "title_en": "Official & Changes",
    },
    PrimaryCategory.GETTING_STARTED: {
        "slug": "getting-started",
        "title_zh": "入门与模式",
        "title_en": "Getting Started & Patterns",
    },
    PrimaryCategory.APPLICATIONS: {
        "slug": "applications",
        "title_zh": "应用与工具",
        "title_en": "Applications & Tools",
    },
    PrimaryCategory.SDK_INTEGRATIONS: {
        "slug": "sdk-integrations",
        "title_zh": "SDK 与集成",
        "title_en": "SDKs & Integrations",
    },
    PrimaryCategory.EVALS_LIMITS: {
        "slug": "evals-limits",
        "title_zh": "评测与限制",
        "title_en": "Evals & Limits",
    },
    PrimaryCategory.RESEARCH_ALTS: {
        "slug": "research-alts",
        "title_zh": "研究与替代实现",
        "title_en": "Research & Alternatives",
    },
}
