"""URL and input sanitization utilities."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_BLOCKED_DNS_SUFFIXES: tuple[str, ...] = (".internal", ".local", ".cluster.local")


def sanitize_url(url: str) -> str:
    """Strip whitespace and remove fragments from URL."""
    url = url.strip()
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _is_private_ip(ip_str: str) -> bool:
    """Return True if the given IP address string is in a non-global range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


def is_safe_url(url: str) -> bool:
    """Check if URL is safe to crawl.

    Enforces:
    - Only ``http`` and ``https`` schemes are allowed.
    - Blocked DNS suffixes (.internal, .local, .cluster.local).
    - All resolved IPs must be globally routable (blocks private, loopback,
      link-local, and reserved ranges — defends against DNS rebinding).
    """
    parsed = urlparse(url)

    # Enforce scheme allowlist
    if parsed.scheme not in _ALLOWED_SCHEMES:
        logger.debug("is_safe_url_rejected_scheme", url=url, scheme=parsed.scheme)
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Block internal DNS suffixes
    lower_host = hostname.lower()
    for suffix in _BLOCKED_DNS_SUFFIXES:
        if lower_host == suffix.lstrip(".") or lower_host.endswith(suffix):
            logger.debug("is_safe_url_rejected_dns_suffix", url=url, hostname=hostname)
            return False

    # If hostname is already an IP literal, check it directly
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            logger.debug("is_safe_url_rejected_ip", url=url, ip=str(ip))
            return False
        return True
    except ValueError:
        pass  # hostname is a domain name — proceed to DNS resolution

    # Resolve all IPs and verify every one is globally routable (anti-DNS-rebinding)
    try:
        results = socket.getaddrinfo(hostname, None)
        if not results:
            return False
        for _family, _type, _proto, _canonname, sockaddr in results:
            ip_str = str(sockaddr[0])
            if _is_private_ip(ip_str):
                logger.debug(
                    "is_safe_url_rejected_resolved_ip",
                    url=url,
                    hostname=hostname,
                    resolved_ip=ip_str,
                )
                return False
    except OSError:
        # DNS resolution failure — treat as unsafe
        logger.debug("is_safe_url_dns_resolution_failed", url=url, hostname=hostname)
        return False

    return True
