import pytest

from breakthevibe.models.database import (
    CrawlRun,
    Project,
    Route,
    TestCase,
    TestResult,
    TestRun,
)


@pytest.mark.unit
class TestDatabaseModels:
    def test_project_creation(self) -> None:
        project = Project(name="My Site", url="https://example.com")
        assert project.name == "My Site"
        assert project.url == "https://example.com"
        assert project.created_at is not None

    def test_crawl_run_creation(self) -> None:
        run = CrawlRun(project_id=1, status="running")
        assert run.status == "running"
        assert run.project_id == 1

    def test_route_creation(self) -> None:
        route = Route(
            crawl_run_id=1,
            url="https://example.com/products",
            path="/products",
        )
        assert route.path == "/products"
        assert route.url == "https://example.com/products"

    def test_test_case_creation(self) -> None:
        tc = TestCase(
            project_id=1,
            name="Login flow",
            category="functional",
            route_path="/login",
        )
        assert tc.category == "functional"
        assert tc.name == "Login flow"

    def test_test_run_creation(self) -> None:
        run = TestRun(project_id=1, status="running")
        assert run.status == "running"
        assert run.total == 0

    def test_test_result_creation(self) -> None:
        result = TestResult(
            test_run_id=1,
            test_case_id=1,
            status="passed",
        )
        assert result.status == "passed"

    def test_project_defaults(self) -> None:
        project = Project(name="Test", url="https://test.com")
        assert project.id is None
        assert project.config_yaml is None
