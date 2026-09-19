from __future__ import annotations

from dataclasses import dataclass

from jev_awesome.models import Resource
from jev_awesome.normalize import github_repo_from_url, normalize_url


@dataclass
class MergeSuggestion:
    left_id: str
    right_id: str
    reason: str
    auto_merge: bool


def identity_keys(resource: Resource) -> set[str]:
    keys: set[str] = {resource.id}
    if resource.github_repo_id is not None:
        keys.add(f"gh_id:{resource.github_repo_id}")
    if resource.github_full_name:
        keys.add(f"gh_name:{resource.github_full_name.lower()}")
    keys.add(f"url:{normalize_url(resource.canonical_url)}")
    for alias in resource.aliases:
        keys.add(f"url:{normalize_url(alias)}")
    gh = github_repo_from_url(resource.canonical_url)
    if gh:
        keys.add(f"gh_name:{gh[0].lower()}/{gh[1].lower()}")
    return keys


def find_duplicate(
    candidate: Resource, existing: list[Resource]
) -> Resource | None:
    """Return existing resource to merge into, or None.

    Different owners with same repo name must NOT merge.
    """
    cand_keys = identity_keys(candidate)
    for item in existing:
        if identity_keys(item) & cand_keys:
            # Extra safety: if both have github full names under different owners, skip
            if (
                candidate.github_full_name
                and item.github_full_name
                and candidate.github_full_name.lower().split("/")[0]
                != item.github_full_name.lower().split("/")[0]
                and candidate.github_repo_id != item.github_repo_id
            ):
                continue
            return item
    return None


def title_similarity_suggestion(
    candidate: Resource, existing: list[Resource], threshold: float = 0.92
) -> MergeSuggestion | None:
    """Fuzzy title match → suggestion only, never auto-merge."""
    from difflib import SequenceMatcher

    ctitle = candidate.original_title.strip().lower()
    if len(ctitle) < 8:
        return None
    for item in existing:
        if item.id == candidate.id:
            continue
        ratio = SequenceMatcher(None, ctitle, item.original_title.strip().lower()).ratio()
        if ratio >= threshold:
            return MergeSuggestion(
                left_id=candidate.id,
                right_id=item.id,
                reason=f"similar_title:{ratio:.3f}",
                auto_merge=False,
            )
    return None


def merge_machine_fields(target: Resource, incoming: Resource) -> Resource:
    """Update machine-safe fields; never overwrite non-empty editorial fields."""
    data = target.model_dump()
    incoming_data = incoming.model_dump()

    editorial_keys = {
        "summary_zh",
        "summary_en",
        "developer_value",
        "jev_role",
        "prerequisites",
        "limitations",
        "editorial_status",
        "verification_level",
        "evidence",
        "review_record",
        "primary_category",
        "resource_kind",
        "jev_relationship",
        "official_status",
        "license_status",
        "license_identifier",
        "license_evidence",
    }

    for key, value in incoming_data.items():
        if key in editorial_keys:
            continue
        if key == "suggestion":
            data["suggestion"] = value
            continue
        if key == "first_discovered_at":
            # Keep earliest
            if incoming.first_discovered_at < target.first_discovered_at:
                data["first_discovered_at"] = incoming_data["first_discovered_at"]
            continue
        if key in {"aliases", "related_links", "tags", "languages"}:
            merged = list(dict.fromkeys([*(data.get(key) or []), *(value or [])]))
            data[key] = merged
            continue
        if value is not None:
            data[key] = value

    # Preserve first_discovered_at minimum already handled
    return Resource.model_validate(data)
