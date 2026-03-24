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
        cases: list[GeneratedTestCase] = []
        for raw in raw_cases:
            try:
                cases.append(self._build_test_case(raw, component_map))
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "skipping_malformed_test_case",
                    error=str(exc),
                    raw_case=str(raw)[:200],
                )

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
            "Analyze the following website structure and generate comprehensive test cases.\n"
            f"Site: {sitemap.base_url}\n\n"
            f"Pages:\n{chr(10).join(pages_desc)}\n\n"
            f"API Endpoints:\n{api_endpoints_desc}"
            f"{spec_only_desc}{inputs_desc}\n\n"
            "VOLUME REQUIREMENT: Generate at least 2-3 test cases per discovered page/route.\n"
            "Cover happy paths, edge cases, and API contracts for every route listed above.\n\n"
            "Generate test cases in these categories:\n"
            "1. functional - category value must be exactly: functional\n"
            "   a. happy_path: Standard user journeys that should succeed\n"
            "   b. edge_case: Boundary values, empty inputs, special characters\n"
            "   c. cross_page: Multi-page flows using navigation links between routes\n"
            "   Use the 'Navigates to' data to build cross-page flows.\n"
            "2. visual - category value must be exactly: visual\n"
            "   Visual regression baseline captures for visually important components\n"
            "3. api - category value must be exactly: api\n"
            "   API contract validation: check status codes AND validate response "
            "body structure (assert key fields exist and have correct types)\n\n"
            "Valid selector strategies: css, xpath, text, role, test_id\n"
            "For fill actions, use the predefined input values when available.\n\n"
            "IMPORTANT for api_call steps: put the HTTP method inside the 'expected' object,\n"
            "not at the top level of the step. Example:\n"
            '  "expected": {"method": "GET", "status": 200}\n\n'
            "Return a JSON object — no markdown, no explanation — with EXACTLY this structure:\n"
            "{\n"
            '  "test_cases": [\n'
            "    {\n"
            '      "name": "home_page_loads_successfully",\n'
            '      "category": "functional",\n'
            '      "description": "Verify the home page renders with the main heading",\n'
            '      "route": "/",\n'
            '      "steps": [\n'
            "        {\n"
            '          "action": "navigate",\n'
            '          "target_url": "/",\n'
            '          "selectors": [],\n'
            '          "expected": null,\n'
            '          "name": null,\n'
            '          "description": "Navigate to home page"\n'
            "        },\n"
            "        {\n"
            '          "action": "assert_text",\n'
            '          "target_url": null,\n'
            '          "selectors": [{"strategy": "role", "value": "heading", "name": "h1"}],\n'
            '          "expected": "Welcome",\n'
            '          "name": null,\n'
            '          "description": "Assert main heading is visible"\n'
            "        }\n"
            "      ]\n"
            "    },\n"
            "    {\n"
            '      "name": "api_get_users_returns_200",\n'
            '      "category": "api",\n'
            '      "description": "Verify GET /users returns 200 with a list",\n'
            '      "route": "/users",\n'
            '      "steps": [\n'
            "        {\n"
            '          "action": "api_call",\n'
            '          "target_url": "/users",\n'
            '          "selectors": [],\n'
            '          "expected": {"method": "GET", "status": 200},\n'
            '          "name": null,\n'
            '          "description": "Call GET /users"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Now generate test cases for all pages and API endpoints listed above."
        )

    def _parse_response(self, content: str) -> list[dict[str, Any]]:
        """Parse LLM response JSON into raw test case dicts."""
        cleaned = content.strip()
        logger.debug("llm_raw_response", content_preview=cleaned[:500])

        # Strip markdown code fences: ```json, ```yaml, ``` etc.
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # Drop opening fence line and any closing fence lines
            lines = [line for line in lines[1:] if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        # Attempt 1: parse the cleaned string directly
        try:
            data = json.loads(cleaned)
            cases: list[dict[str, Any]] = data.get("test_cases", [])
            logger.debug("llm_response_parsed", case_count=len(cases))
            return cases
        except json.JSONDecodeError:
            pass

        # Attempt 2: extract JSON object between first `{` and last `}`
        obj_start = cleaned.find("{")
        obj_end = cleaned.rfind("}")
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            try:
                data = json.loads(cleaned[obj_start : obj_end + 1])
                cases = data.get("test_cases", [])
                if cases:
                    logger.debug("llm_response_extracted_object", case_count=len(cases))
                    return cases
            except json.JSONDecodeError:
                pass

        # Attempt 3: extract JSON array between first `[` and last `]`
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                cases = json.loads(cleaned[start : end + 1])
                if isinstance(cases, list):
                    logger.debug("llm_response_extracted_array", case_count=len(cases))
                    return cases
            except json.JSONDecodeError:
                pass

        # Attempt 4: repair truncated JSON — LLM may have hit max_tokens
        # Find the last complete JSON object in a test_cases array
        arr_start = cleaned.find("[")
        if arr_start != -1:
            # Find last complete `}` that could end a test case object
            fragment = cleaned[arr_start:]
            # Try progressively shorter substrings ending at each `}`
            last_brace = fragment.rfind("}")
            while last_brace > 0:
                candidate = fragment[: last_brace + 1] + "]"
                try:
                    cases = json.loads(candidate)
                    if isinstance(cases, list) and cases:
                        logger.warning(
                            "llm_response_repaired_truncated",
                            original_length=len(content),
                            recovered_cases=len(cases),
                        )
                        return cases
                except json.JSONDecodeError:
                    pass
                last_brace = fragment.rfind("}", 0, last_brace)

        logger.error(
            "llm_response_parse_error",
            content_preview=content[:500],
            content_length=len(content),
            hint="All JSON parse attempts failed including truncation repair. "
            "Check if the LLM model supports structured JSON output.",
        )
        return []

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
