"""FastAPI dependency injection and shared state."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from breakthevibe.config.settings import SENTINEL_ORG_ID, get_settings
from breakthevibe.storage.database import get_engine
from breakthevibe.storage.repositories.crawl_runs import CrawlRunRepository
from breakthevibe.storage.repositories.db_projects import DatabaseProjectRepository
from breakthevibe.storage.repositories.llm_settings import LlmSettingsRepository
from breakthevibe.storage.repositories.test_runs import TestRunRepository
from breakthevibe.storage.repositories.users import DatabaseUserRepository
from breakthevibe.storage.repositories.webauthn import DatabaseWebAuthnCredentialRepository

logger = structlog.get_logger(__name__)


def _create_passkey_service() -> Any:
    """Create the PasskeyService if auth_mode == 'passkey'."""
    settings = get_settings()
    if settings.auth_mode != "passkey":
        return None

    from breakthevibe.web.auth.passkey_service import PasskeyService

    return PasskeyService(
        credential_repo=webauthn_credential_repo,
        user_repo=user_repo,
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        origin=settings.webauthn_origin,
    )


# Shared repositories — always PostgreSQL
project_repo = DatabaseProjectRepository(get_engine())
llm_settings_repo = LlmSettingsRepository(get_engine())
user_repo = DatabaseUserRepository(get_engine())
webauthn_credential_repo = DatabaseWebAuthnCredentialRepository(get_engine())
test_run_repo = TestRunRepository(get_engine())
crawl_run_repo = CrawlRunRepository(get_engine())
passkey_service = _create_passkey_service()

# Per-pipeline locks keyed by "{org_id}:{project_id}" (process-local)
_pipeline_locks: dict[str, asyncio.Lock] = {}


def _lock_key(org_id: str, project_id: str) -> str:
    return f"{org_id}:{project_id}"


def _get_pipeline_lock(org_id: str, project_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific org+project."""
    key = _lock_key(org_id, project_id)
    if key not in _pipeline_locks:
        _pipeline_locks[key] = asyncio.Lock()
    return _pipeline_locks[key]


async def run_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
    org_id: str = SENTINEL_ORG_ID,
) -> None:
    """Run the full pipeline as a background task."""
    from breakthevibe.web.pipeline import build_pipeline
    from breakthevibe.web.sse import PipelineProgressEvent, progress_bus

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
            result = await orchestrator.run(
                project_id=project_id,
                url=url,
                rules_yaml=rules_yaml,
            )

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

            # Persist to DB
            try:
                await test_run_repo.save_pipeline_result(
                    project_id=int(project_id),
                    org_id=org_id,
                    result_data=result_data,
                )
            except (ValueError, TypeError, OSError) as persist_err:
                logger.warning("test_run_persist_failed", error=str(persist_err))

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
            # Persist the failure to DB
            try:
                await test_run_repo.save_pipeline_result(
                    project_id=int(project_id),
                    org_id=org_id,
                    result_data={"success": False, "error_message": str(e)},
                )
            except (ValueError, TypeError, OSError) as persist_err:
                logger.warning("test_run_persist_failed", error=str(persist_err))
