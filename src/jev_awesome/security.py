from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https"}
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
    "169.254.169.254",
}

# Clash/Surge fake-ip / RFC 2544 — NEVER globally trusted.
# Only when JEV_ALLOW_FAKE_IP=1 (local explicit) AND host is allowlisted.
FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)

CLOUD_METADATA_NETS = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)


class UrlSafetyError(ValueError):
    pass


def allow_fake_ip_enabled() -> bool:
    """Explicit local opt-in. CI/production must leave unset/false."""
    if os.environ.get("CI", "").lower() in {"1", "true", "yes"}:
        return False
    if os.environ.get("GITHUB_ACTIONS", "").lower() in {"1", "true"}:
        return False
    raw = os.environ.get("JEV_ALLOW_FAKE_IP", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_fake_ip(addr: ipaddress._BaseAddress) -> bool:
    return any(addr in net for net in FAKE_IP_NETWORKS)


def _is_metadata(addr: ipaddress._BaseAddress) -> bool:
    return any(addr in net for net in CLOUD_METADATA_NETS)


def _is_blocked_ip(ip: str, *, allow_fake_ip: bool = False) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    # IPv4-mapped IPv6
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _is_blocked_ip(str(addr.ipv4_mapped), allow_fake_ip=allow_fake_ip)
    if _is_metadata(addr):
        return True
    if allow_fake_ip and _is_fake_ip(addr):
        return False
    # Fake-ip is private under Python's classification — block unless opted in
    if _is_fake_ip(addr) and not allow_fake_ip:
        return True
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _host_allowlisted(host_l: str, allowed_domains: set[str]) -> bool:
    for d in allowed_domains:
        d_l = d.lower().lstrip(".")
        if host_l == d_l or host_l.endswith("." + d_l):
            return True
    return False


def validate_url_for_fetch(
    url: str,
    *,
    allowed_domains: set[str] | None = None,
    allow_http: bool = False,
    resolve_dns: bool = True,
) -> str:
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES and not (allow_http and scheme == "http"):
        raise UrlSafetyError(f"scheme not allowed: {scheme!r}")
    if not parsed.netloc:
        raise UrlSafetyError("missing host")
    # Reject credentials in URL
    if parsed.username or parsed.password:
        raise UrlSafetyError("userinfo in URL not allowed")
    host = parsed.hostname or ""
    host_l = host.lower().rstrip(".")
    if host_l in BLOCKED_HOSTS or host_l.endswith(".localhost") or host_l.endswith(".local"):
        raise UrlSafetyError(f"blocked host: {host}")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise UrlSafetyError(f"port not allowed: {parsed.port}")

    allowlisted = False
    if allowed_domains is not None:
        allowlisted = _host_allowlisted(host_l, allowed_domains)
        if not allowlisted:
            raise UrlSafetyError(f"domain not in allowlist: {host}")

    fake_ok = allowlisted and allow_fake_ip_enabled()

    try:
        ipaddress.ip_address(host_l)
    except ValueError:
        pass
    else:
        if _is_blocked_ip(host_l, allow_fake_ip=False):
            raise UrlSafetyError(f"private/link-local IP not allowed: {host}")

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host_l, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise UrlSafetyError(f"DNS resolution failed for {host}: {e}") from e
        for info in infos:
            ip = str(info[4][0])
            if _is_blocked_ip(ip, allow_fake_ip=fake_ok):
                raise UrlSafetyError(f"resolved to private IP: {ip}")
    return url.strip()


def validate_redirect_target(
    url: str,
    *,
    allowed_domains: set[str] | None = None,
    allow_http: bool = False,
) -> str:
    return validate_url_for_fetch(
        url,
        allowed_domains=allowed_domains,
        allow_http=allow_http,
        resolve_dns=True,
    )


def escape_md(text: str) -> str:
    # Escape markdown control chars. Do not escape '-' / '.' — repo names and
    # prose become unreadable (typesafe\-ai) while they rarely form structure alone.
    out = []
    for ch in text:
        if ch in "\\`*_{}[]()#+!|<>":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def safe_href(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() in {"http", "https"}:
        return url.strip()
    return None
