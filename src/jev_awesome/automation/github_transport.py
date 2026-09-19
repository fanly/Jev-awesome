"""GitHub HTTP transport for publisher. Production uses httpx; tests inject Fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote


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
    remote_head_override: str | None = None

    def get_json(self, path: str) -> tuple[int, Any]:
        self.calls.append(HttpCall("GET", path))
        # GET /repos/{owner}/{repo}/pulls?head=owner:branch&state=open
        if path.startswith(f"/repos/{self.owner}/{self.repo}/pulls"):
            open_pulls = [p for p in self.pulls if p.get("state") == "open"]
            if "state=closed" in path:
                return 200, [p for p in self.pulls if p.get("state") == "closed"]
            return 200, open_pulls
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
                "title": body.get("title"),
                "body": body.get("body"),
                "head": {
                    "ref": body.get("head"),
                    "sha": self.refs.get(body.get("head") or "", ""),
                },
                "base": {"ref": body.get("base", "main")},
            }
            self.pulls.append(pr)
            return 201, pr
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
                return
        raise KeyError(f"PR {number} not found")

    def mark_merged(self, number: int, *, head_sha: str | None = None) -> None:
        for p in self.pulls:
            if p["number"] == number:
                p["state"] = "closed"
                p["merged"] = True
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
