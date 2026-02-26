"""URL and input sanitization utilities."""

import ipaddress
from urllib.parse import urlparse


def sanitize_url(url: str) -> str:
    """Strip whitespace and remove fragments from URL."""
    url = url.strip()
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def is_safe_url(url: str) -> bool:
    """Check if URL is safe to crawl (not localhost or private IP)."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False

    # Block localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):  # nosec B104
        return False

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_global
    except ValueError:
        # Not an IP address (it's a domain name) — allow it
        return True
