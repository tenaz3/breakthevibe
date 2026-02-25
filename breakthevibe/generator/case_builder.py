"""LLM-powered test case generator."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from breakthevibe.generator.rules.engine import RulesEngine
    from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.models.domain import (
    GeneratedTestCase,
    ResilientSelector,
    SiteMap,
    TestStep,
)
from breakthevibe.types import SelectorStrategy, TestCategory

logger = structlog.get_logger(__name__)


class TestCaseGenerator:
    """Generates test cases from a SiteMap using LLM."""

    def __init__(self, llm: LLMProviderBase, rules: RulesEngine) -> None:
        self._llm = llm
        self._rules = rules

    async def generate(self, sitemap: SiteMap) -> list[GeneratedTestCase]:
        """Generate test cases for a site map."""
        prompt = self._build_prompt(sitemap)
        response = await self._llm.generate(prompt=prompt)

        raw_cases = self._parse_response(response.content)
        cases = [self._build_test_case(raw) for raw in raw_cases]

        # Apply rules filtering
        cases = self._apply_rules(cases)

        logger.info(
            "generated_test_cases",
            count=len(cases),
            categories={
                c.value: sum(1 for tc in cases if tc.category == c)
                for c in TestCategory
            },
        )
        return cases

    def _build_prompt(self, sitemap: SiteMap) -> str:
        """Build the LLM prompt from site map data."""
        pages_desc = []
        for page in sitemap.pages:
            components_desc = ", ".join(c.name for c in page.components)
            api_desc = ", ".join(
                f"{a.method} {a.url}" for a in page.api_calls
            )
            pages_desc.append(
                f"Route: {page.path} (title: {page.title})\n"
                f"  Components: [{components_desc}]\n"
                f"  API calls: [{api_desc}]"
            )

        api_endpoints_desc = "\n".join(
            f"  - {e.method} {e.url} (status: {e.status_code})"
            for e in sitemap.api_endpoints
        )

        return (
            "Analyze the following website structure and generate test cases.\n"
            f"Site: {sitemap.base_url}\n\n"
            f"Pages:\n{chr(10).join(pages_desc)}\n\n"
            f"API Endpoints:\n{api_endpoints_desc}\n\n"
            "Generate test cases in these categories:\n"
            "1. functional - User journey tests with navigation and interactions\n"
            "2. visual - Visual regression baseline captures\n"
            "3. api - API contract validation tests\n\n"
            "Return JSON with this structure:\n"
            "{\n"
            '  "test_cases": [\n'
            "    {\n"
            '      "name": "test_descriptive_name",\n'
            '      "category": "functional|visual|api",\n'
            '      "description": "What this tests",\n'
            '      "route": "/route",\n'
            '      "steps": [\n'
            "        {\n"
            '          "action": "navigate|click|fill|assert_url|assert_text'
            '|api_call|assert_status|screenshot",\n'
            '          "target_url": "optional url",\n'
            '          "selectors": [optional selector objects],\n'
            '          "expected": "optional expected value",\n'
            '          "method": "optional HTTP method",\n'
            '          "name": "optional screenshot name",\n'
            '          "description": "step description"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

    def _parse_response(self, content: str) -> list[dict[str, Any]]:
        """Parse LLM response JSON into raw test case dicts."""
        data = json.loads(content)
        return data.get("test_cases", [])

    def _build_test_case(self, raw: dict[str, Any]) -> GeneratedTestCase:
        """Convert a raw dict into a GeneratedTestCase."""
        steps = []
        for step_raw in raw.get("steps", []):
            selectors = [
                ResilientSelector(
                    strategy=SelectorStrategy(s["strategy"]),
                    value=s["value"],
                    name=s.get("name"),
                )
                for s in step_raw.get("selectors", [])
            ]
            steps.append(
                TestStep(
                    action=step_raw["action"],
                    target_url=step_raw.get("target_url"),
                    selectors=selectors,
                    expected=step_raw.get("expected"),
                    method=step_raw.get("method"),
                    name=step_raw.get("name"),
                    description=step_raw.get("description", ""),
                )
            )

        return GeneratedTestCase(
            name=raw["name"],
            category=TestCategory(raw["category"]),
            description=raw.get("description", ""),
            route=raw.get("route", "/"),
            steps=steps,
        )

    def _apply_rules(
        self, cases: list[GeneratedTestCase]
    ) -> list[GeneratedTestCase]:
        """Filter test cases based on rules engine."""
        filtered = []
        for case in cases:
            if (
                case.category == TestCategory.VISUAL
                and self._rules.should_skip_visual(case.route)
            ):
                logger.debug(
                    "skipping_visual_test", route=case.route, test=case.name
                )
                continue
            filtered.append(case)
        return filtered
