from __future__ import annotations

import re
from dataclasses import dataclass

from jev_awesome.dates import utc_now
from jev_awesome.models import (
    ClassifierMode,
    ClassifierSuggestion,
    JevRelationship,
    OfficialStatus,
    PrimaryCategory,
    Resource,
    ResourceKind,
)

OFFICIAL_HOSTS = {
    "typesafe.ai",
    "docs.typesafe.ai",
    "github.com/typesafe-ai",
}

POSITIVE_PATTERNS = [
    re.compile(r"\bjev\b", re.I),
    re.compile(r"typesafe\.ai", re.I),
    re.compile(r"typesafe[-_ ]?sdk", re.I),
    re.compile(r"@typesafe-ai", re.I),
    re.compile(r"system\s+one", re.I),
]

NEGATIVE_PATTERNS = [
    re.compile(r"\bjava\b.*\bevent\b", re.I),
    # generic "type safe" without typesafe product signals
]


@dataclass
class RulesClassifier:
    mode: ClassifierMode = ClassifierMode.RULES

    def classify(self, resource: Resource) -> ClassifierSuggestion:
        blob = " ".join(
            filter(
                None,
                [
                    resource.original_title,
                    resource.summary_en,
                    resource.summary_zh,
                    resource.canonical_url,
                    " ".join(resource.tags),
                    resource.github_full_name or "",
                ],
            )
        )
        reason_codes: list[str] = []
        positive = sum(1 for p in POSITIVE_PATTERNS if p.search(blob))
        relevant = positive > 0

        kind = ResourceKind.OTHER
        relationship = JevRelationship.UNCLEAR
        category: PrimaryCategory | None = None

        url = resource.canonical_url.lower()
        is_official = any(h in url for h in ("docs.typesafe.ai", "typesafe.ai")) or (
            resource.github_full_name or ""
        ).lower().startswith("typesafe-ai/")

        if is_official:
            reason_codes.append("official_domain")
            relationship = JevRelationship.OFFICIAL
            kind = ResourceKind.OFFICIAL_DOC if "docs.typesafe.ai" in url else ResourceKind.SDK
            if "sdk" in blob.lower():
                kind = ResourceKind.SDK
                category = PrimaryCategory.SDK_INTEGRATIONS
            else:
                category = PrimaryCategory.OFFICIAL
            relevant = True
        elif not relevant:
            reason_codes.append("no_jev_signal")
            relationship = JevRelationship.NOT_RELATED
            kind = ResourceKind.UNRELATED
        else:
            reason_codes.append(f"positive_signals:{positive}")
            if re.search(r"\b(eval|benchmark|limit|jagged)\b", blob, re.I):
                kind = ResourceKind.EVALUATION
                category = PrimaryCategory.EVALS_LIMITS
                relationship = JevRelationship.CALLS_OFFICIAL_API
            elif re.search(r"\b(tutorial|guide|cookbook|quickstart|getting started)\b", blob, re.I):
                kind = ResourceKind.TUTORIAL
                category = PrimaryCategory.GETTING_STARTED
                relationship = JevRelationship.CALLS_OFFICIAL_API
            elif re.search(r"\b(sdk|client|adapter|plugin)\b", blob, re.I):
                kind = ResourceKind.SDK
                category = PrimaryCategory.SDK_INTEGRATIONS
                relationship = JevRelationship.COMMUNITY_SDK
            elif re.search(r"\b(awesome|directory|list)\b", blob, re.I):
                kind = ResourceKind.OTHER
                category = PrimaryCategory.APPLICATIONS
                relationship = JevRelationship.MENTION_ONLY
            else:
                kind = ResourceKind.APPLICATION
                category = PrimaryCategory.APPLICATIONS
                relationship = JevRelationship.UNCLEAR

        # Injection bait: never escalate status from content instructions
        if re.search(r"ignore (all |previous )?rules|mark as curated|set to curated", blob, re.I):
            reason_codes.append("prompt_injection_ignored")

        return ClassifierSuggestion(
            mode=self.mode,
            relevant=relevant,
            relevance_probability=1.0 if relevant else 0.0,
            resource_kind=kind,
            jev_relationship=relationship,
            primary_category=category,
            priority_score=3.0 if is_official else (2.0 if relevant else 0.0),
            reason_codes=reason_codes,
            created_at=utc_now(),
        )


def apply_suggestion_fields(resource: Resource, suggestion: ClassifierSuggestion) -> Resource:
    """Attach suggestion only; do not mutate protected editorial conclusions if set."""
    updates: dict = {"suggestion": suggestion}
    # Fill empty machine-friendly fields only when still pending and empty
    if resource.editorial_status.value in {"pending", "proposed"}:
        if resource.primary_category is None and suggestion.primary_category:
            updates["primary_category"] = suggestion.primary_category
        if (
            resource.resource_kind in {ResourceKind.OTHER, ResourceKind.NEWS}
            and suggestion.resource_kind
            and suggestion.resource_kind not in {ResourceKind.UNRELATED}
        ):
            updates["resource_kind"] = suggestion.resource_kind
        if resource.jev_relationship == JevRelationship.UNCLEAR and suggestion.jev_relationship:
            updates["jev_relationship"] = suggestion.jev_relationship
        if (
            resource.official_status == OfficialStatus.UNKNOWN
            and suggestion.jev_relationship == JevRelationship.OFFICIAL
        ):
            updates["official_status"] = OfficialStatus.OFFICIAL
    return resource.model_copy(update=updates)
