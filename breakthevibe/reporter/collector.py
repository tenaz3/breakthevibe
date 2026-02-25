"""Test result collection and report building."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from breakthevibe.types import TestStatus

if TYPE_CHECKING:
    from pathlib import Path

    from breakthevibe.runner.executor import ExecutionResult
    from breakthevibe.runner.healer import HealResult

logger = structlog.get_logger(__name__)


@dataclass
class ScreenshotRef:
    """Reference to a captured screenshot."""

    suite_name: str
    step_name: str
    path: Path


@dataclass
class TestRunReport:
    """Aggregated report for a complete test run."""

    project_id: str
    run_id: str
    results: list[ExecutionResult]
    heal_warnings: list[str] = field(default_factory=list)
    screenshots: list[ScreenshotRef] = field(default_factory=list)

    @property
    def total_suites(self) -> int:
        return len(self.results)

    @property
    def passed_suites(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_suites(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def overall_status(self) -> TestStatus:
        if not self.results:
            return TestStatus.PASSED
        return TestStatus.PASSED if all(r.success for r in self.results) else TestStatus.FAILED

    @property
    def total_duration(self) -> float:
        return sum(r.duration_seconds for r in self.results)


class ResultCollector:
    """Collects test results and artifacts into a report."""

    def __init__(self) -> None:
        self._results: list[ExecutionResult] = []
        self._heal_warnings: list[str] = []
        self._screenshots: list[ScreenshotRef] = []

    def add_execution_result(self, result: ExecutionResult) -> None:
        """Add an execution result."""
        self._results.append(result)
        logger.info(
            "result_collected",
            suite=result.suite_name,
            success=result.success,
            duration=result.duration_seconds,
        )

    def add_heal_warning(self, suite_name: str, heal_result: HealResult) -> None:
        """Record a healed selector warning."""
        msg = heal_result.warning_message()
        if msg:
            self._heal_warnings.append(msg)
            logger.warning("heal_warning_recorded", suite=suite_name, message=msg)

    def add_screenshot(self, suite_name: str, step_name: str, path: Path) -> None:
        """Add a screenshot reference."""
        self._screenshots.append(
            ScreenshotRef(
                suite_name=suite_name,
                step_name=step_name,
                path=path,
            )
        )

    def build_report(self, project_id: str, run_id: str) -> TestRunReport:
        """Build a complete test run report."""
        report = TestRunReport(
            project_id=project_id,
            run_id=run_id,
            results=list(self._results),
            heal_warnings=list(self._heal_warnings),
            screenshots=list(self._screenshots),
        )
        logger.info(
            "report_built",
            project=project_id,
            run=run_id,
            total=report.total_suites,
            passed=report.passed_suites,
            failed=report.failed_suites,
            status=report.overall_status.value,
        )
        return report
