"""Crawler facade — wires browser, navigator, extractor, and network interceptor."""

from __future__ import annotations

import asyncio
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

    from breakthevibe.generator.rules.engine import RulesEngine
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
        rules: RulesEngine | None = None,
    ) -> None:
        self._browser = browser or BrowserManager(headless=headless)
        self._artifacts = artifacts
        self._max_depth = max_depth
        self._skip_patterns = skip_patterns or []
        self._project_id = project_id
        self._run_id = run_id
        self._rules = rules

        # Apply rules overrides
        if rules:
            self._max_depth = rules.get_max_depth()
            skip_urls = rules.config.crawl.skip_urls
            if skip_urls:
                self._skip_patterns = list(set(self._skip_patterns + skip_urls))

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

            # Install network interception (wrap async callback properly)
            page.on("request", interceptor.on_request)
            page.on("response", lambda r: asyncio.ensure_future(interceptor.on_response(r)))

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

                # Enqueue SPA route changes discovered via History API
                spa_changes = await navigator.get_spa_route_changes(page)
                for spa_url in spa_changes:
                    if navigator.should_visit(spa_url) and navigator.is_within_depth(depth + 1):
                        queue.append((spa_url, depth + 1))
                        logger.debug("spa_route_enqueued", url=spa_url, depth=depth + 1)

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

        # Handle interaction rules (cookie banners, modals)
        await self._handle_interactions(page)

        # Scroll for dynamic content
        await self._scroll_for_content(page)

        # Click interactive elements to discover SPA routes
        await self._click_interactive_elements(page, navigator)

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

    async def _handle_interactions(self, page: Page) -> None:
        """Handle cookie banners, modals, etc. based on rules."""
        if not self._rules:
            return

        # Dismiss cookie banners
        if self._rules.get_cookie_banner_action() == "dismiss":
            for selector in [
                "button:has-text('Accept')",
                "button:has-text('OK')",
                "button:has-text('Got it')",
                "[class*='cookie'] button",
                "[id*='cookie'] button",
            ]:
                try:
                    locator = page.locator(selector).first
                    if await locator.is_visible(timeout=1000):
                        await locator.click()
                        await page.wait_for_timeout(DEFAULT_AFTER_CLICK_WAIT_MS)
                        logger.debug("cookie_banner_dismissed", selector=selector)
                        break
                except Exception:
                    continue

        # Close modals
        if self._rules.get_modal_action() == "close_on_appear":
            for selector in [
                "[role='dialog'] button[aria-label='Close']",
                ".modal-close",
                "[class*='modal'] button:has-text('Close')",
            ]:
                try:
                    locator = page.locator(selector).first
                    if await locator.is_visible(timeout=500):
                        await locator.click()
                        await page.wait_for_timeout(DEFAULT_AFTER_CLICK_WAIT_MS)
                        logger.debug("modal_closed", selector=selector)
                        break
                except Exception:
                    continue

    async def _click_interactive_elements(self, page: Page, navigator: Navigator) -> None:
        """Click navigation elements to trigger SPA route changes."""
        nav_selectors = [
            "nav a[href]",
            "[role='navigation'] a[href]",
            "header a[href]",
        ]
        for selector in nav_selectors:
            try:
                links = page.locator(selector)
                count = await links.count()
                # Limit to 10 nav links per selector to avoid excessive clicking
                for i in range(min(count, 10)):
                    try:
                        link = links.nth(i)
                        if not await link.is_visible():
                            continue
                        await link.click(timeout=2000)
                        await page.wait_for_timeout(DEFAULT_AFTER_CLICK_WAIT_MS)
                        # Navigate back for the next click
                        await page.go_back(timeout=DEFAULT_PAGE_LOAD_TIMEOUT_MS)
                        await page.wait_for_timeout(DEFAULT_AFTER_CLICK_WAIT_MS)
                    except Exception:
                        continue
            except Exception:
                continue

    async def _scroll_for_content(self, page: Page) -> None:
        """Scroll incrementally to trigger lazy/infinite-scroll content."""
        max_scrolls = MAX_SCROLL_ATTEMPTS
        if self._rules:
            action = self._rules.get_infinite_scroll_action()
            # Parse "scroll_N_times" pattern
            if action.startswith("scroll_") and action.endswith("_times"):
                parts = action.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    max_scrolls = int(parts[1])

        for i in range(max_scrolls):
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
