"""Generates executable pytest code from test cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from breakthevibe.types import SelectorStrategy, TestCategory

if TYPE_CHECKING:
    from breakthevibe.models.domain import (
        GeneratedTestCase,
        ResilientSelector,
        TestStep,
    )

logger = structlog.get_logger(__name__)


class CodeBuilder:
    """Generates pytest + Playwright code from GeneratedTestCase objects."""

    def generate(self, case: GeneratedTestCase) -> str:
        """Generate pytest code for a single test case."""
        if case.category == TestCategory.FUNCTIONAL:
            return self._generate_functional(case)
        elif case.category == TestCategory.API:
            return self._generate_api(case)
        elif case.category == TestCategory.VISUAL:
            return self._generate_visual(case)
        else:
            msg = f"Unknown test category: {case.category}"
            raise ValueError(msg)

    def generate_suite(self, cases: list[GeneratedTestCase]) -> str:
        """Generate a complete test file from multiple test cases."""
        has_functional = any(c.category == TestCategory.FUNCTIONAL for c in cases)
        has_api = any(c.category == TestCategory.API for c in cases)
        has_visual = any(c.category == TestCategory.VISUAL for c in cases)

        lines: list[str] = [
            '"""Auto-generated test suite by BreakTheVibe."""',
            "",
            "import pytest",
        ]

        if has_functional or has_visual:
            lines.append("from playwright.async_api import Page, expect")
        if has_api:
            lines.append("import httpx")
        if has_visual:
            lines.append("from pathlib import Path")
            lines.append("from breakthevibe.reporter.diff import VisualDiff")

        lines.extend(["", ""])

        for case in cases:
            func_code = self._generate_function_body(case)
            lines.append(func_code)
            lines.append("")

        return "\n".join(lines)

    def _generate_functional(self, case: GeneratedTestCase) -> str:
        """Generate a full functional test file."""
        lines = [
            '"""Auto-generated functional test by BreakTheVibe."""',
            "",
            "import pytest",
            "from playwright.async_api import Page, expect",
            "",
            "",
            self._generate_function_body(case),
        ]
        return "\n".join(lines)

    def _generate_api(self, case: GeneratedTestCase) -> str:
        """Generate a full API test file."""
        lines = [
            '"""Auto-generated API test by BreakTheVibe."""',
            "",
            "import pytest",
            "import httpx",
            "",
            "",
            self._generate_function_body(case),
        ]
        return "\n".join(lines)

    def _generate_visual(self, case: GeneratedTestCase) -> str:
        """Generate a full visual regression test file."""
        lines = [
            '"""Auto-generated visual regression test by BreakTheVibe."""',
            "",
            "import pytest",
            "from pathlib import Path",
            "from playwright.async_api import Page",
            "",
            "from breakthevibe.reporter.diff import VisualDiff",
            "",
            "",
            self._generate_function_body(case),
        ]
        return "\n".join(lines)

    def _generate_function_body(self, case: GeneratedTestCase) -> str:
        """Generate the test function body."""
        if case.category == TestCategory.FUNCTIONAL:
            return self._functional_body(case)
        elif case.category == TestCategory.API:
            return self._api_body(case)
        elif case.category == TestCategory.VISUAL:
            return self._visual_body(case)
        msg = f"Unknown category: {case.category}"
        raise ValueError(msg)

    def _functional_body(self, case: GeneratedTestCase) -> str:
        """Generate functional test function."""
        lines = [
            "@pytest.mark.asyncio",
            f"async def {case.name}(page: Page) -> None:",
            f'    """{case.description}"""',
        ]
        for step in case.steps:
            lines.extend(self._step_to_playwright(step))
        return "\n".join(lines)

    def _api_body(self, case: GeneratedTestCase) -> str:
        """Generate API test function."""
        lines = [
            "@pytest.mark.asyncio",
            f"async def {case.name}() -> None:",
            f'    """{case.description}"""',
            "    async with httpx.AsyncClient() as client:",
        ]
        for step in case.steps:
            lines.extend(self._step_to_httpx(step))
        return "\n".join(lines)

    def _visual_body(self, case: GeneratedTestCase) -> str:
        """Generate visual regression test function."""
        lines = [
            "@pytest.mark.asyncio",
            f"async def {case.name}(page: Page, tmp_path: Path) -> None:",
            f'    """{case.description}"""',
        ]
        for step in case.steps:
            lines.extend(self._step_to_visual(step))
        return "\n".join(lines)

    def _step_to_playwright(self, step: TestStep) -> list[str]:
        """Convert a test step to Playwright code lines with selector fallback."""
        lines: list[str] = []
        if step.action == "navigate":
            lines.append(f'    await page.goto("{step.target_url}")')
        elif step.action == "click":
            lines.extend(self._build_fallback_locator(step.selectors, "click()"))
        elif step.action == "fill":
            value = step.expected or ""
            lines.extend(self._build_fallback_locator(step.selectors, f'fill("{value}")'))
        elif step.action == "assert_url":
            lines.append(f'    assert page.url == "{step.expected}"')
        elif step.action == "assert_text":
            locator = self._build_locator(step.selectors)
            lines.append(f'    await expect({locator}).to_have_text("{step.expected}")')
        return lines

    def _step_to_httpx(self, step: TestStep) -> list[str]:
        """Convert a test step to httpx code lines."""
        lines: list[str] = []
        if step.action == "api_call":
            method = "GET"
            if isinstance(step.expected, dict):
                method = step.expected.get("method", "GET")
            lines.append(f'        response = await client.{method.lower()}("{step.target_url}")')
        elif step.action == "assert_status":
            lines.append(f"        assert response.status_code == {step.expected}")
        return lines

    def _step_to_visual(self, step: TestStep) -> list[str]:
        """Convert a test step to visual regression code lines with diff comparison."""
        lines: list[str] = []
        if step.action == "navigate":
            lines.append(f'    await page.goto("{step.target_url}")')
        elif step.action == "screenshot":
            name = step.expected or "screenshot"
            lines.append(f'    current = tmp_path / "{name}.png"')
            lines.append("    await page.screenshot(path=str(current))")
            lines.append(f'    baseline = Path("baselines") / "{name}.png"')
            lines.append("    if baseline.exists():")
            lines.append(f'        diff_path = tmp_path / "{name}_diff.png"')
            lines.append("        diff = VisualDiff().compare(baseline, current, diff_path)")
            lines.append("        assert diff.matches, (")
            lines.append('            f"Visual regression: {diff.diff_percentage:.2%} changed"')
            lines.append("        )")
        return lines

    def _build_fallback_locator(self, selectors: list[ResilientSelector], action: str) -> list[str]:
        """Build selector fallback chain: try each in priority order."""
        if not selectors or len(selectors) <= 1:
            locator = self._build_locator(selectors)
            return [f"    await {locator}.{action}"]

        # Generate try/except chain for resilient selector fallback
        lines: list[str] = []
        for i, sel in enumerate(selectors):
            locator_str = self._single_locator(sel)
            if i == 0:
                lines.append("    try:")
                lines.append(f"        locator = {locator_str}")
                lines.append("        if await locator.count() > 0:")
                lines.append(f"            await locator.{action}")
            elif i == len(selectors) - 1:
                lines.append("    except Exception:")
                lines.append(f"        await {locator_str}.{action}")
            else:
                lines.append("    except Exception:")
                lines.append("        try:")
                lines.append(f"            await {locator_str}.{action}")
        return lines

    def _build_locator(self, selectors: list[ResilientSelector]) -> str:
        """Build a Playwright locator from selectors, using highest priority."""
        if not selectors:
            return 'page.locator("body")'
        return self._single_locator(selectors[0])

    def _single_locator(self, sel: ResilientSelector) -> str:
        """Convert a single selector to a Playwright locator string."""
        if sel.strategy == SelectorStrategy.TEST_ID:
            return f'page.get_by_test_id("{sel.value}")'
        elif sel.strategy == SelectorStrategy.ROLE:
            if sel.name:
                return f'page.get_by_role("{sel.value}", name="{sel.name}")'
            return f'page.get_by_role("{sel.value}")'
        elif sel.strategy == SelectorStrategy.TEXT:
            return f'page.get_by_text("{sel.value}")'
        elif sel.strategy == SelectorStrategy.CSS:
            return f'page.locator("{sel.value}")'
        else:
            return f'page.locator("{sel.value}")'
