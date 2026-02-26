"""SPA-aware page navigator for crawling websites."""

import fnmatch
from urllib.parse import urlparse

from playwright.async_api import Page

from breakthevibe.constants import DEFAULT_MAX_DEPTH

# JavaScript to extract all links from the page
DISCOVER_LINKS_JS = """
() => {
    const links = new Set();
    document.querySelectorAll('a[href]').forEach(a => {
        try {
            const url = new URL(a.href, window.location.origin);
            links.add(url.origin + url.pathname);
        } catch {}
    });
    return [...links];
}
"""

# JavaScript to install SPA navigation listener
INSTALL_SPA_LISTENER_JS = """
() => {
    if (window.__btv_spa_listener) return;
    window.__btv_spa_listener = true;
    window.__btv_route_changes = [];
    const orig_push = history.pushState;
    const orig_replace = history.replaceState;
    history.pushState = function(...args) {
        orig_push.apply(this, args);
        window.__btv_route_changes.push(window.location.href);
    };
    history.replaceState = function(...args) {
        orig_replace.apply(this, args);
        window.__btv_route_changes.push(window.location.href);
    };
    window.addEventListener('popstate', () => {
        window.__btv_route_changes.push(window.location.href);
    });
    window.addEventListener('hashchange', () => {
        window.__btv_route_changes.push(window.location.href);
    });
}
"""


class Navigator:
    """SPA-aware page discovery and navigation."""

    def __init__(
        self,
        base_url: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
        skip_patterns: list[str] | None = None,
        allowed_domains: list[str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._max_depth = max_depth
        self._skip_patterns = skip_patterns or []
        self._visited: set[str] = set()
        self._base_domain = urlparse(base_url).netloc
        # Allowed domains includes the base domain plus any configured (#19)
        self._allowed_domains: set[str] = {self._base_domain}
        if allowed_domains:
            self._allowed_domains.update(allowed_domains)

    def should_skip(self, path: str) -> bool:
        """Check if path matches any skip pattern."""
        return any(fnmatch.fnmatch(path, pattern) for pattern in self._skip_patterns)

    def should_visit(self, url: str) -> bool:
        """Check if URL should be visited (allowed domain, not visited, not skipped)."""
        if url in self._visited:
            return False
        parsed = urlparse(url)
        if parsed.netloc not in self._allowed_domains:
            return False
        path = parsed.path or "/"
        return not self.should_skip(path)

    def is_within_depth(self, depth: int) -> bool:
        """Check if current depth is within max depth."""
        return depth <= self._max_depth

    def mark_visited(self, url: str) -> None:
        """Mark a URL as visited."""
        self._visited.add(url)

    def get_path(self, url: str) -> str:
        """Extract clean path from URL (without query params or fragment)."""
        parsed = urlparse(url)
        return parsed.path or "/"

    async def discover_links(self, page: Page) -> list[str]:
        """Discover all links on the current page, filtered to same domain."""
        all_links: list[str] = await page.evaluate(DISCOVER_LINKS_JS)
        return [
            link
            for link in all_links
            if self.should_visit(link) and not link.startswith("javascript:")
        ]

    async def install_spa_listener(self, page: Page) -> None:
        """Install JavaScript listener for SPA route changes."""
        await page.evaluate(INSTALL_SPA_LISTENER_JS)

    async def get_spa_route_changes(self, page: Page) -> list[str]:
        """Get any SPA route changes that occurred since last check."""
        result: list[str] = await page.evaluate(
            "() => { const c = window.__btv_route_changes || [];"
            " window.__btv_route_changes = []; return c; }"
        )
        return result

    async def get_current_url(self, page: Page) -> str:
        """Get the current page URL."""
        return page.url
