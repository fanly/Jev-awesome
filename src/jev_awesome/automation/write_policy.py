"""Path + field write policy for automation publisher.

Allowlist is defined by trusted main code — never by artifacts or robot branch.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

# Relative to repo root. Globs are prefix / exact path rules, not shell-expanded.
ALLOWED_PATH_PREFIXES: tuple[str, ...] = (
    "data/observations/",
    "data/inbox/",
    "data/events/",
    "data/cache/checkpoints/",
    "data/reports/",
)

ALLOWED_EXACT_PATHS: tuple[str, ...] = (
    "README.md",
    "README.en.md",
)

ALLOWED_PATH_PREFIXES_DOCS: tuple[str, ...] = (
    "docs/categories/",
    "docs/updates/",
)

# Never auto-touched
FORBIDDEN_PATH_PREFIXES: tuple[str, ...] = (
    "src/",
    ".github/",
    "tests/",
    "config/",
    "templates/",
    "schemas/",
    "docs/implementation/",
    "docs/operations/",
    "docs/guides/",
)

FORBIDDEN_EXACT: tuple[str, ...] = (
    "LICENSE",
    "AGENTS.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".gitignore",
    ".env",
    ".env.example",
    ".github/CODEOWNERS",
)

# Resource JSON fields robots may update on pending/proposed machine-owned records
MACHINE_WRITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "suggestion",
        "content_hash",
        "github_repo_id",
        "github_full_name",
        "aliases",
        "related_links",
        "tags",
        "languages",
        "source_identity",
        "author_or_org",
        "last_material_change_at",
        "canonical_url",
        "original_title",  # only when editorial_status is pending and no human summary yet — enforced below
        "summary_en",  # machine discovery snippet only if summary_zh empty and status pending
        "published_at",
        "license_identifier",
        "license_status",
        "resource_kind",  # suggestion-applied only for pending empty-ish
        "primary_category",
        "jev_relationship",
        "official_status",
    }
)

EDITORIAL_PROTECTED_FIELDS: frozenset[str] = frozenset(
    {
        "summary_zh",
        "developer_value",
        "jev_role",
        "prerequisites",
        "limitations",
        "editorial_status",
        "verification_level",
        "evidence",
        "review_record",
        "id",
        "schema_version",
        "first_discovered_at",
    }
)

ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "first_discovered",
        "new_version",
        "doc_change",
        "suggestion_only",
    }
)

FORBIDDEN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "human_accepted",
        "verification_update",
        "withdrawn",
        "archived",
    }
)

MAX_SINGLE_FILE_BYTES = 1_500_000
MAX_TOTAL_WRITE_BYTES = 40_000_000
MAX_FILE_COUNT = 5_000


class WritePolicyError(ValueError):
    pass


def normalize_rel_path(path: str | Path) -> str:
    raw = str(path).replace("\\", "/")
    if raw.startswith("/") or raw.startswith("~"):
        raise WritePolicyError(f"absolute path rejected: {path}")
    if "\x00" in raw:
        raise WritePolicyError("nul in path")
    parts = PurePosixPath(raw).parts
    if ".." in parts:
        raise WritePolicyError(f"path traversal rejected: {path}")
    if any(p in {".git"} or p.startswith(".git") for p in parts if p != ".github"):
        # allow .github only as forbidden prefix check elsewhere; block .git objects
        if parts[0] == ".git":
            raise WritePolicyError(f"git metadata path rejected: {path}")
    norm = PurePosixPath(*parts).as_posix() if parts else ""
    if norm != PurePosixPath(raw).as_posix() and ".." in raw:
        raise WritePolicyError(f"path rejected: {path}")
    return norm.lstrip("./")


def is_path_allowed(rel: str) -> bool:
    try:
        p = normalize_rel_path(rel)
    except WritePolicyError:
        return False
    if p in FORBIDDEN_EXACT:
        return False
    for pref in FORBIDDEN_PATH_PREFIXES:
        if p == pref.rstrip("/") or p.startswith(pref):
            return False
    if p in ALLOWED_EXACT_PATHS:
        return True
    for pref in ALLOWED_PATH_PREFIXES + ALLOWED_PATH_PREFIXES_DOCS:
        if p.startswith(pref):
            return True
    # curated resources: robot must NOT write data/resources/ (human curation only)
    return False


def assert_path_allowed(rel: str) -> str:
    p = normalize_rel_path(rel)
    if not is_path_allowed(p):
        raise WritePolicyError(f"path not in automation allowlist: {p}")
    return p


def assert_not_symlink(path: Path) -> None:
    if path.is_symlink():
        raise WritePolicyError(f"symlink rejected: {path}")


def filter_machine_resource_update(existing: dict | None, incoming: dict) -> dict:
    """Return sanitized resource dict for automation write.

    Never overwrites editorial protected fields when existing has them.
    Never raises editorial_status to curated/rejected/archived.
    """
    out = dict(incoming)
    # Strip forbidden event-like elevation
    status = out.get("editorial_status", "pending")
    if status in {"curated", "rejected", "archived"}:
        if existing is None or existing.get("editorial_status") != status:
            raise WritePolicyError(f"automation cannot set editorial_status={status}")
    if existing:
        for field in EDITORIAL_PROTECTED_FIELDS:
            if field in existing and existing[field] not in (None, "", [], {}):
                out[field] = existing[field]
        # Keep earliest discovery
        if existing.get("first_discovered_at"):
            out["first_discovered_at"] = existing["first_discovered_at"]
        # If human summaries exist, keep titles stable unless pending-only empty
        if existing.get("summary_zh"):
            out["summary_zh"] = existing["summary_zh"]
            if existing.get("original_title"):
                out["original_title"] = existing["original_title"]
        # Never let automation change verification upward beyond source_checked
        # when existing already has human evidence
        if existing.get("verification_level") in {
            "code_located",
            "reproduced",
            "benchmarked",
            "source_checked",
        } and existing.get("evidence"):
            out["verification_level"] = existing["verification_level"]
            out["evidence"] = existing["evidence"]
        if existing.get("review_record") and (
            existing["review_record"].get("decision") or existing["review_record"].get("reviewer")
        ):
            out["review_record"] = existing["review_record"]
            out["editorial_status"] = existing.get("editorial_status", out.get("editorial_status"))
    else:
        # New records: only pending/proposed
        if out.get("editorial_status") not in {"pending", "proposed", None}:
            out["editorial_status"] = "pending"
        if out.get("editorial_status") is None:
            out["editorial_status"] = "pending"
        # Automation must not claim human acceptance
        rr = out.get("review_record") or {}
        if rr.get("decision") in {"approve", "reject", "archive", "merge"}:
            raise WritePolicyError("new resource cannot carry human decision")
    return out


def assert_event_allowed(event_type: str) -> None:
    if event_type in FORBIDDEN_EVENT_TYPES:
        raise WritePolicyError(f"automation cannot emit event_type={event_type}")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise WritePolicyError(f"unknown/disallowed event_type={event_type}")


def validate_write_set(
    rel_paths: list[str],
    *,
    sizes: dict[str, int] | None = None,
) -> None:
    if len(rel_paths) > MAX_FILE_COUNT:
        raise WritePolicyError("too many files in write set")
    total = 0
    for rel in rel_paths:
        assert_path_allowed(rel)
        if sizes and rel in sizes:
            if sizes[rel] > MAX_SINGLE_FILE_BYTES:
                raise WritePolicyError(f"file too large: {rel}")
            total += sizes[rel]
    if total > MAX_TOTAL_WRITE_BYTES:
        raise WritePolicyError("total write set too large")


def env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
