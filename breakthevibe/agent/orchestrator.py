"""Pipeline orchestrator — coordinates all stages."""

from __future__ import annotations

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
    warnings: list[str] = field(default_factory=list)


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
            try:
                self._progress_callback(stage, status, error)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "progress_callback_failed",
                    stage=stage,
                    status=status,
                    error=str(exc),
                )

    async def run(
        self,
        project_id: str,
        url: str,
        rules_yaml: str = "",
        openapi_spec: dict[str, Any] | None = None,
        org_id: str = SENTINEL_ORG_ID,
        active_stages: list[PipelineStage] | None = None,
        pre_context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Execute the pipeline, optionally restricted to a subset of stages.

        Args:
            project_id: The project identifier.
            url: The target URL to crawl/test.
            rules_yaml: Optional YAML rules for the pipeline.
            openapi_spec: Optional OpenAPI spec for API testing.
            org_id: The organisation identifier for multi-tenant scoping.
            active_stages: Ordered list of stages to execute. Defaults to all
                five stages when ``None``.
            pre_context: Optional pre-populated context (e.g. cached test cases).
        """
        run_id = str(uuid.uuid4())
        start = time.monotonic()
        completed: list[PipelineStage] = []

        # Bind correlation ID for all logs within this pipeline run (#12)
        bind_contextvars(pipeline_run_id=run_id, pipeline_project_id=project_id)

        active_stages_set: set[PipelineStage] = (
            set(active_stages) if active_stages is not None else set(PipelineStage)
        )

        logger.info(
            "pipeline_started",
            project_id=project_id,
            run_id=run_id,
            url=url,
            active_stages=[s.value for s in (active_stages or list(PipelineStage))],
        )

        all_stages = [
            (PipelineStage.CRAWL, self._run_crawl),
            (PipelineStage.MAP, self._run_map),
            (PipelineStage.GENERATE, self._run_generate),
            (PipelineStage.RUN, self._run_tests),
            (PipelineStage.REPORT, self._run_report),
        ]

        stages = [(s, h) for s, h in all_stages if s in active_stages_set]

        context: dict[str, Any] = {
            "url": url,
            "rules_yaml": rules_yaml,
            "project_id": project_id,
            "run_id": run_id,
            "openapi_spec": openapi_spec,
            "org_id": org_id,
        }
        if pre_context:
            context.update(pre_context)

        try:
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
                        # Broad catch: pipeline stages (crawl, map, generate, run) raise
                        # heterogeneous exception types; all must be caught to drive retry logic.
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
                        warnings=context.get("pipeline_warnings", []),
                    )

            self._emit("", "done")
            duration = time.monotonic() - start
            logger.info("pipeline_completed", run_id=run_id, duration=duration)
            pipeline_warnings = context.get("pipeline_warnings", [])
            return PipelineResult(
                project_id=project_id,
                run_id=run_id,
                success=not pipeline_warnings,
                completed_stages=completed,
                duration_seconds=duration,
                report=context.get("report"),
                sitemap=context.get("sitemap"),
                warnings=pipeline_warnings,
            )
        finally:
            unbind_contextvars("pipeline_run_id", "pipeline_project_id")

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
                from breakthevibe.utils.sitemap_hash import compute_sitemap_hash

                s_hash = compute_sitemap_hash(result)
                crawl_run = CrawlRun(
                    project_id=pid,
                    org_id=context.get("org_id", SENTINEL_ORG_ID),
                    status="completed",
                    site_map_json=result.model_dump_json(),
                    sitemap_hash=s_hash,
                )
                session.add(crawl_run)
                await session.commit()
                context["crawl_run_id"] = crawl_run.id
                context["sitemap_hash"] = s_hash
        except Exception as e:
            # Broad catch: DB persist is best-effort; SQLAlchemy, asyncpg, and
            # serialization errors must not abort the pipeline.
            logger.warning("sitemap_persist_failed", error=str(e))

    async def _run_generate(self, context: dict[str, Any]) -> None:
        if not self._generator:
            raise RuntimeError(
                "No LLM provider configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
                "GOOGLE_API_KEY, or ensure Ollama is running to generate tests."
            )
        cases = await self._generator.generate(context.get("sitemap"))
        logger.info("generate_produced", test_case_count=len(cases))
        if not cases:
            logger.error(
                "generate_returned_empty_cases",
                project_id=context.get("project_id"),
                hint="LLM returned no parseable test cases. Check LLM config, API key, and model.",
            )
            context["generate_warning"] = (
                "No test cases generated — the LLM response could not be parsed into "
                "valid test cases. Check your LLM configuration and API key."
            )
        # Generate executable code for each test case
        if self._code_builder:
            for case in cases:
                case.code = self._code_builder.generate(case)
        context["test_cases"] = cases

        # Cache generated test cases to DB (best-effort)
        if cases:
            try:
                from breakthevibe.storage.database import get_engine
                from breakthevibe.storage.repositories.test_cases import TestCaseRepository

                repo = TestCaseRepository(get_engine())
                await repo.save_batch(
                    project_id=int(context["project_id"]),
                    org_id=context.get("org_id", SENTINEL_ORG_ID),
                    crawl_run_id=context.get("crawl_run_id"),
                    sitemap_hash=context.get("sitemap_hash", ""),
                    cases=cases,
                )
            except Exception as e:
                logger.warning("test_case_cache_failed", error=str(e))

    async def _run_tests(self, context: dict[str, Any]) -> None:
        cases = context.get("test_cases", [])
        if not cases:
            warning = context.get("generate_warning", "")
            logger.error(
                "no_test_cases_to_run",
                project_id=context.get("project_id"),
                generate_warning=warning,
                hint="Generate stage produced 0 test cases — skipping test execution.",
            )
            context["test_results"] = []
            context.setdefault(
                "pipeline_warnings",
                [],
            ).append(
                warning
                or "Generate stage produced 0 test cases. Check LLM configuration and rules."
            )
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
                    logger.info(
                        "suite_execution_result",
                        suite=suite.name,
                        success=result.success,
                        exit_code=result.exit_code,
                        duration=result.duration_seconds,
                    )
                    if not result.success:
                        logger.warning(
                            "suite_failed",
                            suite=suite.name,
                            exit_code=result.exit_code,
                            timed_out=result.timed_out,
                        )
                    if self._collector:
                        self._collector.add_execution_result(result)
            context["test_results"] = results
        elif self._code_builder:
            # Fallback: run all tests as a single suite
            suite_code = self._code_builder.generate_suite(cases)
            if suite_code:
                result = await self._runner.run(suite_name="all", test_code=suite_code)
                logger.info(
                    "suite_execution_result",
                    suite="all",
                    success=result.success,
                    exit_code=result.exit_code,
                    duration=result.duration_seconds,
                )
                if not result.success:
                    logger.warning(
                        "suite_failed",
                        suite="all",
                        exit_code=result.exit_code,
                        timed_out=result.timed_out,
                    )
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
            if report:
                logger.info(
                    "report_summary",
                    total_suites=report.total_suites,
                    passed_suites=report.passed_suites,
                    failed_suites=report.failed_suites,
                    overall_status=report.overall_status.value,
                )
            else:
                logger.warning("report_is_none", project_id=context.get("project_id"))
