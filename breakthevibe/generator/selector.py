"""Resilient selector chain builder."""

from __future__ import annotations

import structlog

from breakthevibe.models.domain import ComponentInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy

logger = structlog.get_logger(__name__)

# Priority order: most stable first
STRATEGY_PRIORITY: list[SelectorStrategy] = [
    SelectorStrategy.TEST_ID,
    SelectorStrategy.ROLE,
    SelectorStrategy.TEXT,
    SelectorStrategy.SEMANTIC,
    SelectorStrategy.STRUCTURAL,
    SelectorStrategy.CSS,
]


class SelectorBuilder:
    """Builds ordered, deduplicated selector chains for components."""

    def build_chain(self, component: ComponentInfo) -> list[ResilientSelector]:
        """Build a prioritized selector chain from a component's selectors + metadata."""
        all_selectors = list(component.selectors)

        # Infer additional selectors from component metadata
        all_selectors.extend(self._infer_from_metadata(component, all_selectors))

        # Deduplicate by (strategy, value) pair
        seen: set[tuple[SelectorStrategy, str]] = set()
        unique: list[ResilientSelector] = []
        for sel in all_selectors:
            key = (sel.strategy, sel.value)
            if key not in seen:
                seen.add(key)
                unique.append(sel)

        # Sort by priority order
        priority_map = {s: i for i, s in enumerate(STRATEGY_PRIORITY)}
        unique.sort(key=lambda s: priority_map.get(s.strategy, len(STRATEGY_PRIORITY)))

        return unique

    def _infer_from_metadata(
        self, component: ComponentInfo, existing: list[ResilientSelector]
    ) -> list[ResilientSelector]:
        """Infer selectors from component metadata that aren't already present."""
        existing_strategies = {s.strategy for s in existing}
        inferred: list[ResilientSelector] = []

        # Infer test_id selector
        if SelectorStrategy.TEST_ID not in existing_strategies and component.test_id:
            inferred.append(
                ResilientSelector(
                    strategy=SelectorStrategy.TEST_ID,
                    value=component.test_id,
                )
            )

        # Infer role selector
        if SelectorStrategy.ROLE not in existing_strategies and component.aria_role:
            inferred.append(
                ResilientSelector(
                    strategy=SelectorStrategy.ROLE,
                    value=component.aria_role,
                    name=component.text_content or component.name,
                )
            )

        # Infer text selector
        if SelectorStrategy.TEXT not in existing_strategies and component.text_content:
            inferred.append(
                ResilientSelector(
                    strategy=SelectorStrategy.TEXT,
                    value=component.text_content,
                )
            )

        return inferred
