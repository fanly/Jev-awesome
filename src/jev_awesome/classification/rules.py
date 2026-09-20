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

# Strong product / SDK signals (prefer these over bare name matches)
STRONG_PATTERNS = [
    re.compile(r"typesafe\.ai", re.I),
    re.compile(r"api\.typesafe\.ai", re.I),
    re.compile(r"TYPESAFE_API_KEY"),
    re.compile(r"@typesafe-ai/sdk", re.I),
    re.compile(r"typesafe[-_ ]?sdk", re.I),
    re.compile(r"jev-latest", re.I),
    re.compile(r"system\s+one", re.I),
    re.compile(r"\bsystem_one\b", re.I),
    re.compile(r"@typesafe-ai", re.I),
]

POSITIVE_PATTERNS = [
    re.compile(r"\bjev\b", re.I),
    *STRONG_PATTERNS,
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
        strong_hits = sum(1 for p in STRONG_PATTERNS if p.search(blob))
        positive = sum(1 for p in POSITIVE_PATTERNS if p.search(blob))
        name_only_jev = bool(re.search(r"\bjev\b", blob, re.I)) and strong_hits == 0
        relevant = positive > 0

        kind = ResourceKind.OTHER
        relationship = JevRelationship.UNCLEAR
        category: PrimaryCategory | None = None
        priority = 0.0

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
            priority = 3.0
        elif strong_hits > 0:
            reason_codes.append(f"strong_signals:{strong_hits}")
            relevant = True
            priority = 2.5
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
                priority = 1.5
            else:
                kind = ResourceKind.APPLICATION
                category = PrimaryCategory.APPLICATIONS
                relationship = JevRelationship.CALLS_OFFICIAL_API
        elif name_only_jev:
            # Weak: name-only jev without TypeSafe product signals → low priority / not high radar
            reason_codes.append("weak_name_only_jev")
            relevant = True
            priority = 0.5
            relationship = JevRelationship.UNCLEAR
            kind = ResourceKind.OTHER
            category = PrimaryCategory.APPLICATIONS
        elif not relevant:
            reason_codes.append("no_jev_signal")
            relationship = JevRelationship.NOT_RELATED
            kind = ResourceKind.UNRELATED
            priority = 0.0
        else:
            reason_codes.append(f"positive_signals:{positive}")
            priority = 2.0
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
            priority_score=priority,
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
