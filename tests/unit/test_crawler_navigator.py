from unittest.mock import AsyncMock

import pytest

from breakthevibe.crawler.navigator import Navigator


@pytest.mark.unit
class TestNavigator:
    def test_init_with_config(self) -> None:
        nav = Navigator(
            base_url="https://example.com",
            max_depth=3,
            skip_patterns=["/admin/*"],
        )
        assert nav._base_url == "https://example.com"
        assert nav._max_depth == 3
        assert nav._visited == set()

    def test_should_skip_matching_pattern(self) -> None:
        nav = Navigator(
            base_url="https://example.com",
            skip_patterns=["/admin/*", "/api/internal/*"],
        )
        assert nav.should_skip("/admin/settings") is True
        assert nav.should_skip("/api/internal/debug") is True
        assert nav.should_skip("/products") is False

    def test_should_skip_already_visited(self) -> None:
        nav = Navigator(base_url="https://example.com")
        nav._visited.add("https://example.com/products")
        assert nav.should_visit("https://example.com/products") is False

    def test_should_visit_same_domain(self) -> None:
        nav = Navigator(base_url="https://example.com")
        assert nav.should_visit("https://example.com/about") is True
        assert nav.should_visit("https://other-site.com/page") is False

    def test_respects_max_depth(self) -> None:
        nav = Navigator(base_url="https://example.com", max_depth=2)
        assert nav.is_within_depth(0) is True
        assert nav.is_within_depth(2) is True
        assert nav.is_within_depth(3) is False

    @pytest.mark.asyncio
    async def test_discover_links_from_page(self) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(
            return_value=[
                "https://example.com/about",
                "https://example.com/products",
                "https://other.com/external",
                "javascript:void(0)",
            ]
        )

        nav = Navigator(base_url="https://example.com")
        links = await nav.discover_links(mock_page)

        assert "https://example.com/about" in links
        assert "https://example.com/products" in links
        assert "https://other.com/external" not in links
        assert "javascript:void(0)" not in links

    @pytest.mark.asyncio
    async def test_get_current_url(self) -> None:
        nav = Navigator(base_url="https://example.com")
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/products/123"

        new_url = await nav.get_current_url(mock_page)
        assert new_url == "https://example.com/products/123"

    def test_mark_visited(self) -> None:
        nav = Navigator(base_url="https://example.com")
        nav.mark_visited("https://example.com/about")
        assert "https://example.com/about" in nav._visited
        assert nav.should_visit("https://example.com/about") is False

    def test_get_path_from_url(self) -> None:
        nav = Navigator(base_url="https://example.com")
        assert nav.get_path("https://example.com/products?page=1") == "/products"
        assert nav.get_path("https://example.com/") == "/"
        assert nav.get_path("https://example.com") == "/"
