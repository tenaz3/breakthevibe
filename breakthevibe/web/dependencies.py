"""FastAPI dependency injection and shared state."""

from __future__ import annotations

from typing import Any

import structlog

from breakthevibe.config.settings import get_settings
from breakthevibe.storage.repositories.llm_settings import InMemoryLlmSettingsRepository
from breakthevibe.storage.repositories.projects import ProjectRepository

logger = structlog.get_logger(__name__)


def _create_project_repo() -> ProjectRepository | Any:
    """Create the appropriate project repository based on settings."""
    settings = get_settings()
    if settings.use_database:
        from sqlalchemy.ext.asyncio import create_async_engine

        from breakthevibe.storage.repositories.db_projects import DatabaseProjectRepository

        engine = create_async_engine(settings.database_url, echo=settings.debug)
        return DatabaseProjectRepository(engine)
    return ProjectRepository()


def _create_llm_settings_repo() -> Any:
    """Create the appropriate LLM settings repository."""
    settings = get_settings()
    if settings.use_database:
        from sqlalchemy.ext.asyncio import create_async_engine

        from breakthevibe.storage.repositories.llm_settings import LlmSettingsRepository

        engine = create_async_engine(settings.database_url, echo=settings.debug)
        return LlmSettingsRepository(engine)
    return InMemoryLlmSettingsRepository()


# Shared repositories
project_repo = _create_project_repo()
llm_settings_repo = _create_llm_settings_repo()

# Store pipeline run results in memory (replaced by DB in production)
pipeline_results: dict[str, dict[str, Any]] = {}


async def _persist_test_run(project_id: str, result_data: dict[str, Any]) -> None:
    """Persist test run results to DB when database is enabled."""
    settings = get_settings()
    if not settings.use_database:
        return

    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlmodel.ext.asyncio.session import AsyncSession

        from breakthevibe.models.database import TestRun

        engine = create_async_engine(settings.database_url, echo=settings.debug)
        async with AsyncSession(engine) as session:
            test_run = TestRun(
                project_id=int(project_id),
                status="completed" if result_data.get("success") else "failed",
                execution_mode="smart",
                total=len(result_data.get("completed_stages", [])),
                passed=1 if result_data.get("success") else 0,
                failed=0 if result_data.get("success") else 1,
            )
            session.add(test_run)
            await session.commit()
            logger.info("test_run_persisted", project_id=project_id)
    except Exception as e:
        logger.warning("test_run_persist_failed", error=str(e))


async def run_pipeline(project_id: str, url: str, rules_yaml: str = "") -> None:
    """Run the full pipeline as a background task."""
    from breakthevibe.web.pipeline import build_pipeline

    logger.info("pipeline_background_start", project_id=project_id, url=url)
    try:
        orchestrator = build_pipeline(project_id=project_id, url=url, rules_yaml=rules_yaml)
        result = await orchestrator.run(project_id=project_id, url=url, rules_yaml=rules_yaml)

        # Build rich result data including report details
        report = result.report
        result_data: dict[str, Any] = {
            "run_id": result.run_id,
            "success": result.success,
            "completed_stages": [s.value for s in result.completed_stages],
            "failed_stage": result.failed_stage.value if result.failed_stage else None,
            "error_message": result.error_message,
            "duration_seconds": result.duration_seconds,
        }
        if report:
            result_data["total"] = report.total_suites
            result_data["passed"] = report.passed_suites
            result_data["failed"] = report.failed_suites
            result_data["status"] = report.overall_status.value
            result_data["heal_warnings"] = report.heal_warnings
            result_data["suites"] = [
                {
                    "name": r.suite_name,
                    "success": r.success,
                    "stdout": r.stdout,
                    "duration": r.duration_seconds,
                    "step_captures": [
                        {
                            "name": sc.name,
                            "screenshot_path": sc.screenshot_path,
                            "network_calls": sc.network_calls,
                            "console_logs": sc.console_logs,
                        }
                        for sc in r.step_captures
                    ],
                }
                for r in report.results
            ]
        pipeline_results[project_id] = result_data

        # Also persist to DB
        await _persist_test_run(project_id, result_data)

        status = "completed" if result.success else "failed"
        await project_repo.update(project_id, status=status, last_run_id=result.run_id)
        logger.info("pipeline_background_done", project_id=project_id, success=result.success)

    except Exception as e:
        logger.error("pipeline_background_error", project_id=project_id, error=str(e))
        await project_repo.update(project_id, status="failed")
        pipeline_results[project_id] = {
            "success": False,
            "error_message": str(e),
        }
