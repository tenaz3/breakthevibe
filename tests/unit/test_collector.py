from pathlib import Path

import pytest

from breakthevibe.models.domain import ResilientSelector
from breakthevibe.reporter.collector import ResultCollector, TestRunReport
from breakthevibe.runner.executor import ExecutionResult
from breakthevibe.runner.healer import HealResult
from breakthevibe.types import SelectorStrategy, TestStatus


@pytest.mark.unit
class TestResultCollector:
    @pytest.fixture()
    def collector(self) -> ResultCollector:
        return ResultCollector()

    @pytest.fixture()
    def passing_result(self, tmp_path: Path) -> ExecutionResult:
        return ExecutionResult(
            suite_name="test_home",
            success=True,
            exit_code=0,
            stdout="2 passed in 1.5s",
            stderr="",
            test_file=tmp_path / "test_home.py",
            duration_seconds=1.5,
        )

    @pytest.fixture()
    def failing_result(self, tmp_path: Path) -> ExecutionResult:
        return ExecutionResult(
            suite_name="test_products",
            success=False,
            exit_code=1,
            stdout="1 passed, 1 failed in 2.0s",
            stderr="AssertionError: expected 200 got 404",
            test_file=tmp_path / "test_products.py",
            duration_seconds=2.0,
        )

    def test_collect_single_pass(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
    ) -> None:
        collector.add_execution_result(passing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-1")
        assert isinstance(report, TestRunReport)
        assert report.project_id == "proj-1"
        assert report.run_id == "run-1"
        assert report.total_suites == 1
        assert report.passed_suites == 1
        assert report.failed_suites == 0

    def test_collect_mixed_results(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
        failing_result: ExecutionResult,
    ) -> None:
        collector.add_execution_result(passing_result)
        collector.add_execution_result(failing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-2")
        assert report.total_suites == 2
        assert report.passed_suites == 1
        assert report.failed_suites == 1
        assert report.overall_status == TestStatus.FAILED

    def test_all_passing_status(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
    ) -> None:
        collector.add_execution_result(passing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-3")
        assert report.overall_status == TestStatus.PASSED

    def test_collect_healed_selectors(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
    ) -> None:
        heal = HealResult(
            found=True,
            healed=True,
            used_selector=ResilientSelector(
                strategy=SelectorStrategy.CSS, value=".btn"
            ),
            original_selector=ResilientSelector(
                strategy=SelectorStrategy.TEST_ID, value="submit"
            ),
        )
        collector.add_execution_result(passing_result)
        collector.add_heal_warning("test_home", heal)
        report = collector.build_report(project_id="proj-1", run_id="run-4")
        assert len(report.heal_warnings) == 1
        assert "submit" in report.heal_warnings[0]

    def test_collect_screenshots(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
        tmp_path: Path,
    ) -> None:
        screenshot = tmp_path / "home.png"
        screenshot.write_bytes(b"\x89PNG fake data")
        collector.add_execution_result(passing_result)
        collector.add_screenshot("test_home", "home_step_1", screenshot)
        report = collector.build_report(project_id="proj-1", run_id="run-5")
        assert len(report.screenshots) == 1
        assert report.screenshots[0].step_name == "home_step_1"

    def test_empty_report(self, collector: ResultCollector) -> None:
        report = collector.build_report(project_id="proj-1", run_id="run-6")
        assert report.total_suites == 0
        assert report.overall_status == TestStatus.PASSED

    def test_duration_sums(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
        failing_result: ExecutionResult,
    ) -> None:
        collector.add_execution_result(passing_result)
        collector.add_execution_result(failing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-7")
        assert report.total_duration == pytest.approx(3.5, abs=0.1)
