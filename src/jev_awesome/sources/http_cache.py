"""HTTP conditional-request body cache for collectors (ETag / 304)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CachedHttpBody:
    url: str
    etag: str | None
    body: str
    content_sha256: str

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "etag": self.etag,
            "body": self.body,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CachedHttpBody:
        return cls(
            url=str(data["url"]),
            etag=data.get("etag"),
            body=str(data["body"]),
            content_sha256=str(data["content_sha256"]),
        )


class HttpBodyCache:
    """Durable cache of successful GET bodies keyed by stable page id."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, cache_key: str) -> Path:
        safe = cache_key.replace(":", "_").replace("/", "_")
        return self.root / f"{safe}.json"

    def load(self, cache_key: str) -> CachedHttpBody | None:
        path = self._path(cache_key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cached = CachedHttpBody.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
        # Integrity: body must match recorded digest
        digest = hashlib.sha256(cached.body.encode("utf-8")).hexdigest()
        if digest != cached.content_sha256:
            return None
        return cached

    def save(self, cache_key: str, *, url: str, etag: str | None, body: str) -> CachedHttpBody:
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        cached = CachedHttpBody(url=url, etag=etag, body=body, content_sha256=digest)
        path = self._path(cache_key)
        path.write_text(json.dumps(cached.to_dict(), indent=2) + "\n", encoding="utf-8")
        return cached

    def drop(self, cache_key: str) -> None:
        path = self._path(cache_key)
        if path.exists():
            path.unlink()
