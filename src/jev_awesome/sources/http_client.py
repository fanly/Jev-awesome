from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from jev_awesome.security import UrlSafetyError, validate_redirect_target, validate_url_for_fetch


@dataclass
class RateLimitState:
    remaining: int | None = None
    reset_at: float | None = None
    retry_after: float | None = None


@dataclass
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    text: str
    url: str
    from_cache: bool = False
    etag: str | None = None


@dataclass
class SafeHttpClient:
    timeout: float = 30.0
    max_response_bytes: int = 2_000_000
    max_redirects: int = 5
    user_agent: str = "Jev-awesome-collector/0.1 (+https://github.com/fanly/Jev-awesome)"
    token: str | None = None
    allowed_domains: set[str] | None = None
    allow_http: bool = False
    rate: RateLimitState = field(default_factory=RateLimitState)
    request_count: int = 0

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _update_rate(self, headers: httpx.Headers) -> None:
        if "x-ratelimit-remaining" in headers:
            try:
                self.rate.remaining = int(headers["x-ratelimit-remaining"])
            except ValueError:
                pass
        if "x-ratelimit-reset" in headers:
            try:
                self.rate.reset_at = float(headers["x-ratelimit-reset"])
            except ValueError:
                pass
        if "retry-after" in headers:
            try:
                self.rate.retry_after = float(headers["retry-after"])
            except ValueError:
                self.rate.retry_after = None

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        auth_for_github_only: bool = True,
        allowed_domains: set[str] | None = None,
    ) -> HttpResponse:
        domains = allowed_domains if allowed_domains is not None else self.allowed_domains
        validate_url_for_fetch(url, allowed_domains=domains, allow_http=self.allow_http)
        req_headers = self._headers(headers)
        # Never forward Authorization to non-GitHub hosts
        if auth_for_github_only:
            from urllib.parse import urlparse

            host = (urlparse(url).hostname or "").lower()
            if "github.com" not in host and "api.github.com" not in host:
                req_headers.pop("Authorization", None)
        if etag:
            req_headers["If-None-Match"] = etag
        if last_modified:
            req_headers["If-Modified-Since"] = last_modified

        current = url
        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
            headers=req_headers,
        ) as client:
            for _ in range(self.max_redirects + 1):
                self.request_count += 1
                resp = client.get(current)
                self._update_rate(resp.headers)
                if resp.status_code in {301, 302, 303, 307, 308}:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise UrlSafetyError("redirect without Location")
                    # Resolve relative
                    current = str(httpx.URL(current).join(loc))
                    # Strip auth on cross-host redirect
                    validate_redirect_target(
                        current,
                        allowed_domains=domains,
                        allow_http=self.allow_http,
                    )
                    from urllib.parse import urlparse as up

                    if up(current).hostname != up(url).hostname:
                        req_headers.pop("Authorization", None)
                        client.headers.pop("Authorization", None)
                    continue
                content = resp.content
                if len(content) > self.max_response_bytes:
                    raise UrlSafetyError("response too large")
                return HttpResponse(
                    status_code=resp.status_code,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    text=resp.text,
                    url=str(resp.url),
                    from_cache=resp.status_code == 304,
                    etag=resp.headers.get("etag"),
                )
        raise UrlSafetyError("too many redirects")

    def wait_if_needed(self) -> None:
        if self.rate.retry_after:
            time.sleep(min(self.rate.retry_after, 60))
            self.rate.retry_after = None
        elif self.rate.remaining is not None and self.rate.remaining <= 1:
            if self.rate.reset_at:
                delay = max(0.0, self.rate.reset_at - time.time())
                time.sleep(min(delay, 60))


def classify_http_error(status: int) -> str:
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden_or_rate"
    if status == 404:
        return "not_found"
    if status == 410:
        return "gone"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "server_error"
    return f"http_{status}"
