"""Playwright browser management with video recording."""

from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from breakthevibe.constants import DEFAULT_VIEWPORT_HEIGHT, DEFAULT_VIEWPORT_WIDTH


class BrowserManager:
    def __init__(self, headless: bool = True):
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def launch(self) -> None:
        """Launch the browser."""
        self._playwright = await async_playwright().__aenter__()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

    async def new_context(
        self,
        video_dir: str | None = None,
        viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
        viewport_height: int = DEFAULT_VIEWPORT_HEIGHT,
    ) -> BrowserContext:
        """Create a new browser context with optional video recording."""
        if not self._browser:
            raise RuntimeError("Browser not launched. Call launch() first.")

        kwargs: dict[str, Any] = {
            "viewport": {"width": viewport_width, "height": viewport_height},
        }
        if video_dir:
            kwargs["record_video_dir"] = video_dir
            kwargs["record_video_size"] = {"width": viewport_width, "height": viewport_height}

        return await self._browser.new_context(**kwargs)

    async def new_page(self, context: BrowserContext) -> Page:
        """Create a new page in the given context."""
        return await context.new_page()

    async def close(self) -> None:
        """Close browser and playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.__aexit__(None, None, None)
