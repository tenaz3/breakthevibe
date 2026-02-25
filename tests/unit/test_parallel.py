import pytest

from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.models.domain import GeneratedTestCase, TestStep
from breakthevibe.runner.parallel import ExecutionPlan, ParallelScheduler
from breakthevibe.types import TestCategory


def _make_case(name: str, category: TestCategory, route: str) -> GeneratedTestCase:
    return GeneratedTestCase(
        name=name,
        category=category,
        description=f"Test {name}",
        route=route,
        steps=[
            TestStep(
                action="navigate",
                target_url=f"https://example.com{route}",
                description="nav",
            ),
        ],
    )


RULES_SMART = """
execution:
  mode: smart
  suites: {}
"""

RULES_SEQUENTIAL = """
execution:
  mode: sequential
  suites: {}
"""

RULES_PARALLEL = """
execution:
  mode: parallel
  suites: {}
"""

RULES_WITH_SUITES = """
execution:
  mode: smart
  suites:
    auth-flow:
      mode: sequential
      shared_context: true
    product-pages:
      mode: parallel
      workers: 4
"""


@pytest.mark.unit
class TestParallelScheduler:
    def test_smart_mode_groups_by_route(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SMART))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_home_1", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_home_2", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_products_1", TestCategory.FUNCTIONAL, "/products"),
            _make_case("test_api_1", TestCategory.API, "/"),
        ]

        plan = scheduler.schedule(cases)
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.suites) >= 1

    def test_sequential_mode_single_group(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SEQUENTIAL))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_1", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_2", TestCategory.FUNCTIONAL, "/products"),
        ]

        plan = scheduler.schedule(cases)
        for suite in plan.suites:
            assert suite.workers == 1

    def test_parallel_mode_max_workers(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_PARALLEL))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_1", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_2", TestCategory.FUNCTIONAL, "/products"),
            _make_case("test_3", TestCategory.FUNCTIONAL, "/about"),
        ]

        plan = scheduler.schedule(cases)
        assert any(s.workers > 1 for s in plan.suites)

    def test_suite_config_overrides(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_WITH_SUITES))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_login", TestCategory.FUNCTIONAL, "/login"),
            _make_case("test_product_1", TestCategory.FUNCTIONAL, "/products"),
        ]

        plan = scheduler.schedule(
            cases,
            suite_assignments={
                "test_login": "auth-flow",
                "test_product_1": "product-pages",
            },
        )

        auth_suite = next((s for s in plan.suites if s.name == "auth-flow"), None)
        product_suite = next((s for s in plan.suites if s.name == "product-pages"), None)

        assert auth_suite is not None
        assert auth_suite.workers == 1  # sequential
        assert product_suite is not None
        assert product_suite.workers == 4

    def test_smart_groups_api_tests_separately(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SMART))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_home_ui", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_api_health", TestCategory.API, "/"),
            _make_case("test_home_visual", TestCategory.VISUAL, "/"),
        ]

        plan = scheduler.schedule(cases)
        api_suites = [
            s for s in plan.suites if any(c.category == TestCategory.API for c in s.cases)
        ]
        assert len(api_suites) >= 1
        assert api_suites[0].workers > 1 or len(api_suites[0].cases) <= 1

    def test_empty_cases_returns_empty_plan(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SMART))
        scheduler = ParallelScheduler(rules)
        plan = scheduler.schedule([])
        assert plan.suites == []
