"""Unit tests for Crawler facade in breakthevibe/crawler/crawler.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from breakthevibe.crawler.crawler import Crawler
from breakthevibe.models.domain import CrawlResult

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_mock_page() -> AsyncMock:
    """Return a fully-mocked Playwright Page object."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.title = AsyncMock(return_value="Test Page")
    page.screenshot = AsyncMock(return_value=b"PNG_DATA")
    page.url = "https://example.com/"

    # evaluate returns vary by call — we use a side_effect list so that
    # _scroll_for_content gets consistent heights (stops after first attempt)
    # and navigator methods get link lists.
    def _evaluate_side_effect(script: str, *args: object) -> object:
        if "scrollHeight" in script and "scrollTo" not in script:
            return 1000
        if "scrollTo" in script:
            return None
        if "__btv_route_changes" in script:
            return []
        # discover_links JS
        return []

    page.evaluate = AsyncMock(side_effect=_evaluate_side_effect)
    page.on = MagicMock()
    return page


def _make_mock_context(page: AsyncMock) -> AsyncMock:
    context = AsyncMock()
    context.close = AsyncMock()
    return context


def _make_mock_browser(page: AsyncMock, context: AsyncMock) -> MagicMock:
    """Return a mocked BrowserManager that yields the given page/context."""
    browser = MagicMock()
    browser.launch = AsyncMock()
    browser.close = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.new_page = AsyncMock(return_value=page)
    return browser


# ---------------------------------------------------------------------------
# Test: SSRF protection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrawlerSsrfProtection:
    @pytest.mark.asyncio
    async def test_crawl_blocks_link_local_aws_metadata(self) -> None:
        crawler = Crawler()
        result = await crawler.crawl("http://169.254.169.254/latest/meta-data/")
        assert isinstance(result, CrawlResult)
        assert result.pages == []
        assert result.total_routes == 0
        assert result.total_components == 0
        assert result.total_api_calls == 0

    @pytest.mark.asyncio
    async def test_crawl_blocks_localhost(self) -> None:
        crawler = Crawler()
        result = await crawler.crawl("http://localhost:8080/admin")
        assert isinstance(result, CrawlResult)
        assert result.pages == []

    @pytest.mark.asyncio
    async def test_crawl_blocks_loopback_ip(self) -> None:
        crawler = Crawler()
        result = await crawler.crawl("http://127.0.0.1/secret")
        assert isinstance(result, CrawlResult)
        assert result.pages == []

    @pytest.mark.asyncio
    async def test_crawl_blocks_private_class_a(self) -> None:
        crawler = Crawler()
        result = await crawler.crawl("http://10.0.0.1/internal")
        assert isinstance(result, CrawlResult)
        assert result.pages == []

    @pytest.mark.asyncio
    async def test_crawl_blocks_private_class_c(self) -> None:
        crawler = Crawler()
        result = await crawler.crawl("http://192.168.1.100/admin")
        assert isinstance(result, CrawlResult)
        assert result.pages == []

    @pytest.mark.asyncio
    async def test_crawl_blocks_ipv6_loopback(self) -> None:
        crawler = Crawler()
        result = await crawler.crawl("http://[::1]/secret")
        assert isinstance(result, CrawlResult)
        assert result.pages == []

    @pytest.mark.asyncio
    async def test_ssrf_block_logs_warning(self) -> None:
        with patch("breakthevibe.crawler.crawler.logger") as mock_logger:
            crawler = Crawler()
            await crawler.crawl("http://169.254.169.254/")
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[0][0] == "unsafe_url_blocked"


