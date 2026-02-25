"""Smart parallel/sequential test scheduling."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from breakthevibe.types import TestCategory

if TYPE_CHECKING:
    from breakthevibe.generator.rules.engine import RulesEngine
    from breakthevibe.models.domain import GeneratedTestCase

logger = structlog.get_logger(__name__)


@dataclass
class SuiteSchedule:
    """A group of test cases with execution configuration."""

    name: str
    cases: list[GeneratedTestCase]
    workers: int = 1
    shared_context: bool = False


@dataclass
class ExecutionPlan:
    """Complete execution plan with ordered suites."""

    suites: list[SuiteSchedule] = field(default_factory=list)

    @property
    def total_cases(self) -> int:
        return sum(len(s.cases) for s in self.suites)


class ParallelScheduler:
    """Analyzes test dependencies and decides parallel vs sequential."""

    def __init__(self, rules: RulesEngine) -> None:
        self._rules = rules
        self._max_workers = os.cpu_count() or 4

    def schedule(
        self,
        cases: list[GeneratedTestCase],
        suite_assignments: dict[str, str] | None = None,
    ) -> ExecutionPlan:
        """Create an execution plan from test cases."""
        if not cases:
            return ExecutionPlan()

        mode = self._rules.get_execution_mode()

        if suite_assignments:
            return self._schedule_with_assignments(cases, suite_assignments)

        if mode == "sequential":
            return self._schedule_sequential(cases)
        elif mode == "parallel":
            return self._schedule_parallel(cases)
        else:  # smart
            return self._schedule_smart(cases)

    def _schedule_sequential(
        self, cases: list[GeneratedTestCase]
    ) -> ExecutionPlan:
        """All tests in one sequential suite."""
        return ExecutionPlan(
            suites=[SuiteSchedule(name="all", cases=cases, workers=1)]
        )

    def _schedule_parallel(
        self, cases: list[GeneratedTestCase]
    ) -> ExecutionPlan:
        """All tests in one parallel suite with max workers."""
        workers = min(len(cases), self._max_workers)
        return ExecutionPlan(
            suites=[
                SuiteSchedule(name="all", cases=cases, workers=max(workers, 1))
            ]
        )

    def _schedule_smart(
        self, cases: list[GeneratedTestCase]
    ) -> ExecutionPlan:
        """Group by category and route, decide workers per group."""
        suites: list[SuiteSchedule] = []

        # Separate API tests (stateless, safe to parallelize)
        api_cases = [c for c in cases if c.category == TestCategory.API]
        ui_cases = [c for c in cases if c.category != TestCategory.API]

        if api_cases:
            workers = min(len(api_cases), self._max_workers)
            suites.append(
                SuiteSchedule(
                    name="api-tests",
                    cases=api_cases,
                    workers=max(workers, 1),
                )
            )

        # Group UI tests by route
        by_route: dict[str, list[GeneratedTestCase]] = defaultdict(list)
        for case in ui_cases:
            by_route[case.route].append(case)

        for route, route_cases in by_route.items():
            safe_name = route.strip("/").replace("/", "-") or "root"
            suites.append(
                SuiteSchedule(
                    name=f"ui-{safe_name}",
                    cases=route_cases,
                    workers=1,
                )
            )

        logger.info(
            "smart_schedule",
            suites=len(suites),
            total_cases=sum(len(s.cases) for s in suites),
        )
        return ExecutionPlan(suites=suites)

    def _schedule_with_assignments(
        self,
        cases: list[GeneratedTestCase],
        assignments: dict[str, str],
    ) -> ExecutionPlan:
        """Schedule based on explicit suite assignments with config overrides."""
        suites_map: dict[str, list[GeneratedTestCase]] = defaultdict(list)
        unassigned: list[GeneratedTestCase] = []

        for case in cases:
            suite_name = assignments.get(case.name)
            if suite_name:
                suites_map[suite_name].append(case)
            else:
                unassigned.append(case)

        suites: list[SuiteSchedule] = []
        for suite_name, suite_cases in suites_map.items():
            config = self._rules.get_suite_config(suite_name)
            if config:
                mode = config.get("mode", "smart")
                workers = (
                    1
                    if mode == "sequential"
                    else config.get("workers", self._max_workers)
                )
                shared = config.get("shared_context", False)
            else:
                workers = 1
                shared = False

            suites.append(
                SuiteSchedule(
                    name=suite_name,
                    cases=suite_cases,
                    workers=workers,
                    shared_context=shared,
                )
            )

        if unassigned:
            suites.append(
                SuiteSchedule(name="unassigned", cases=unassigned, workers=1)
            )

        return ExecutionPlan(suites=suites)
