from unittest.mock import AsyncMock

import pytest

from breakthevibe.crawler.extractor import ComponentExtractor
from breakthevibe.models.domain import ComponentInfo

MOCK_DOM_RESULT = [
    {
        "tag": "button",
        "text": "Submit",
        "aria_role": "button",
        "is_interactive": True,
        "test_id": "submit-btn",
        "css_selector": "form > button.primary",
        "aria_name": "Submit",
        "bounding_box": {"x": 100, "y": 200, "width": 80, "height": 40},
        "visible": True,
    },
    {
        "tag": "input",
        "text": "",
        "aria_role": "textbox",
        "is_interactive": True,
        "test_id": None,
        "css_selector": "input[type='email']",
        "aria_name": "Email address",
        "bounding_box": {"x": 100, "y": 150, "width": 200, "height": 30},
        "visible": True,
    },
    {
        "tag": "nav",
        "text": "",
        "aria_role": "navigation",
        "is_interactive": False,
        "test_id": "main-nav",
        "css_selector": "nav.main-navigation",
        "aria_name": None,
        "bounding_box": {"x": 0, "y": 0, "width": 1280, "height": 60},
        "visible": True,
    },
]


@pytest.mark.unit
class TestComponentExtractor:
    @pytest.mark.asyncio
    async def test_extract_components_returns_list(self) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=MOCK_DOM_RESULT)

        extractor = ComponentExtractor()
        components = await extractor.extract_components(mock_page)

        assert len(components) == 3
        assert all(isinstance(c, ComponentInfo) for c in components)

    @pytest.mark.asyncio
    async def test_extract_builds_selectors(self) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=MOCK_DOM_RESULT)

        extractor = ComponentExtractor()
        components = await extractor.extract_components(mock_page)

        submit_btn = components[0]
        assert submit_btn.element_type == "button"
        assert submit_btn.text_content == "Submit"
        assert len(submit_btn.selectors) >= 2

    @pytest.mark.asyncio
    async def test_extract_interactions(self) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=MOCK_DOM_RESULT)

        extractor = ComponentExtractor()
        interactions = await extractor.extract_interactions(mock_page)

        interactive = [i for i in interactions if i.action_type in ("click", "input")]
        assert len(interactive) >= 2  # button + input

    @pytest.mark.asyncio
    async def test_extract_handles_empty_page(self) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        extractor = ComponentExtractor()
        components = await extractor.extract_components(mock_page)
        assert components == []

    @pytest.mark.asyncio
    async def test_take_screenshot(self) -> None:
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"png_data")

        extractor = ComponentExtractor()
        data = await extractor.take_screenshot(mock_page, "/tmp/test.png")
        mock_page.screenshot.assert_called_once_with(path="/tmp/test.png", full_page=True)
        assert data == b"png_data"
