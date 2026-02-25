"""Self-healing selector recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from breakthevibe.types import SelectorStrategy

if TYPE_CHECKING:
    from breakthevibe.models.domain import ResilientSelector

logger = structlog.get_logger(__name__)


@dataclass
class HealResult:
    """Result of a selector healing attempt."""

    found: bool
    healed: bool
    used_selector: ResilientSelector | None = None
    original_selector: ResilientSelector | None = None
    locator: Any = None

    def warning_message(self) -> str | None:
        """Generate a warning message if healing occurred."""
        if not self.healed or not self.used_selector or not self.original_selector:
            return None
        return (
            f"Selector healed: preferred {self.original_selector.strategy.value}"
            f"({self.original_selector.value}) failed, "
            f"fell back to {self.used_selector.strategy.value}"
            f"({self.used_selector.value})"
        )


class SelectorHealer:
    """Tries selectors in priority order, healing when preferred ones fail."""

    async def find_element(self, page: Any, selectors: list[ResilientSelector]) -> HealResult:
        """Try each selector in order until one finds an element."""
        if not selectors:
            return HealResult(found=False, healed=False)

        original = selectors[0]

        for i, selector in enumerate(selectors):
            try:
                locator = self._get_locator(page, selector)
                count = await locator.count()
                if count > 0:
                    healed = i > 0
                    if healed:
                        logger.warning(
                            "selector_healed",
                            original=f"{original.strategy.value}:{original.value}",
                            healed_to=f"{selector.strategy.value}:{selector.value}",
                        )
                    return HealResult(
                        found=True,
                        healed=healed,
                        used_selector=selector,
                        original_selector=original if healed else None,
                        locator=locator,
                    )
            except Exception:
                logger.debug(
                    "selector_error",
                    strategy=selector.strategy.value,
                    value=selector.value,
                )
                continue

        logger.error(
            "all_selectors_failed",
            selector_count=len(selectors),
            original=f"{original.strategy.value}:{original.value}",
        )
        return HealResult(found=False, healed=False)

    def _get_locator(self, page: Any, selector: ResilientSelector) -> Any:
        """Get a Playwright locator from a selector (#17)."""
        if selector.strategy == SelectorStrategy.TEST_ID:
            return page.get_by_test_id(selector.value)
        elif selector.strategy == SelectorStrategy.ROLE:
            if selector.name:
                return page.get_by_role(selector.value, name=selector.name)
            return page.get_by_role(selector.value)
        elif selector.strategy == SelectorStrategy.TEXT:
            return page.get_by_text(selector.value)
        elif selector.strategy == SelectorStrategy.SEMANTIC:
            # Value is like "nav[Main Navigation]" — extract the tag part
            tag = selector.value.split("[")[0] if "[" in selector.value else selector.value
            return page.locator(tag)
        elif selector.strategy == SelectorStrategy.STRUCTURAL:
            # Value is a DOM path like "div#app > nav > a"
            return page.locator(selector.value)
        else:
            return page.locator(selector.value)
