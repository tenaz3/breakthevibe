import json
from unittest.mock import AsyncMock

import pytest

from breakthevibe.generator.case_builder import TestCaseGenerator
from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.llm.provider import LLMResponse
from breakthevibe.models.domain import (
    ApiCallInfo,
    ComponentInfo,
    PageData,
    ResilientSelector,
    SiteMap,
)
from breakthevibe.types import SelectorStrategy, TestCategory

SAMPLE_SITEMAP = SiteMap(
    base_url="https://example.com",
    pages=[
        PageData(
            url="https://example.com/",
            path="/",
            title="Home",
            components=[
                ComponentInfo(
                    name="CTA Button",
                    element_type="button",
                    selectors=[
                        ResilientSelector(
                            strategy=SelectorStrategy.TEST_ID, value="cta-btn"
                        ),
                        ResilientSelector(
                            strategy=SelectorStrategy.TEXT, value="Get Started"
                        ),
                    ],
                    aria_role="button",
                    text_content="Get Started",
                ),
            ],
            api_calls=[
                ApiCallInfo(
                    url="https://example.com/api/featured",
                    method="GET",
                    status_code=200,
                    response_body={"items": []},
                ),
            ],
        ),
        PageData(
            url="https://example.com/products",
            path="/products",
            title="Products",
            components=[
                ComponentInfo(
                    name="Filter",
                    element_type="select",
                    selectors=[
                        ResilientSelector(
                            strategy=SelectorStrategy.ROLE,
                            value="combobox",
                            name="Category",
                        ),
                    ],
                    aria_role="combobox",
                ),
            ],
            api_calls=[
                ApiCallInfo(
                    url="https://example.com/api/products",
                    method="GET",
                    status_code=200,
                    response_body={"products": []},
                ),
            ],
        ),
    ],
    api_endpoints=[
        ApiCallInfo(
            url="https://example.com/api/featured", method="GET", status_code=200
        ),
        ApiCallInfo(
            url="https://example.com/api/products", method="GET", status_code=200
        ),
    ],
)

MOCK_LLM_RESPONSE = json.dumps(
    {
        "test_cases": [
            {
                "name": "test_home_cta_navigation",
                "category": "functional",
                "description": "Verify CTA button navigates to expected destination",
                "route": "/",
                "steps": [
                    {
                        "action": "navigate",
                        "target_url": "https://example.com/",
                        "description": "Navigate to home page",
                    },
                    {
                        "action": "click",
                        "selectors": [
                            {"strategy": "test_id", "value": "cta-btn"},
                            {"strategy": "text", "value": "Get Started"},
                        ],
                        "description": "Click CTA button",
                    },
                    {
                        "action": "assert_url",
                        "expected": "https://example.com/products",
                        "description": "Verify navigation to products page",
                    },
                ],
            },
            {
                "name": "test_api_featured_status",
                "category": "api",
                "description": "Validate /api/featured returns 200",
                "route": "/",
                "steps": [
                    {
                        "action": "api_call",
                        "method": "GET",
                        "target_url": "https://example.com/api/featured",
                        "description": "Call featured API",
                    },
                    {
                        "action": "assert_status",
                        "expected": 200,
                        "description": "Verify 200 status code",
                    },
                ],
            },
            {
                "name": "test_home_visual_baseline",
                "category": "visual",
                "description": "Visual baseline for home page",
                "route": "/",
                "steps": [
                    {
                        "action": "navigate",
                        "target_url": "https://example.com/",
                        "description": "Navigate to home page",
                    },
                    {
                        "action": "screenshot",
                        "name": "home_baseline",
                        "description": "Capture baseline screenshot",
                    },
                ],
            },
        ]
    }
)

RULES_YAML = """
tests:
  skip_visual:
    - "/admin"
api:
  ignore_endpoints:
    - "/api/analytics/*"
"""


@pytest.mark.unit
class TestTestCaseGenerator:
    @pytest.fixture()
    def mock_llm(self) -> AsyncMock:
        llm = AsyncMock()
        llm.generate.return_value = LLMResponse(
            content=MOCK_LLM_RESPONSE,
            model="test-model",
            tokens_used=300,
        )
        return llm

    @pytest.fixture()
    def rules(self) -> RulesEngine:
        return RulesEngine(RulesConfig.from_yaml(RULES_YAML))

    @pytest.fixture()
    def generator(
        self, mock_llm: AsyncMock, rules: RulesEngine
    ) -> TestCaseGenerator:
        return TestCaseGenerator(llm=mock_llm, rules=rules)

    @pytest.mark.asyncio
    async def test_generates_test_cases(
        self, generator: TestCaseGenerator
    ) -> None:
        cases = await generator.generate(SAMPLE_SITEMAP)
        assert len(cases) == 3
        categories = {c.category for c in cases}
        assert TestCategory.FUNCTIONAL in categories
        assert TestCategory.API in categories
        assert TestCategory.VISUAL in categories

    @pytest.mark.asyncio
    async def test_functional_test_has_steps(
        self, generator: TestCaseGenerator
    ) -> None:
        cases = await generator.generate(SAMPLE_SITEMAP)
        functional = [c for c in cases if c.category == TestCategory.FUNCTIONAL]
        assert len(functional) == 1
        assert len(functional[0].steps) == 3
        assert functional[0].steps[0].action == "navigate"

    @pytest.mark.asyncio
    async def test_api_test_has_steps(
        self, generator: TestCaseGenerator
    ) -> None:
        cases = await generator.generate(SAMPLE_SITEMAP)
        api_tests = [c for c in cases if c.category == TestCategory.API]
        assert len(api_tests) == 1
        assert api_tests[0].steps[0].action == "api_call"

    @pytest.mark.asyncio
    async def test_llm_receives_sitemap_context(
        self, generator: TestCaseGenerator, mock_llm: AsyncMock
    ) -> None:
        await generator.generate(SAMPLE_SITEMAP)
        call_args = mock_llm.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "example.com" in prompt
        assert "CTA Button" in prompt
        assert "/api/featured" in prompt

    @pytest.mark.asyncio
    async def test_skips_filtered_routes(self, mock_llm: AsyncMock) -> None:
        """Routes in skip_visual should be excluded from visual tests."""
        rules = RulesEngine(
            RulesConfig.from_yaml(
                """
tests:
  skip_visual:
    - "/"
"""
            )
        )
        gen = TestCaseGenerator(llm=mock_llm, rules=rules)
        cases = await gen.generate(SAMPLE_SITEMAP)
        visual = [c for c in cases if c.category == TestCategory.VISUAL]
        # The LLM still returns them, but generator filters based on rules
        for v in visual:
            assert v.route != "/"
