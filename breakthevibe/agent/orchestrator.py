"""Pipeline orchestrator — coordinates all stages."""

from __future__ import annotations

import contextlib
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from breakthevibe.config.settings import SENTINEL_ORG_ID

if TYPE_CHECKING:
    from breakthevibe.agent.planner import AgentPlanner
    from breakthevibe.generator.code_builder import CodeBuilder
    from breakthevibe.runner.parallel import ParallelScheduler

logger = structlog.get_logger(__name__)


class PipelineStage(StrEnum):
    CRAWL = "crawl"
    MAP = "map"
    GENERATE = "generate"
    RUN = "run"
    REPORT = "report"


@dataclass
class PipelineResult:
    """Result of a full pipeline execution."""

    project_id: str
    run_id: str
    success: bool
    completed_stages: list[PipelineStage] = field(default_factory=list)
    failed_stage: PipelineStage | None = None
    error_message: str = ""
    duration_seconds: float = 0.0
    report: Any = None  # TestRunReport from ResultCollector
    sitemap: Any = None  # SiteMap from MindMapBuilder


class PipelineOrchestrator:
    """Coordinates the full pipeline: crawl -> map -> generate -> run -> report."""

    def __init__(
        self,
        crawler: Any = None,
        mapper: Any = None,
        generator: Any = None,
        runner: Any = None,
        collector: Any = None,
        planner: AgentPlanner | None = None,
        code_builder: CodeBuilder | None = None,
        scheduler: ParallelScheduler | None = None,
        max_retries: int | None = None,
        progress_callback: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._crawler = crawler
        self._mapper = mapper
        self._generator = generator
        self._runner = runner
        self._collector = collector
        self._planner = planner
        self._code_builder = code_builder
        self._scheduler = scheduler
        # Use explicit max_retries if provided, otherwise default based on planner
        self.max_retries: int = max_retries if max_retries is not None else (3 if planner else 1)
        self._progress_callback = progress_callback

    def _emit(self, stage: str, status: str, error: str = "") -> None:
        """Fire progress callback if one is registered."""
        if self._progress_callback is not None:
            with contextlib.suppress(Exception):
                self._progress_callback(stage, status, error)

    async def run(
        self,
        project_id: str,
        url: str,
        rules_yaml: str = "",
        openapi_spec: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Execute the full pipeline."""
        run_id = str(uuid.uuid4())
        start = time.monotonic()
        completed: list[PipelineStage] = []

        # Bind correlation ID for all logs within this pipeline run (#12)
        bind_contextvars(pipeline_run_id=run_id, pipeline_project_id=project_id)

        logger.info("pipeline_started", project_id=project_id, run_id=run_id, url=url)

        stages = [
            (PipelineStage.CRAWL, self._run_crawl),
            (PipelineStage.MAP, self._run_map),
            (PipelineStage.GENERATE, self._run_generate),
            (PipelineStage.RUN, self._run_tests),
            (PipelineStage.REPORT, self._run_report),
        ]

        context: dict[str, Any] = {
            "url": url,
            "rules_yaml": rules_yaml,
            "project_id": project_id,
            "run_id": run_id,
            "openapi_spec": openapi_spec,
        }

        for stage, handler in stages:
            success = False
            last_error = ""

            for attempt in range(self.max_retries):
                try:
                    logger.info("stage_starting", stage=stage.value, attempt=attempt + 1)
                    self._emit(stage.value, "started")
                    await handler(context)
                    self._emit(stage.value, "completed")
                    completed.append(stage)
                    success = True
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "stage_failed",
                        stage=stage.value,
                        attempt=attempt + 1,
                        error=last_error,
                    )

                    # Consult planner for smart retry decisions
                    if self._planner and attempt < self.max_retries - 1:
                        decision = await self._planner.analyze_failure(
                            stage=stage,
                            error=last_error,
                            attempt=attempt + 1,
                        )
                        if not decision.should_retry:
                            logger.info(
                                "planner_abort",
                                stage=stage.value,
                                reason=decision.reason,
                            )
                            break
                        if decision.adjusted_params:
                            context.update(decision.adjusted_params)
                            logger.info(
                                "planner_retry",
                                stage=stage.value,
                                reason=decision.reason,
                                params=decision.adjusted_params,
                            )

            if not success:
                self._emit(stage.value, "failed", last_error)
                duration = time.monotonic() - start
                logger.error("pipeline_failed", stage=stage.value, error=last_error)
                unbind_contextvars("pipeline_run_id", "pipeline_project_id")
                return PipelineResult(
                    project_id=project_id,
                    run_id=run_id,
                    success=False,
                    completed_stages=completed,
                    failed_stage=stage,
                    error_message=last_error,
                    duration_seconds=duration,
                    report=context.get("report"),
                    sitemap=context.get("sitemap"),
                )

        self._emit("", "done")
        duration = time.monotonic() - start
        logger.info("pipeline_completed", run_id=run_id, duration=duration)
        unbind_contextvars("pipeline_run_id", "pipeline_project_id")
        return PipelineResult(
            project_id=project_id,
            run_id=run_id,
            success=True,
            completed_stages=completed,
            duration_seconds=duration,
            report=context.get("report"),
            sitemap=context.get("sitemap"),
        )

    async def _run_crawl(self, context: dict[str, Any]) -> None:
        url = context["url"]
        # Apply adjusted_params from planner (e.g., increased timeout/depth)
        max_depth = context.get("max_depth")
        if max_depth is not None:
            self._crawler._max_depth = int(max_depth)
        result = await self._crawler.crawl(url)
        context["crawl_result"] = result

    async def _run_map(self, context: dict[str, Any]) -> None:
        result = await self._mapper.build(
            context.get("crawl_result"),
            context["url"],
            openapi_spec=context.get("openapi_spec"),
        )
        context["sitemap"] = result

        # Persist sitemap to DB (#11)
        try:
            from sqlmodel.ext.asyncio.session import AsyncSession

            from breakthevibe.models.database import CrawlRun
            from breakthevibe.storage.database import get_engine

            async with AsyncSession(get_engine()) as session:
                try:
                    pid = int(context["project_id"])
                except (ValueError, TypeError):
                    logger.warning("invalid_project_id", project_id=context["project_id"])
                    return
                crawl_run = CrawlRun(
                    project_id=pid,
                    org_id=context.get("org_id", SENTINEL_ORG_ID),
                    status="completed",
                    site_map_json=result.model_dump_json(),
                )
                session.add(crawl_run)
                await session.commit()
        except Exception as e:
            logger.warning("sitemap_persist_failed", error=str(e))

    async def _run_generate(self, context: dict[str, Any]) -> None:
        if not self._generator:
            logger.warning("no_generator_available", reason="no LLM provider configured")
            context["test_cases"] = []
            return
        cases = await self._generator.generate(context.get("sitemap"))
        # Generate executable code for each test case
        if self._code_builder:
            for case in cases:
                case.code = self._code_builder.generate(case)
        context["test_cases"] = cases

    async def _run_tests(self, context: dict[str, Any]) -> None:
        cases = context.get("test_cases", [])
        if not cases:
            logger.info("no_test_cases_to_run")
            context["test_results"] = []
            return

        if not self._runner:
            logger.warning("no_runner_available")
            context["test_results"] = []
            return

        # Use scheduler to create execution plan if available
        if self._scheduler and self._code_builder:
            plan = self._scheduler.schedule(cases)
            results = []
            for suite in plan.suites:
                if not suite.cases:
                    continue
                suite_code = self._code_builder.generate_suite(suite.cases)
                if suite_code:
                    result = await self._runner.run(
                        suite_name=suite.name,
                        test_code=suite_code,
                        workers=suite.workers,
                    )
                    results.append(result)
                    if self._collector:
                        self._collector.add_execution_result(result)
            context["test_results"] = results
        elif self._code_builder:
            # Fallback: run all tests as a single suite
            suite_code = self._code_builder.generate_suite(cases)
            if suite_code:
                result = await self._runner.run(suite_name="all", test_code=suite_code)
                if self._collector:
                    self._collector.add_execution_result(result)
                context["test_results"] = [result]
        else:
            logger.warning("no_code_builder_available")
            context["test_results"] = []

    async def _run_report(self, context: dict[str, Any]) -> None:
        if self._collector:
            report = self._collector.build_report(
                project_id=context["project_id"],
                run_id=context.get("run_id", "auto"),
            )
            context["report"] = report
