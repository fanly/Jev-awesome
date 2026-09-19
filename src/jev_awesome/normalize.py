from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


def normalize_url(url: str, *, drop_fragment: bool = False) -> str:
    """Normalize URL for identity. Do not lowercase path. Keep meaningful query."""
    raw = url.strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    # Drop default ports
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    path = parsed.path or "/"
    # Collapse duplicate slashes in path but keep case
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    fragment = "" if drop_fragment else parsed.fragment
    return urlunparse((scheme, netloc, path, "", query, fragment))


def github_repo_from_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host not in {"github.com", "www.github.com"}:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def stable_web_id(canonical_url: str) -> str:
    digest = hashlib.sha256(normalize_url(canonical_url).encode("utf-8")).hexdigest()[:16]
    return f"web:{digest}"


def github_entity_id(repo_id: int) -> str:
    return f"github:{repo_id}"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
