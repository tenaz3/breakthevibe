"""Tests for sitemap hashing utility."""

import pytest

from breakthevibe.models.domain import ApiCallInfo, PageData, SiteMap
from breakthevibe.utils.sitemap_hash import compute_sitemap_hash


@pytest.mark.unit
class TestSitemapHash:
    def _make_sitemap(self, pages: list[PageData] | None = None) -> SiteMap:
        return SiteMap(
            base_url="https://example.com",
            pages=pages or [],
            api_endpoints=[],
        )

    def test_deterministic(self) -> None:
        """Same sitemap produces same hash."""
        s1 = self._make_sitemap([PageData(path="/", url="https://example.com/")])
        s2 = self._make_sitemap([PageData(path="/", url="https://example.com/")])
        assert compute_sitemap_hash(s1) == compute_sitemap_hash(s2)

    def test_different_pages_different_hash(self) -> None:
        """Different pages produce different hashes."""
        s1 = self._make_sitemap([PageData(path="/", url="https://example.com/")])
        s2 = self._make_sitemap([PageData(path="/about", url="https://example.com/about")])
        assert compute_sitemap_hash(s1) != compute_sitemap_hash(s2)

    def test_hash_is_short(self) -> None:
        """Hash is truncated to 16 chars."""
        s = self._make_sitemap()
        h = compute_sitemap_hash(s)
        assert len(h) == 16
        assert h.isalnum()

    def test_empty_sitemap(self) -> None:
        """Empty sitemap still produces a valid hash."""
        s = self._make_sitemap()
        h = compute_sitemap_hash(s)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_api_endpoints_affect_hash(self) -> None:
        """API endpoints change the hash."""
        s1 = SiteMap(base_url="https://example.com", pages=[], api_endpoints=[])
        s2 = SiteMap(
            base_url="https://example.com",
            pages=[],
            api_endpoints=[ApiCallInfo(url="https://example.com/api/users", method="GET")],
        )
        assert compute_sitemap_hash(s1) != compute_sitemap_hash(s2)
