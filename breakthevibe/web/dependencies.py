"""FastAPI dependency injection and shared state."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from breakthevibe.config.settings import SENTINEL_ORG_ID, get_settings
from breakthevibe.storage.repositories.llm_settings import InMemoryLlmSettingsRepository
from breakthevibe.storage.repositories.projects import ProjectRepository

logger = structlog.get_logger(__name__)


def _create_project_repo() -> ProjectRepository | Any:
    """Create the appropriate project repository based on settings."""
    settings = get_settings()
    if settings.use_database:
        from breakthevibe.storage.database import get_engine
        from breakthevibe.storage.repositories.db_projects import (
            DatabaseProjectRepository,
        )

        return DatabaseProjectRepository(get_engine())
    return ProjectRepository()


def _create_llm_settings_repo() -> Any:
    """Create the appropriate LLM settings repository."""
    settings = get_settings()
    if settings.use_database:
        from breakthevibe.storage.database import get_engine
        from breakthevibe.storage.repositories.llm_settings import LlmSettingsRepository

        return LlmSettingsRepository(get_engine())
    return InMemoryLlmSettingsRepository()


# Shared repositories
project_repo = _create_project_repo()
llm_settings_repo = _create_llm_settings_repo()

# Store pipeline run results in memory keyed by "{org_id}:{project_id}"
pipeline_results: dict[str, dict[str, Any]] = {}

# Per-pipeline locks keyed by "{org_id}:{project_id}"
_pipeline_locks: dict[str, asyncio.Lock] = {}


def _cache_key(org_id: str, project_id: str) -> str:
    """Build a tenant-namespaced cache key."""
    return f"{org_id}:{project_id}"


def _get_pipeline_lock(org_id: str, project_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific org+project."""
    key = _cache_key(org_id, project_id)
    if key not in _pipeline_locks:
        _pipeline_locks[key] = asyncio.Lock()
    return _pipeline_locks[key]


async def _persist_test_run(
    project_id: str,
    result_data: dict[str, Any],
    org_id: str = SENTINEL_ORG_ID,
) -> None:
    """Persist test run results to DB when database is enabled."""
    settings = get_settings()
    if not settings.use_database:
        return

    try:
        from sqlmodel.ext.asyncio.session import AsyncSession

        from breakthevibe.models.database import TestRun
        from breakthevibe.storage.database import get_engine

        async with AsyncSession(get_engine()) as session:
            try:
                pid = int(project_id)
            except (ValueError, TypeError):
                logger.warning("invalid_project_id_for_persist", project_id=project_id)
                return
            test_run = TestRun(
                project_id=pid,
                org_id=org_id,
                status="completed" if result_data.get("success") else "failed",
                execution_mode="smart",
                total=len(result_data.get("completed_stages", [])),
                passed=1 if result_data.get("success") else 0,
                failed=0 if result_data.get("success") else 1,
            )
            session.add(test_run)
            await session.commit()
            logger.info("test_run_persisted", project_id=project_id, org_id=org_id)
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("test_run_persist_failed", error=str(e))


async def run_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
    org_id: str = SENTINEL_ORG_ID,
) -> None:
    """Run the full pipeline as a background task."""
    from breakthevibe.web.pipeline import build_pipeline
    from breakthevibe.web.sse import PipelineProgressEvent, progress_bus

    cache_key = _cache_key(org_id, project_id)
    lock = _get_pipeline_lock(org_id, project_id)
    if lock.locked():
        logger.warning("pipeline_already_running", project_id=project_id, org_id=org_id)
        return

    async with lock:
        logger.info(
            "pipeline_background_start",
            project_id=project_id,
            org_id=org_id,
            url=url,
        )

        # Clear stale progress state from any previous run
        progress_bus.clear(project_id)

        def _progress(stage: str, status: str, error: str = "") -> None:
            progress_bus.notify(
                PipelineProgressEvent(
                    project_id=project_id,
                    stage=stage,
                    status=status,
                    error=error,
                )
            )

        try:
            orchestrator = await build_pipeline(
                project_id=project_id,
                url=url,
                rules_yaml=rules_yaml,
                progress_callback=_progress,
                org_id=org_id,
            )
            result = await orchestrator.run(project_id=project_id, url=url, rules_yaml=rules_yaml)

            # Build rich result data including report details
            report = result.report
            result_data: dict[str, Any] = {
                "run_id": result.run_id,
                "success": result.success,
                "completed_stages": [s.value for s in result.completed_stages],
                "failed_stage": (result.failed_stage.value if result.failed_stage else None),
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
            # Store sitemap for the /api/projects/{id}/sitemap endpoint
            if result.sitemap:
                result_data["sitemap"] = (
                    result.sitemap.model_dump()
                    if hasattr(result.sitemap, "model_dump")
                    else result.sitemap
                )

            pipeline_results[cache_key] = result_data

            # Also persist to DB
            await _persist_test_run(project_id, result_data, org_id=org_id)

            status = "completed" if result.success else "failed"
            await project_repo.update(
                project_id, org_id=org_id, status=status, last_run_id=result.run_id
            )
            logger.info(
                "pipeline_background_done",
                project_id=project_id,
                org_id=org_id,
                success=result.success,
            )

        except Exception as e:
            logger.error(
                "pipeline_background_error",
                project_id=project_id,
                org_id=org_id,
                error=str(e),
            )
            progress_bus.notify(
                PipelineProgressEvent(
                    project_id=project_id,
                    stage="",
                    status="failed",
                    error=str(e),
                )
            )
            await project_repo.update(project_id, org_id=org_id, status="failed")
            pipeline_results[cache_key] = {
                "success": False,
                "error_message": str(e),
            }
