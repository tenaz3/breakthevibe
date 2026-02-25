from unittest.mock import AsyncMock, patch

import pytest

from breakthevibe.crawler.browser import BrowserManager


@pytest.mark.unit
class TestBrowserManager:
    @pytest.mark.asyncio
    async def test_launch_creates_browser(self) -> None:
        with patch("breakthevibe.crawler.browser.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            manager = BrowserManager(headless=True)
            await manager.launch()

            assert manager._browser is not None

    @pytest.mark.asyncio
    async def test_new_context_with_video(self) -> None:
        with patch("breakthevibe.crawler.browser.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            manager = BrowserManager(headless=True)
            await manager.launch()
            await manager.new_context(video_dir="/tmp/videos")

            call_kwargs = mock_browser.new_context.call_args.kwargs
            assert call_kwargs["record_video_dir"] == "/tmp/videos"

    @pytest.mark.asyncio
    async def test_new_context_without_browser_raises(self) -> None:
        manager = BrowserManager()
        with pytest.raises(RuntimeError, match="not launched"):
            await manager.new_context()