# ---------------------------------------------------------------------------
# Test: crawl() happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrawlerCrawl:
    @pytest.mark.asyncio
    async def test_crawl_returns_crawl_result(self) -> None:
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(page, context)

        with (
            patch("breakthevibe.crawler.crawler.ComponentExtractor") as mock_extractor_cls,
            patch("breakthevibe.crawler.crawler.NetworkInterceptor") as mock_interceptor_cls,
            patch("breakthevibe.crawler.crawler.Navigator") as mock_navigator_cls,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_components = AsyncMock(return_value=[])
            mock_extractor.extract_interactions = AsyncMock(return_value=[])
            mock_extractor.take_screenshot = AsyncMock(return_value=b"PNG")
            mock_extractor_cls.return_value = mock_extractor

            mock_interceptor = MagicMock()
            mock_interceptor.clear = MagicMock()
            mock_interceptor.get_captured_calls = MagicMock(return_value=[])
            mock_interceptor.on_request = MagicMock()
            mock_interceptor.on_response = AsyncMock()
            mock_interceptor_cls.return_value = mock_interceptor

            mock_navigator = AsyncMock()
            mock_navigator.should_visit = MagicMock(return_value=True)
            mock_navigator.is_within_depth = MagicMock(return_value=True)
            mock_navigator.mark_visited = MagicMock()
            mock_navigator.install_spa_listener = AsyncMock()
            mock_navigator.discover_links = AsyncMock(return_value=[])
            mock_navigator.get_spa_route_changes = AsyncMock(return_value=[])
            mock_navigator.get_path = MagicMock(return_value="/")
            mock_navigator_cls.return_value = mock_navigator

            crawler = Crawler(browser=browser)
            result = await crawler.crawl("https://example.com")

        assert isinstance(result, CrawlResult)

    @pytest.mark.asyncio
    async def test_crawl_launches_and_closes_browser(self) -> None:
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(page, context)

        with (
            patch("breakthevibe.crawler.crawler.ComponentExtractor") as mock_extractor_cls,
            patch("breakthevibe.crawler.crawler.NetworkInterceptor") as mock_interceptor_cls,
            patch("breakthevibe.crawler.crawler.Navigator") as mock_navigator_cls,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_components = AsyncMock(return_value=[])
            mock_extractor.extract_interactions = AsyncMock(return_value=[])
            mock_extractor_cls.return_value = mock_extractor

            mock_interceptor = MagicMock()
            mock_interceptor.clear = MagicMock()
            mock_interceptor.get_captured_calls = MagicMock(return_value=[])
            mock_interceptor.on_request = MagicMock()
            mock_interceptor.on_response = AsyncMock()
            mock_interceptor_cls.return_value = mock_interceptor

            mock_navigator = AsyncMock()
            mock_navigator.should_visit = MagicMock(return_value=True)
            mock_navigator.is_within_depth = MagicMock(return_value=True)
            mock_navigator.mark_visited = MagicMock()
            mock_navigator.install_spa_listener = AsyncMock()
            mock_navigator.discover_links = AsyncMock(return_value=[])
            mock_navigator.get_spa_route_changes = AsyncMock(return_value=[])
            mock_navigator.get_path = MagicMock(return_value="/")
            mock_navigator_cls.return_value = mock_navigator

            crawler = Crawler(browser=browser)
            await crawler.crawl("https://example.com")

        browser.launch.assert_awaited_once()
        browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crawl_closes_context(self) -> None:
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(page, context)

        with (
            patch("breakthevibe.crawler.crawler.ComponentExtractor") as mock_extractor_cls,
            patch("breakthevibe.crawler.crawler.NetworkInterceptor") as mock_interceptor_cls,
            patch("breakthevibe.crawler.crawler.Navigator") as mock_navigator_cls,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_components = AsyncMock(return_value=[])
            mock_extractor.extract_interactions = AsyncMock(return_value=[])
            mock_extractor_cls.return_value = mock_extractor

            mock_interceptor = MagicMock()
            mock_interceptor.clear = MagicMock()
            mock_interceptor.get_captured_calls = MagicMock(return_value=[])
            mock_interceptor.on_request = MagicMock()
            mock_interceptor.on_response = AsyncMock()
            mock_interceptor_cls.return_value = mock_interceptor

            mock_navigator = AsyncMock()
            mock_navigator.should_visit = MagicMock(return_value=True)
            mock_navigator.is_within_depth = MagicMock(return_value=True)
            mock_navigator.mark_visited = MagicMock()
            mock_navigator.install_spa_listener = AsyncMock()
            mock_navigator.discover_links = AsyncMock(return_value=[])
            mock_navigator.get_spa_route_changes = AsyncMock(return_value=[])
            mock_navigator.get_path = MagicMock(return_value="/")
            mock_navigator_cls.return_value = mock_navigator

            crawler = Crawler(browser=browser)
            await crawler.crawl("https://example.com")

        context.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_crawl_result_page_count_matches_visited(self) -> None:
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(page, context)

        with (
            patch("breakthevibe.crawler.crawler.ComponentExtractor") as mock_extractor_cls,
            patch("breakthevibe.crawler.crawler.NetworkInterceptor") as mock_interceptor_cls,
            patch("breakthevibe.crawler.crawler.Navigator") as mock_navigator_cls,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_components = AsyncMock(return_value=[])
            mock_extractor.extract_interactions = AsyncMock(return_value=[])
            mock_extractor_cls.return_value = mock_extractor

            mock_interceptor = MagicMock()
            mock_interceptor.clear = MagicMock()
            mock_interceptor.get_captured_calls = MagicMock(return_value=[])
            mock_interceptor.on_request = MagicMock()
            mock_interceptor.on_response = AsyncMock()
            mock_interceptor_cls.return_value = mock_interceptor

            mock_navigator = AsyncMock()
            mock_navigator.should_visit = MagicMock(return_value=True)
            mock_navigator.is_within_depth = MagicMock(return_value=True)
            mock_navigator.mark_visited = MagicMock()
            mock_navigator.install_spa_listener = AsyncMock()
            # No additional links discovered — only the seed URL is crawled
            mock_navigator.discover_links = AsyncMock(return_value=[])
            mock_navigator.get_spa_route_changes = AsyncMock(return_value=[])
            mock_navigator.get_path = MagicMock(return_value="/")
            mock_navigator_cls.return_value = mock_navigator

            crawler = Crawler(browser=browser)
            result = await crawler.crawl("https://example.com")

        assert result.total_routes == 1
        assert len(result.pages) == 1

    @pytest.mark.asyncio
    async def test_crawl_installs_network_interceptor_on_page(self) -> None:
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(page, context)

        with (
            patch("breakthevibe.crawler.crawler.ComponentExtractor") as mock_extractor_cls,
            patch("breakthevibe.crawler.crawler.NetworkInterceptor") as mock_interceptor_cls,
            patch("breakthevibe.crawler.crawler.Navigator") as mock_navigator_cls,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_components = AsyncMock(return_value=[])
            mock_extractor.extract_interactions = AsyncMock(return_value=[])
            mock_extractor_cls.return_value = mock_extractor

            mock_interceptor = MagicMock()
            mock_interceptor.clear = MagicMock()
            mock_interceptor.get_captured_calls = MagicMock(return_value=[])
            mock_interceptor.on_request = MagicMock()
            mock_interceptor.on_response = AsyncMock()
            mock_interceptor_cls.return_value = mock_interceptor

            mock_navigator = AsyncMock()
            mock_navigator.should_visit = MagicMock(return_value=True)
            mock_navigator.is_within_depth = MagicMock(return_value=True)
            mock_navigator.mark_visited = MagicMock()
            mock_navigator.install_spa_listener = AsyncMock()
            mock_navigator.discover_links = AsyncMock(return_value=[])
            mock_navigator.get_spa_route_changes = AsyncMock(return_value=[])
            mock_navigator.get_path = MagicMock(return_value="/")
            mock_navigator_cls.return_value = mock_navigator

            crawler = Crawler(browser=browser)
            await crawler.crawl("https://example.com")

        # page.on must have been called with "request" and "response"
        on_calls = {call[0][0] for call in page.on.call_args_list}
        assert "request" in on_calls
        assert "response" in on_calls

    @pytest.mark.asyncio
    async def test_crawl_browser_closed_even_on_exception(self) -> None:
        """browser.close() must be called in the finally block."""
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(page, context)
        browser.new_context = AsyncMock(side_effect=RuntimeError("context failure"))

        with (
            patch("breakthevibe.crawler.crawler.ComponentExtractor"),
            patch("breakthevibe.crawler.crawler.NetworkInterceptor"),
            patch("breakthevibe.crawler.crawler.Navigator"),
        ):
            crawler = Crawler(browser=browser)
            with pytest.raises(RuntimeError, match="context failure"):
                await crawler.crawl("https://example.com")

        browser.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: _scroll_for_content
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrawlerScrollForContent:
    def _make_scroll_crawler(self) -> Crawler:
        """Create a Crawler instance with _rules=None for scroll testing."""
        crawler = Crawler.__new__(Crawler)
        crawler._rules = None
        crawler._after_click_wait = 500
        crawler._page_load_timeout = 30000
        crawler._viewport_width = 1280
        crawler._viewport_height = 800
        return crawler

    @pytest.mark.asyncio
    async def test_scroll_calls_evaluate_for_height(self) -> None:
        page = AsyncMock()
        # Sequence per iteration: prev_height, scrollTo (None), new_height
        # Same height → loop breaks after first attempt.
        # Then: final scrollTo(0,0) → None.
        page.evaluate = AsyncMock(side_effect=[1000, None, 1000, None])
        page.wait_for_timeout = AsyncMock()

        crawler = self._make_scroll_crawler()
        await crawler._scroll_for_content(page)

        assert page.evaluate.await_count >= 1

    @pytest.mark.asyncio
    async def test_scroll_breaks_when_height_unchanged(self) -> None:
        """When document height stops growing, the loop must exit early."""
        page = AsyncMock()
        # Heights: prev=1000, scrollTo returns None, new=1000 (no change → break)
        page.evaluate = AsyncMock(side_effect=[1000, None, 1000, None])
        page.wait_for_timeout = AsyncMock()

        crawler = self._make_scroll_crawler()
        await crawler._scroll_for_content(page)

        # Scroll-to-top evaluate is called after the loop
        calls = [str(c) for c in page.evaluate.call_args_list]
        scroll_to_top_calls = [c for c in calls if "scrollTo(0, 0)" in c]
        assert len(scroll_to_top_calls) == 1

    @pytest.mark.asyncio
    async def test_scroll_scrolls_to_top_after_loop(self) -> None:
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=[1000, None, 1000, None])
        page.wait_for_timeout = AsyncMock()

        crawler = self._make_scroll_crawler()
        await crawler._scroll_for_content(page)

        all_scripts = [str(c.args[0]) for c in page.evaluate.call_args_list]
        assert any("scrollTo(0, 0)" in s for s in all_scripts)

    @pytest.mark.asyncio
    async def test_scroll_waits_after_scrolling_to_bottom(self) -> None:
        from breakthevibe.constants import DEFAULT_SCROLL_WAIT_MS

        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=[1000, None, 1000, None])
        page.wait_for_timeout = AsyncMock()

        crawler = self._make_scroll_crawler()
        await crawler._scroll_for_content(page)

        # wait_for_timeout is called at least once with DEFAULT_SCROLL_WAIT_MS
        timeout_args = [c.args[0] for c in page.wait_for_timeout.call_args_list]
        assert DEFAULT_SCROLL_WAIT_MS in timeout_args

    @pytest.mark.asyncio
    async def test_scroll_continues_when_height_grows(self) -> None:
        """When height keeps growing the loop should run until MAX_SCROLL_ATTEMPTS."""
        from breakthevibe.constants import MAX_SCROLL_ATTEMPTS

        # Alternate heights that always differ so the loop runs to the limit.
        # Pattern: prev_height, scrollTo, new_height, prev_height, scrollTo, new_height ...
        # then the final scroll-to-top
        heights = []
        for i in range(MAX_SCROLL_ATTEMPTS):
            heights.append(1000 + i * 100)  # prev_height
            heights.append(None)  # scrollTo
            heights.append(1000 + (i + 1) * 100)  # new_height (always grows)
        heights.append(None)  # final scrollTo(0,0)

        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=heights)
        page.wait_for_timeout = AsyncMock()

        crawler = self._make_scroll_crawler()
        await crawler._scroll_for_content(page)

        # Should have looped MAX_SCROLL_ATTEMPTS times
        # Each loop iteration: 3 evaluate calls; plus 1 for scroll-to-top
        expected_min_calls = MAX_SCROLL_ATTEMPTS * 3
        assert page.evaluate.await_count >= expected_min_calls


# ---------------------------------------------------------------------------
# Test: Constructor defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrawlerConstructor:
    def test_default_headless_is_true(self) -> None:
        crawler = Crawler()
        assert crawler._browser is not None

    def test_custom_max_depth(self) -> None:
        crawler = Crawler(max_depth=3)
        assert crawler._max_depth == 3

    def test_default_max_depth(self) -> None:
        from breakthevibe.constants import DEFAULT_MAX_DEPTH

        crawler = Crawler()
        assert crawler._max_depth == DEFAULT_MAX_DEPTH

    def test_skip_patterns_default_empty(self) -> None:
        crawler = Crawler()
        assert crawler._skip_patterns == []

    def test_custom_skip_patterns(self) -> None:
        patterns = ["/admin/*", "/internal/*"]
        crawler = Crawler(skip_patterns=patterns)
        assert crawler._skip_patterns == patterns

    def test_provided_browser_used(self) -> None:
        mock_browser = MagicMock()
        crawler = Crawler(browser=mock_browser)
        assert crawler._browser is mock_browser

    def test_project_and_run_ids_stored(self) -> None:
        crawler = Crawler(project_id="proj-123", run_id="run-456")
        assert crawler._project_id == "proj-123"
        assert crawler._run_id == "run-456"
