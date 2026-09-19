from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https"}
# http only if explicitly allowed by source config
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.google",
}

# Clash/Surge fake-ip and RFC 2544 benchmarking range — not a routable LAN.
# Allowed only when the hostname is already on an explicit allowlist.
FAKE_IP_NETWORKS = (
    ipaddress.ip_network("198.18.0.0/15"),
)


class UrlSafetyError(ValueError):
    pass


def _is_fake_ip(addr: ipaddress._BaseAddress) -> bool:
    return any(addr in net for net in FAKE_IP_NETWORKS)


def _is_blocked_ip(ip: str, *, allow_fake_ip: bool = False) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if allow_fake_ip and _is_fake_ip(addr):
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


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
    host = parsed.hostname or ""
    host_l = host.lower().rstrip(".")
    if host_l in BLOCKED_HOSTS or host_l.endswith(".localhost"):
        raise UrlSafetyError(f"blocked host: {host}")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise UrlSafetyError(f"port not allowed: {parsed.port}")
    allowlisted = False
    if allowed_domains is not None:
        allowlisted = any(
            host_l == d.lower() or host_l.endswith("." + d.lower()) for d in allowed_domains
        )
        if not allowlisted:
            raise UrlSafetyError(f"domain not in allowlist: {host}")
    # Literal IP in URL — never allow private literals
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
            ip = info[4][0]
            # Fake-ip (198.18/15) only tolerated for explicitly allowlisted hostnames
            if _is_blocked_ip(ip, allow_fake_ip=allowlisted):
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
    """Escape Markdown-sensitive characters in untrusted strings."""
    out = []
    for ch in text:
        if ch in "\\`*_{}[]()#+-.!|<>":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def safe_href(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() in {"http", "https"}:
        return url.strip()
    return None
