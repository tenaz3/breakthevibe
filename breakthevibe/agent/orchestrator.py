"""Pipeline orchestrator — coordinates all stages."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

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


class PipelineOrchestrator:
    """Coordinates the full pipeline: crawl -> map -> generate -> run -> report."""

    def __init__(
        self,
        crawler: Any = None,
        mapper: Any = None,
        generator: Any = None,
        runner: Any = None,
        collector: Any = None,
        planner: Any = None,
    ) -> None:
        self._crawler = crawler
        self._mapper = mapper
        self._generator = generator
        self._runner = runner
        self._collector = collector
        self._planner = planner
        self.max_retries: int = 1

    async def run(
        self,
        project_id: str,
        url: str,
        rules_yaml: str = "",
    ) -> PipelineResult:
        """Execute the full pipeline."""
        run_id = str(uuid.uuid4())
        start = time.monotonic()
        completed: list[PipelineStage] = []

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
        }

        for stage, handler in stages:
            success = False
            last_error = ""

            for attempt in range(self.max_retries):
                try:
                    logger.info("stage_starting", stage=stage.value, attempt=attempt + 1)
                    await handler(context)
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

            if not success:
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
                )

        duration = time.monotonic() - start
        logger.info("pipeline_completed", run_id=run_id, duration=duration)
        return PipelineResult(
            project_id=project_id,
            run_id=run_id,
            success=True,
            completed_stages=completed,
            duration_seconds=duration,
        )

    async def _run_crawl(self, context: dict[str, Any]) -> None:
        result = await self._crawler.crawl(context["url"])
        context["crawl_result"] = result

    async def _run_map(self, context: dict[str, Any]) -> None:
        result = await self._mapper.build(context.get("crawl_result"))
        context["sitemap"] = result

    async def _run_generate(self, context: dict[str, Any]) -> None:
        result = await self._generator.generate(context.get("sitemap"))
        context["test_cases"] = result

    async def _run_tests(self, context: dict[str, Any]) -> None:
        result = await self._runner.run(context.get("test_cases"))
        context["test_results"] = result

    async def _run_report(self, context: dict[str, Any]) -> None:
        if self._collector:
            self._collector.build_report(
                project_id=context["project_id"],
                run_id="auto",
            )
