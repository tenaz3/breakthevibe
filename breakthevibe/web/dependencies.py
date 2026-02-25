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


async def run_pipeline(project_id: str, url: str, rules_yaml: str = "") -> None:
    """Run the full pipeline as a background task."""
    from breakthevibe.web.pipeline import build_pipeline

    logger.info("pipeline_background_start", project_id=project_id, url=url)
    try:
        orchestrator = build_pipeline(project_id=project_id, url=url, rules_yaml=rules_yaml)
        result = await orchestrator.run(project_id=project_id, url=url, rules_yaml=rules_yaml)

        # Store result and update project status
        pipeline_results[project_id] = {
            "run_id": result.run_id,
            "success": result.success,
            "completed_stages": [s.value for s in result.completed_stages],
            "failed_stage": result.failed_stage.value if result.failed_stage else None,
            "error_message": result.error_message,
            "duration_seconds": result.duration_seconds,
        }

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
