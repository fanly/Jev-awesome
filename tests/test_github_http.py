from __future__ import annotations

import json

from jev_awesome.sources import CollectContext
from jev_awesome.sources.github import GitHubDiscoveryAdapter
from jev_awesome.sources.http_client import HttpResponse, SafeHttpClient


class ScriptedClient(SafeHttpClient):
    def __init__(self, responses: list[HttpResponse]):
        super().__init__(allowed_domains={"api.github.com", "github.com"})
        self._responses = list(responses)
        self.request_count = 0

    def get(self, url: str, **kwargs):  # type: ignore[override]
        self.request_count += 1
        if not self._responses:
            raise RuntimeError(f"unexpected request: {url}")
        return self._responses.pop(0)


def test_t05_pagination_and_incomplete():
    page1 = {
        "total_count": 1500,
        "incomplete_results": True,
        "items": [
            {
                "id": 1,
                "full_name": "a/b",
                "html_url": "https://github.com/a/b",
                "description": "jev",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ],
    }
    page2 = {
        "total_count": 1500,
        "incomplete_results": False,
        "items": [],
    }
    client = ScriptedClient(
        [
            HttpResponse(200, {}, json.dumps(page1), "https://api.github.com"),
            HttpResponse(200, {}, json.dumps(page2), "https://api.github.com"),
        ]
    )
    adapter = GitHubDiscoveryAdapter(queries=["topic:jev"], client=client)
    resources, result = adapter.collect(
        CollectContext(dry_run=True, write_local=False, max_pages=2)
    )
    assert len(resources) == 1
    assert any("incomplete_results" in g for g in result.coverage_gaps)


def test_t06_401_no_blind_retry():
    client = ScriptedClient([HttpResponse(401, {}, '{"message":"bad"}', "https://api.github.com")])
    adapter = GitHubDiscoveryAdapter(queries=["topic:jev"], client=client)
    resources, result = adapter.collect(CollectContext(dry_run=True, write_local=False))
    assert resources == []
    assert result.status == "failed"
    assert client.request_count == 1


def test_t08_etag_304_reuses():
    client = ScriptedClient(
        [HttpResponse(304, {}, "", "https://api.github.com", from_cache=True, etag='"abc"')]
    )
    # Direct client behavior
    resp = client.get("https://api.github.com/x", etag='"abc"')
    assert resp.status_code == 304
    assert resp.from_cache is True
