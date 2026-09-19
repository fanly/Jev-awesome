from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jev_awesome.dates import utc_now
from jev_awesome.models import (
    ClassifierMode,
    ClassifierSuggestion,
    JevRelationship,
    PrimaryCategory,
    Resource,
    ResourceKind,
)

# Verified against typesafe-sdk 0.7.0 and docs.typesafe.ai (2026-09-19)


class TypeSafeConfigError(RuntimeError):
    pass


@dataclass
class TypeSafeClassifier:
    """Optional real TypeSafe SDK adapter. Never invents API fields."""

    mode: ClassifierMode = ClassifierMode.TYPESAFE
    api_key: str | None = None
    max_requests: int = 50
    request_count: int = 0
    model: str | None = None
    client_factory: Callable[..., Any] | None = None
    _errors: list[str] = field(default_factory=list)

    def _require_key(self) -> str:
        key = self.api_key or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise TypeSafeConfigError(
                "TYPESAFE_API_KEY is required for classifier mode "
                f"{self.mode.value}; refusing to pretend the API is connected"
            )
        return key

    def classify(self, resource: Resource) -> ClassifierSuggestion:
        if self.request_count >= self.max_requests:
            return ClassifierSuggestion(
                mode=self.mode,
                error="typesafe_request_budget_exceeded",
                reason_codes=["budget_exceeded"],
                created_at=utc_now(),
            )
        try:
            from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
        except ImportError as e:  # pragma: no cover
            raise TypeSafeConfigError(f"typesafe-sdk not installed: {e}") from e

        key = self._require_key()
        state = {
            "title": resource.original_title,
            "url": resource.canonical_url,
            "summary": resource.summary_en or resource.summary_zh or "",
            "tags": resource.tags,
            "full_name": resource.github_full_name or "",
            "author": resource.author_or_org or "",
        }
        # Independent questions — none depends on another's answer in this call
        questions = {
            "relevant": Noul(
                instructions=(
                    "Is `title` / `summary` / `url` about TypeSafe AI, its System One "
                    "model Jev, or software that integrates the TypeSafe API/SDK? "
                    "Answer yes only for the TypeSafe product ecosystem, not generic "
                    "'type-safe' programming or unrelated projects that merely share a name."
                ),
            ),
            "kind": Choice(
                instructions="What kind of developer resource is this?",
                criteria={
                    "official_doc": "Official TypeSafe documentation or changelog",
                    "sdk": "Language SDK, client, or framework integration",
                    "tutorial": "Getting-started guide, cookbook, or pattern write-up",
                    "application": "Application or tool with a concrete implementation",
                    "evaluation": "Evaluation, benchmark, failure case, or limits study",
                    "research": "Research paper or independent reimplementation",
                    "insufficient_evidence": "Not enough information to classify",
                    "unrelated": "Not about TypeSafe / Jev",
                },
            ),
            "relationship": Choice(
                instructions="How does this resource relate to Jev / TypeSafe?",
                criteria={
                    "official": "Published by TypeSafe / typesafe-ai",
                    "calls_official_api": "Calls the official TypeSafe API or SDK",
                    "community_sdk": "Community-maintained SDK or binding",
                    "inspired_independent": "Inspired by Jev but independent implementation",
                    "mention_only": "Only mentions Jev/TypeSafe without integration",
                    "unclear": "Relationship cannot be determined",
                    "not_related": "Not related",
                },
            ),
            "review_priority": Score(
                instructions="How urgently should a human curator review this candidate?",
                criteria=[
                    "Low priority / likely noise",
                    "Medium priority / plausible candidate",
                    "High priority / official or strong evidence",
                ],
            ),
        }

        factory = self.client_factory or TypeSafeClient
        self.request_count += 1
        try:
            with factory(api_key=key, model=self.model) as client:
                response = client.system_one(state=state, questions=questions)
        except Exception as e:  # noqa: BLE001
            self._errors.append(str(e))
            return ClassifierSuggestion(
                mode=self.mode,
                error=f"typesafe_call_failed:{type(e).__name__}:{e}",
                reason_codes=["typesafe_error"],
                created_at=utc_now(),
            )

        # Noul: only .noul — no confidence field exists on NoulAnswer
        noul_obj: Any = response.nouls.get("relevant") or response.answers.get("relevant")
        if noul_obj is None:
            raise TypeError("typesafe response missing noul for 'relevant'")
        relevance_p = float(noul_obj.noul)
        # Do NOT read confidence on Noul
        choice_kind: Any = response.choices.get("kind") or response.answers.get("kind")
        choice_rel: Any = response.choices.get("relationship") or response.answers.get(
            "relationship"
        )
        score_pri: Any = response.scores.get("review_priority") or response.answers.get(
            "review_priority"
        )
        if choice_kind is None or choice_rel is None or score_pri is None:
            raise TypeError("typesafe response missing choice/score answers")

        kind_raw = choice_kind.choice
        rel_raw = choice_rel.choice
        try:
            kind = ResourceKind(kind_raw)
        except ValueError:
            kind = ResourceKind.INSUFFICIENT_EVIDENCE
        try:
            relationship = JevRelationship(rel_raw)
        except ValueError:
            relationship = JevRelationship.UNCLEAR

        category_map = {
            ResourceKind.OFFICIAL_DOC: PrimaryCategory.OFFICIAL,
            ResourceKind.SDK: PrimaryCategory.SDK_INTEGRATIONS,
            ResourceKind.TUTORIAL: PrimaryCategory.GETTING_STARTED,
            ResourceKind.APPLICATION: PrimaryCategory.APPLICATIONS,
            ResourceKind.EVALUATION: PrimaryCategory.EVALS_LIMITS,
            ResourceKind.RESEARCH: PrimaryCategory.RESEARCH_ALTS,
            ResourceKind.ALTERNATIVE: PrimaryCategory.RESEARCH_ALTS,
        }

        return ClassifierSuggestion(
            mode=self.mode,
            relevant=relevance_p >= 0.5,
            relevance_probability=relevance_p,
            resource_kind=kind,
            jev_relationship=relationship,
            primary_category=category_map.get(kind),
            priority_score=float(score_pri.score),
            reason_codes=[
                f"noul_relevant:{relevance_p:.3f}",
                f"kind_confidence:{float(choice_kind.confidence):.3f}",
                f"rel_confidence:{float(choice_rel.confidence):.3f}",
            ],
            model_name=self.model or "jev-latest",
            created_at=utc_now(),
        )


def build_classifier(mode: ClassifierMode, **kwargs: Any):
    from jev_awesome.classification.rules import RulesClassifier

    if mode == ClassifierMode.RULES:
        return RulesClassifier()
    if mode == ClassifierMode.TYPESAFE:
        return TypeSafeClassifier(mode=mode, **kwargs)
    if mode == ClassifierMode.AUTO:
        key = kwargs.get("api_key") or os.environ.get("TYPESAFE_API_KEY")
        if key:
            return TypeSafeClassifier(mode=ClassifierMode.AUTO, api_key=key, **kwargs)
        return RulesClassifier(mode=ClassifierMode.AUTO)
    raise ValueError(f"unknown classifier mode: {mode}")
