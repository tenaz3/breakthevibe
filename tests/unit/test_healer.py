from unittest.mock import AsyncMock, MagicMock

import pytest

from breakthevibe.models.domain import ResilientSelector
from breakthevibe.runner.healer import HealResult, SelectorHealer
from breakthevibe.types import SelectorStrategy


@pytest.mark.unit
class TestSelectorHealer:
    @pytest.fixture()
    def healer(self) -> SelectorHealer:
        return SelectorHealer()

    @pytest.fixture()
    def selector_chain(self) -> list[ResilientSelector]:
        return [
            ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="submit-btn"),
            ResilientSelector(strategy=SelectorStrategy.ROLE, value="button", name="Submit"),
            ResilientSelector(strategy=SelectorStrategy.TEXT, value="Submit"),
            ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn-submit"),
        ]

    @pytest.mark.asyncio
    async def test_first_selector_works(
        self,
        healer: SelectorHealer,
        selector_chain: list[ResilientSelector],
    ) -> None:
        """When the first selector works, no healing needed."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_page.get_by_test_id.return_value = mock_locator

        result = await healer.find_element(mock_page, selector_chain)
        assert isinstance(result, HealResult)
        assert result.found is True
        assert result.healed is False
        assert result.used_selector == selector_chain[0]

    @pytest.mark.asyncio
    async def test_heals_to_second_selector(
        self,
        healer: SelectorHealer,
        selector_chain: list[ResilientSelector],
    ) -> None:
        """When first selector fails, falls back to second."""
        mock_page = MagicMock()

        mock_locator_fail = MagicMock()
        mock_locator_fail.count = AsyncMock(return_value=0)

        mock_locator_ok = MagicMock()
        mock_locator_ok.count = AsyncMock(return_value=1)

        mock_page.get_by_test_id.return_value = mock_locator_fail
        mock_page.get_by_role.return_value = mock_locator_ok

        result = await healer.find_element(mock_page, selector_chain)
        assert result.found is True
        assert result.healed is True
        assert result.used_selector == selector_chain[1]
        assert result.original_selector == selector_chain[0]

    @pytest.mark.asyncio
    async def test_all_selectors_fail(
        self,
        healer: SelectorHealer,
        selector_chain: list[ResilientSelector],
    ) -> None:
        """When all selectors fail, result.found is False."""
        mock_page = MagicMock()
        mock_locator_fail = MagicMock()
        mock_locator_fail.count = AsyncMock(return_value=0)

        mock_page.get_by_test_id.return_value = mock_locator_fail
        mock_page.get_by_role.return_value = mock_locator_fail
        mock_page.get_by_text.return_value = mock_locator_fail
        mock_page.locator.return_value = mock_locator_fail

        result = await healer.find_element(mock_page, selector_chain)
        assert result.found is False
        assert result.healed is False
        assert result.used_selector is None

    @pytest.mark.asyncio
    async def test_heals_to_css_fallback(
        self,
        healer: SelectorHealer,
        selector_chain: list[ResilientSelector],
    ) -> None:
        """Falls all the way to CSS selector."""
        mock_page = MagicMock()

        mock_fail = MagicMock()
        mock_fail.count = AsyncMock(return_value=0)

        mock_ok = MagicMock()
        mock_ok.count = AsyncMock(return_value=1)

        mock_page.get_by_test_id.return_value = mock_fail
        mock_page.get_by_role.return_value = mock_fail
        mock_page.get_by_text.return_value = mock_fail
        mock_page.locator.return_value = mock_ok

        result = await healer.find_element(mock_page, selector_chain)
        assert result.found is True
        assert result.healed is True
        assert result.used_selector.strategy == SelectorStrategy.CSS

    def test_heal_result_warning_message(self) -> None:
        result = HealResult(
            found=True,
            healed=True,
            used_selector=ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn"),
            original_selector=ResilientSelector(
                strategy=SelectorStrategy.TEST_ID, value="submit-btn"
            ),
        )
        msg = result.warning_message()
        assert "test_id" in msg
        assert "css" in msg
        assert "submit-btn" in msg

    def test_heal_result_no_warning_when_not_healed(self) -> None:
        result = HealResult(
            found=True,
            healed=False,
            used_selector=ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="btn"),
        )
        assert result.warning_message() is None

    @pytest.mark.asyncio
    async def test_empty_selector_chain(self, healer: SelectorHealer) -> None:
        mock_page = MagicMock()
        result = await healer.find_element(mock_page, [])
        assert result.found is False

    @pytest.mark.asyncio
    async def test_handles_locator_exception(self, healer: SelectorHealer) -> None:
        """If a locator throws, treat it as not found and continue."""
        mock_page = MagicMock()

        mock_error_locator = MagicMock()
        mock_error_locator.count = AsyncMock(side_effect=Exception("element detached"))

        mock_ok_locator = MagicMock()
        mock_ok_locator.count = AsyncMock(return_value=1)

        mock_page.get_by_test_id.return_value = mock_error_locator
        mock_page.get_by_role.return_value = mock_ok_locator

        chain = [
            ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="btn"),
            ResilientSelector(strategy=SelectorStrategy.ROLE, value="button", name="Submit"),
        ]
        result = await healer.find_element(mock_page, chain)
        assert result.found is True
        assert result.healed is True
