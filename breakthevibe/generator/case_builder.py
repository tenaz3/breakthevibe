"""LLM-powered test case generator."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from breakthevibe.generator.rules.engine import RulesEngine
    from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.generator.selector import SelectorBuilder
from breakthevibe.models.domain import (
    ComponentInfo,
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
        self._selector_builder = SelectorBuilder()

    async def generate(self, sitemap: SiteMap) -> list[GeneratedTestCase]:
        """Generate test cases for a site map."""
        prompt = self._build_prompt(sitemap)
        response = await self._llm.generate(prompt=prompt)

        # Build a component lookup for selector enrichment (#3)
        component_map: dict[str, ComponentInfo] = {}
        for page in sitemap.pages:
            for comp in page.components:
                component_map[comp.name] = comp

        raw_cases = self._parse_response(response.content)
        cases = [self._build_test_case(raw, component_map) for raw in raw_cases]

        # Apply rules filtering
        cases = self._apply_rules(cases)

        logger.info(
            "generated_test_cases",
            count=len(cases),
            categories={c.value: sum(1 for tc in cases if tc.category == c) for c in TestCategory},
        )
        return cases

    def _build_prompt(self, sitemap: SiteMap) -> str:
        """Build the LLM prompt from site map data."""
        pages_desc = []
        for page in sitemap.pages:
            components_desc = ", ".join(c.name for c in page.components)
            interactions_desc = ", ".join(f"{i.action_type}({i.name})" for i in page.interactions)
            api_desc = ", ".join(f"{a.method} {a.url}" for a in page.api_calls)
            nav_desc = ", ".join(page.navigates_to) if page.navigates_to else "none"
            pages_desc.append(
                f"Route: {page.path} (title: {page.title})\n"
                f"  Components: [{components_desc}]\n"
                f"  Interactions: [{interactions_desc}]\n"
                f"  API calls: [{api_desc}]\n"
                f"  Navigates to: [{nav_desc}]"
            )

        api_endpoints_desc = "\n".join(
            f"  - {e.method} {e.url} (status: {e.status_code})" for e in sitemap.api_endpoints
        )

        # Include spec-only endpoints from API merge (#5)
        spec_only_desc = ""
        if sitemap.api_merge and sitemap.api_merge.spec_only:
            spec_only_lines = "\n".join(
                f"  - {ep.get('method', 'GET')} {ep.get('path', ep.get('url', ''))}"
                for ep in sitemap.api_merge.spec_only
            )
            spec_only_desc = (
                f"\n\nSpec-only endpoints (in OpenAPI spec but not observed in traffic):\n"
                f"{spec_only_lines}\n"
                "Generate tests for these too to verify they are reachable."
            )

        # Include predefined input values (#4)
        inputs_desc = ""
        all_inputs = self._rules.get_all_inputs()
        if all_inputs:
            inputs_lines = "\n".join(f"  {k}: {v}" for k, v in all_inputs.items())
            inputs_desc = f"\n\nPredefined input values (use these for form fills):\n{inputs_lines}"

        return (
            "Analyze the following website structure and generate test cases.\n"
            f"Site: {sitemap.base_url}\n\n"
            f"Pages:\n{chr(10).join(pages_desc)}\n\n"
            f"API Endpoints:\n{api_endpoints_desc}"
            f"{spec_only_desc}{inputs_desc}\n\n"
            "Generate test cases in these categories:\n"
            "1. functional - Include these sub-types:\n"
            "   a. happy_path: Standard user journeys that should succeed\n"
            "   b. edge_case: Boundary values, empty inputs, special characters\n"
            "   c. cross_page: Multi-page flows using navigation links between routes\n"
            "   Use the 'Navigates to' data to build cross-page flows.\n"
            "2. visual - Visual regression baseline captures for visually important components\n"
            "3. api - API contract validation: check status codes AND validate response "
            "body structure (assert key fields exist and have correct types)\n\n"
            "For fill actions, use the predefined input values when available.\n\n"
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
            '|api_call|assert_status|assert_body|screenshot",\n'
            '          "target_url": "optional url",\n'
            '          "selectors": [{"strategy": "test_id|role|text|css",'
            ' "value": "...", "name": "optional"}],\n'
            '          "expected": "optional expected value or JSON schema object",\n'
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
        # Strip markdown code fences if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (``` markers)
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("llm_response_parse_error", content=content[:200])
            return []
        cases: list[dict[str, Any]] = data.get("test_cases", [])
        return cases

    def _build_test_case(
        self, raw: dict[str, Any], component_map: dict[str, ComponentInfo] | None = None
    ) -> GeneratedTestCase:
        """Convert a raw dict into a GeneratedTestCase with selector enrichment."""
        component_map = component_map or {}
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

            # Enrich selectors via SelectorBuilder if we can match a component (#3)
            step_desc = step_raw.get("description", "")
            for comp_name, comp in component_map.items():
                if comp_name in step_desc or (
                    selectors
                    and any(s.value in (comp.test_id or "") for s in selectors if comp.test_id)
                ):
                    selectors = self._selector_builder.build_chain(
                        ComponentInfo(
                            name=comp.name,
                            element_type=comp.element_type,
                            selectors=selectors + comp.selectors,
                            text_content=comp.text_content,
                            aria_role=comp.aria_role,
                            test_id=comp.test_id,
                            is_interactive=comp.is_interactive,
                        )
                    )
                    break

            steps.append(
                TestStep(
                    action=step_raw["action"],
                    target_url=step_raw.get("target_url"),
                    selectors=selectors,
                    expected=step_raw.get("expected"),
                    method=step_raw.get("method"),
                    name=step_raw.get("name"),
                    description=step_desc,
                )
            )

        return GeneratedTestCase(
            name=raw["name"],
            category=TestCategory(raw["category"]),
            description=raw.get("description", ""),
            route=raw.get("route", "/"),
            steps=steps,
        )

    def _apply_rules(self, cases: list[GeneratedTestCase]) -> list[GeneratedTestCase]:
        """Filter test cases based on rules engine."""
        filtered = []
        for case in cases:
            # Skip visual tests for excluded routes
            if case.category == TestCategory.VISUAL and self._rules.should_skip_visual(case.route):
                logger.debug("skipping_visual_test", route=case.route, test=case.name)
                continue

            # Skip tests for crawl-excluded routes (#4)
            if self._rules.should_skip_url(case.route):
                logger.debug("skipping_excluded_route", route=case.route, test=case.name)
                continue

            # Filter out ignored API endpoints from API test steps (#4)
            if case.category == TestCategory.API:
                kept_steps = []
                for step in case.steps:
                    if (
                        step.action == "api_call"
                        and step.target_url
                        and self._rules.should_ignore_endpoint(step.target_url)
                    ):
                        logger.debug(
                            "skipping_ignored_endpoint",
                            endpoint=step.target_url,
                            test=case.name,
                        )
                        continue
                    kept_steps.append(step)
                if not kept_steps:
                    continue
                case.steps = kept_steps

            filtered.append(case)
        return filtered
