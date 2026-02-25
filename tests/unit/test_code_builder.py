import pytest

from breakthevibe.generator.code_builder import CodeBuilder
from breakthevibe.models.domain import (
    GeneratedTestCase,
    ResilientSelector,
    TestStep,
)
from breakthevibe.types import SelectorStrategy, TestCategory


@pytest.mark.unit
class TestCodeBuilder:
    @pytest.fixture()
    def builder(self) -> CodeBuilder:
        return CodeBuilder()

    @pytest.fixture()
    def functional_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_home_cta_navigation",
            category=TestCategory.FUNCTIONAL,
            description="Verify CTA button navigates correctly",
            route="/",
            steps=[
                TestStep(
                    action="navigate",
                    target_url="https://example.com/",
                    description="Open home page",
                ),
                TestStep(
                    action="click",
                    selectors=[
                        ResilientSelector(
                            strategy=SelectorStrategy.TEST_ID, value="cta-btn"
                        ),
                        ResilientSelector(
                            strategy=SelectorStrategy.TEXT, value="Get Started"
                        ),
                    ],
                    description="Click CTA button",
                ),
                TestStep(
                    action="assert_url",
                    expected="https://example.com/products",
                    description="Verify navigation",
                ),
            ],
        )

    @pytest.fixture()
    def api_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_api_featured_status",
            category=TestCategory.API,
            description="Validate /api/featured returns 200",
            route="/",
            steps=[
                TestStep(
                    action="api_call",
                    target_url="https://example.com/api/featured",
                    expected={"method": "GET"},
                    description="Call featured API",
                ),
                TestStep(
                    action="assert_status",
                    expected=200,
                    description="Verify 200 status",
                ),
            ],
        )

    @pytest.fixture()
    def visual_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_home_visual_baseline",
            category=TestCategory.VISUAL,
            description="Visual baseline for home page",
            route="/",
            steps=[
                TestStep(
                    action="navigate",
                    target_url="https://example.com/",
                    description="Navigate to home",
                ),
                TestStep(
                    action="screenshot",
                    expected="home_baseline",
                    description="Capture baseline",
                ),
            ],
        )

    def test_generates_valid_python(
        self, builder: CodeBuilder, functional_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(functional_case)
        compile(code, "<test>", "exec")

    def test_functional_has_playwright_imports(
        self, builder: CodeBuilder, functional_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(functional_case)
        assert "import pytest" in code
        assert "playwright" in code.lower() or "page" in code

    def test_functional_has_navigate(
        self, builder: CodeBuilder, functional_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(functional_case)
        assert "goto" in code or "navigate" in code
        assert "example.com" in code

    def test_functional_has_click_with_selectors(
        self, builder: CodeBuilder, functional_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(functional_case)
        assert "cta-btn" in code or "Get Started" in code

    def test_functional_has_url_assertion(
        self, builder: CodeBuilder, functional_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(functional_case)
        assert "assert" in code
        assert "products" in code

    def test_api_has_httpx_or_request(
        self, builder: CodeBuilder, api_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(api_case)
        assert "httpx" in code or "request" in code.lower()
        assert "api/featured" in code

    def test_api_has_status_assertion(
        self, builder: CodeBuilder, api_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(api_case)
        assert "status_code" in code
        assert "200" in code

    def test_visual_has_screenshot(
        self, builder: CodeBuilder, visual_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(visual_case)
        assert "screenshot" in code

    def test_generates_function_name(
        self, builder: CodeBuilder, functional_case: GeneratedTestCase
    ) -> None:
        code = builder.generate(functional_case)
        assert "def test_home_cta_navigation" in code

    def test_generate_suite(
        self,
        builder: CodeBuilder,
        functional_case: GeneratedTestCase,
        api_case: GeneratedTestCase,
    ) -> None:
        code = builder.generate_suite([functional_case, api_case])
        assert "test_home_cta_navigation" in code
        assert "test_api_featured_status" in code
        compile(code, "<test>", "exec")
