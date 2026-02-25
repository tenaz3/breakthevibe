import pytest

from breakthevibe.models.domain import (
    ComponentInfo,
    CrawlResult,
    GeneratedTestCase,
    PageData,
    ResilientSelector,
    SiteMap,
    TestStep,
)
from breakthevibe.types import SelectorStrategy, TestCategory


@pytest.mark.unit
class TestDomainModels:
    def test_resilient_selector(self) -> None:
        selector = ResilientSelector(
            strategy=SelectorStrategy.TEST_ID,
            value="submit-btn",
        )
        assert selector.strategy == SelectorStrategy.TEST_ID

    def test_component_info(self) -> None:
        comp = ComponentInfo(
            name="navbar",
            element_type="nav",
            selectors=[ResilientSelector(strategy=SelectorStrategy.ROLE, value="navigation")],
        )
        assert comp.name == "navbar"
        assert len(comp.selectors) == 1

    def test_page_data(self) -> None:
        page = PageData(
            url="https://example.com/products",
            path="/products",
            components=[],
            interactions=[],
            api_calls=[],
        )
        assert page.path == "/products"

    def test_site_map(self) -> None:
        site_map = SiteMap(
            base_url="https://example.com",
            pages=[],
        )
        assert site_map.base_url == "https://example.com"

    def test_crawl_result(self) -> None:
        result = CrawlResult(pages=[])
        assert result.total_routes == 0

    def test_test_step(self) -> None:
        step = TestStep(
            action="click",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Submit"),
            ],
        )
        assert step.action == "click"

    def test_generated_test_case(self) -> None:
        tc = GeneratedTestCase(
            name="Login test",
            category=TestCategory.FUNCTIONAL,
            route="/login",
            steps=[TestStep(action="navigate", target_url="/login")],
            code="def test_login(): pass",
        )
        assert tc.category == TestCategory.FUNCTIONAL
        assert len(tc.steps) == 1
