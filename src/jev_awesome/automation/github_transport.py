"""GitHub HTTP transport for publisher. Production uses httpx; tests inject Fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qs, quote, urlparse


@dataclass
class HttpCall:
    method: str
    url: str
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)


class GitHubTransport(Protocol):
    calls: list[HttpCall]

    def get_json(self, path: str) -> tuple[int, Any]: ...

    def post_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any]: ...

    def patch_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any]: ...


def pr_is_merged(pr: dict[str, Any]) -> bool:
    """True if GitHub PR is merged (merged==True OR merged_at is a non-null string)."""
    if pr.get("merged") is True:
        return True
    merged_at = pr.get("merged_at")
    return isinstance(merged_at, str) and bool(merged_at.strip())


def pr_is_closed_unmerged(pr: dict[str, Any]) -> bool:
    return pr.get("state") == "closed" and not pr_is_merged(pr)


def normalize_pr_list_item(pr: dict[str, Any]) -> dict[str, Any]:
    """Shared list shape: omit `merged` boolean so callers must use pr_is_merged/merged_at."""
    out = dict(pr)
    merged_flag = out.pop("merged", None)
    if pr_is_merged({**out, "merged": merged_flag}):
        out.setdefault("merged_at", out.get("merged_at") or "1970-01-01T00:00:00Z")
    else:
        out.setdefault("merged_at", None)
    return out


@dataclass
class HttpxGitHubTransport:
    """Real transport. Authorization only to api.github.com."""

    token: str
    api_base: str = "https://api.github.com"
    user_agent: str = "Jev-awesome-publisher/0.1"
    calls: list[HttpCall] = field(default_factory=list)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_json(self, path: str) -> tuple[int, Any]:
        import httpx

        url = f"{self.api_base}{path}"
        self.calls.append(HttpCall("GET", url))
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            r = client.get(url, headers=self._headers())
            try:
                data = r.json() if r.content else None
            except Exception:  # noqa: BLE001
                data = {"raw": r.text[:500]}
            return r.status_code, data

    def post_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        import httpx

        url = f"{self.api_base}{path}"
        self.calls.append(HttpCall("POST", url, body=body))
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            r = client.post(url, headers=self._headers(), json=body)
            return r.status_code, (r.json() if r.content else None)

    def patch_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        import httpx

        url = f"{self.api_base}{path}"
        self.calls.append(HttpCall("PATCH", url, body=body))
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            r = client.patch(url, headers=self._headers(), json=body)
            return r.status_code, (r.json() if r.content else None)


class GitHubAPIError(RuntimeError):
    """GitHub REST call failed in a way that must not be treated as empty success."""


@dataclass
class FakeGitHubTransport:
    """In-memory GitHub REST subset for publisher integration tests."""

    owner: str = "fanly"
    repo: str = "Jev-awesome"
    calls: list[HttpCall] = field(default_factory=list)
    pulls: list[dict[str, Any]] = field(default_factory=list)
    next_pr: int = 1
    # branch ref -> sha
    refs: dict[str, str] = field(default_factory=dict)
    # Simulate API failure modes
    fail_create_pr: bool = False
    fail_update_pr: bool = False
    fail_list_prs_status: int | None = None
    remote_head_override: str | None = None

    def get_json(self, path: str) -> tuple[int, Any]:
        self.calls.append(HttpCall("GET", path))
        # GET /repos/{owner}/{repo}/pulls?head=owner:branch&state=open
        if path.startswith(f"/repos/{self.owner}/{self.repo}/pulls"):
            if self.fail_list_prs_status is not None:
                return self.fail_list_prs_status, {"message": "list failed"}
            parsed = urlparse(path if "://" in path else f"https://api.github.com{path}")
            qs = parse_qs(parsed.query)
            state = (qs.get("state") or ["open"])[0]
            head_filter = (qs.get("head") or [None])[0]
            page = int((qs.get("page") or ["1"])[0])
            per_page = int((qs.get("per_page") or ["20"])[0])
            items = [p for p in self.pulls if p.get("state") == state]
            if head_filter:
                # head is owner:branch
                want_branch = head_filter.split(":", 1)[-1]
                items = [p for p in items if (p.get("head") or {}).get("ref") == want_branch]
            start = (page - 1) * per_page
            page_items = items[start : start + per_page]
            # Omit `merged` boolean — real GitHub list often has merged_at only
            return 200, [normalize_pr_list_item(p) for p in page_items]
        if "/git/ref/heads/" in path:
            branch = path.rsplit("/", 1)[-1]
            sha = self.refs.get(branch)
            if not sha:
                return 404, {"message": "Not Found"}
            return 200, {"ref": f"refs/heads/{branch}", "object": {"sha": sha}}
        return 404, {"message": "Not Found"}

    def post_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        self.calls.append(HttpCall("POST", path, body=body))
        if path == f"/repos/{self.owner}/{self.repo}/pulls":
            if self.fail_create_pr:
                return 500, {"message": "create failed"}
            # Only one open robot PR
            head = body.get("head")
            for p in self.pulls:
                if p.get("state") == "open" and p.get("head", {}).get("ref") == head:
                    return 422, {"message": "already exists", "number": p["number"]}
            number = self.next_pr
            self.next_pr += 1
            pr = {
                "number": number,
                "html_url": f"https://github.com/{self.owner}/{self.repo}/pull/{number}",
                "state": "open",
                "merged": False,
                "merged_at": None,
                "title": body.get("title"),
                "body": body.get("body"),
                "head": {
                    "ref": body.get("head"),
                    "sha": self.refs.get(body.get("head") or "", ""),
                },
                "base": {"ref": body.get("base", "main")},
            }
            self.pulls.append(pr)
            return 201, normalize_pr_list_item(pr)
        return 404, {"message": "Not Found"}

    def patch_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        self.calls.append(HttpCall("PATCH", path, body=body))
        if self.fail_update_pr:
            return 500, {"message": "update failed"}
        # /repos/.../pulls/{number}
        try:
            number = int(path.rstrip("/").rsplit("/", 1)[-1])
        except ValueError:
            return 404, {"message": "Not Found"}
        for p in self.pulls:
            if p["number"] == number:
                if "state" in body:
                    p["state"] = body["state"]
                if "title" in body:
                    p["title"] = body["title"]
                if "body" in body:
                    p["body"] = body["body"]
                return 200, p
        return 404, {"message": "Not Found"}

    def set_branch_sha(self, branch: str, sha: str) -> None:
        self.refs[branch] = sha

    def open_robot_prs(self, branch: str) -> list[dict[str, Any]]:
        return [
            p
            for p in self.pulls
            if p.get("state") == "open" and p.get("head", {}).get("ref") == branch
        ]

    def close_pr(self, number: int, *, merged: bool = False) -> None:
        for p in self.pulls:
            if p["number"] == number:
                p["state"] = "closed"
                p["merged"] = merged
                p["merged_at"] = "2026-01-15T12:00:00Z" if merged else None
                return
        raise KeyError(f"PR {number} not found")

    def mark_merged(self, number: int, *, head_sha: str | None = None) -> None:
        """Mark PR merged using merged_at (omit relying on `merged` alone for list path)."""
        for p in self.pulls:
            if p["number"] == number:
                p["state"] = "closed"
                # Keep merged for internal helpers; list responses strip it via normalize.
                p["merged"] = True
                p["merged_at"] = "2026-01-15T12:00:00Z"
                if head_sha:
                    p.setdefault("head", {})["sha"] = head_sha
                return
        raise KeyError(f"PR {number} not found")

    def robot_prs(self, branch: str) -> list[dict[str, Any]]:
        return [p for p in self.pulls if p.get("head", {}).get("ref") == branch]

    def latest_unmerged_head_sha(self, branch: str) -> str | None:
        """Head SHA for open or closed-unmerged robot PR (prefer open)."""
        open_prs = [
            p
            for p in self.pulls
            if p.get("head", {}).get("ref") == branch and p.get("state") == "open"
        ]
        if open_prs:
            return (open_prs[0].get("head") or {}).get("sha") or self.refs.get(branch)
        closed = [
            p
            for p in self.pulls
            if p.get("head", {}).get("ref") == branch
            and p.get("state") == "closed"
            and not p.get("merged")
        ]
        if closed:
            return (closed[0].get("head") or {}).get("sha")
        return None

    def has_merged_robot_pr(self, branch: str) -> bool:
        return any(p.get("head", {}).get("ref") == branch and p.get("merged") for p in self.pulls)


def encode_head(owner: str, branch: str) -> str:
    return quote(f"{owner}:{branch}", safe=":")
