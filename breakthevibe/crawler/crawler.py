"""Crawler facade — wires browser, navigator, extractor, and network interceptor."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from breakthevibe.constants import (
    DEFAULT_AFTER_CLICK_WAIT_MS,
    DEFAULT_MAX_DEPTH,
    DEFAULT_PAGE_LOAD_TIMEOUT_MS,
    DEFAULT_SCROLL_WAIT_MS,
    MAX_SCROLL_ATTEMPTS,
)
from breakthevibe.crawler.browser import BrowserManager
from breakthevibe.crawler.extractor import ComponentExtractor
from breakthevibe.crawler.navigator import Navigator
from breakthevibe.crawler.network import NetworkInterceptor
from breakthevibe.models.domain import ApiCallInfo, CrawlResult, PageData
from breakthevibe.utils.sanitize import is_safe_url

if TYPE_CHECKING:
    from playwright.async_api import Page

    from breakthevibe.storage.artifacts import ArtifactStore

logger = structlog.get_logger(__name__)


class Crawler:
    """Orchestrates all crawler sub-modules to crawl a target site."""

    def __init__(
        self,
        browser: BrowserManager | None = None,
        artifacts: ArtifactStore | None = None,
        headless: bool = True,
        max_depth: int = DEFAULT_MAX_DEPTH,
        skip_patterns: list[str] | None = None,
        project_id: str = "",
        run_id: str = "",
    ) -> None:
        self._browser = browser or BrowserManager(headless=headless)
        self._artifacts = artifacts
        self._max_depth = max_depth
        self._skip_patterns = skip_patterns or []
        self._project_id = project_id
        self._run_id = run_id

    async def crawl(self, url: str) -> CrawlResult:
        """Crawl a website starting from the given URL.

        Returns a CrawlResult with page data, components, and API calls.
        """
        if not is_safe_url(url):
            logger.warning("unsafe_url_blocked", url=url)
            return CrawlResult(pages=[], total_routes=0, total_components=0, total_api_calls=0)

        navigator = Navigator(
            base_url=url,
            max_depth=self._max_depth,
            skip_patterns=self._skip_patterns,
        )
        extractor = ComponentExtractor()
        interceptor = NetworkInterceptor()

        pages: list[PageData] = []
        queue: list[tuple[str, int]] = [(url, 0)]

        await self._browser.launch()
        try:
            video_dir = None
            if self._artifacts and self._project_id and self._run_id:
                videos_dir = self._artifacts.get_run_dir(self._project_id, self._run_id) / "videos"
                videos_dir.mkdir(parents=True, exist_ok=True)
                video_dir = str(videos_dir)

            context = await self._browser.new_context(video_dir=video_dir)
            page = await self._browser.new_page(context)

            # Install network interception
            page.on("request", interceptor.on_request)
            page.on("response", interceptor.on_response)

            while queue:
                current_url, depth = queue.pop(0)
                if not navigator.should_visit(current_url):
                    continue
                if not navigator.is_within_depth(depth):
                    continue

                navigator.mark_visited(current_url)
                page_data = await self._crawl_page(
                    page, current_url, navigator, extractor, interceptor, depth
                )
                pages.append(page_data)

                # Discover links for further crawling
                discovered = await navigator.discover_links(page)
                for link in discovered:
                    queue.append((link, depth + 1))

            await context.close()
        finally:
            await self._browser.close()

        total_components = sum(len(p.components) for p in pages)
        total_api_calls = sum(len(p.api_calls) for p in pages)

        logger.info(
            "crawl_complete",
            url=url,
            pages=len(pages),
            components=total_components,
            api_calls=total_api_calls,
        )

        return CrawlResult(
            pages=pages,
            total_routes=len(pages),
            total_components=total_components,
            total_api_calls=total_api_calls,
        )

    async def _crawl_page(
        self,
        page: Page,
        url: str,
        navigator: Navigator,
        extractor: ComponentExtractor,
        interceptor: NetworkInterceptor,
        depth: int,
    ) -> PageData:
        """Crawl a single page: navigate, install SPA listener, extract, screenshot."""
        logger.info("crawling_page", url=url, depth=depth)
        interceptor.clear()

        await page.goto(url, timeout=DEFAULT_PAGE_LOAD_TIMEOUT_MS)
        await page.wait_for_load_state("networkidle", timeout=DEFAULT_PAGE_LOAD_TIMEOUT_MS)
        await navigator.install_spa_listener(page)

        # Scroll for dynamic content
        await self._scroll_for_content(page)

        # Extract components and interactions
        components = await extractor.extract_components(page)
        interactions = await extractor.extract_interactions(page)

        # Capture screenshot
        screenshot_path = None
        if self._artifacts and self._project_id and self._run_id:
            step_name = navigator.get_path(url).replace("/", "_").strip("_") or "index"
            ss_data = await extractor.take_screenshot(page, "")
            saved = self._artifacts.save_screenshot(
                self._project_id, self._run_id, step_name, ss_data
            )
            screenshot_path = str(saved)

        # Build API call domain objects from interceptor data
        api_calls = [
            ApiCallInfo(
                url=call["url"],
                method=call["method"],
                status_code=call.get("status_code"),
                request_headers=call.get("request_headers", {}),
                response_headers=call.get("response_headers", {}),
                request_body=call.get("request_body"),
                response_body=call.get("response_body"),
            )
            for call in interceptor.get_captured_calls()
        ]

        # Detect links this page navigates to
        discovered = await navigator.discover_links(page)
        navigates_to = [navigator.get_path(link) for link in discovered]

        # Check for SPA route changes
        spa_changes = await navigator.get_spa_route_changes(page)
        if spa_changes:
            logger.debug("spa_routes_detected", url=url, changes=spa_changes)

        return PageData(
            url=url,
            path=navigator.get_path(url),
            title=await page.title(),
            components=components,
            interactions=interactions,
            api_calls=api_calls,
            screenshot_path=screenshot_path,
            navigates_to=navigates_to,
        )

    async def _scroll_for_content(self, page: Page) -> None:
        """Scroll incrementally to trigger lazy/infinite-scroll content."""
        for i in range(MAX_SCROLL_ATTEMPTS):
            prev_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(DEFAULT_SCROLL_WAIT_MS)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break
            logger.debug("scroll_loaded_content", attempt=i + 1, height=new_height)

        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(DEFAULT_AFTER_CLICK_WAIT_MS)
