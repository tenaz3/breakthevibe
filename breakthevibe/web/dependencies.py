"""FastAPI dependency injection and shared state."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from breakthevibe.agent.orchestrator import PipelineStage
from breakthevibe.config.settings import SENTINEL_ORG_ID, get_settings
from breakthevibe.storage.database import get_engine
from breakthevibe.storage.repositories.crawl_runs import CrawlRunRepository
from breakthevibe.storage.repositories.db_projects import DatabaseProjectRepository
from breakthevibe.storage.repositories.llm_settings import LlmSettingsRepository
from breakthevibe.storage.repositories.test_cases import TestCaseRepository
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
test_case_repo = TestCaseRepository(get_engine())
crawl_run_repo = CrawlRunRepository(get_engine())
passkey_service = _create_passkey_service()

# Per-pipeline locks keyed by "{org_id}:{project_id}" (process-local)
_pipeline_locks: dict[str, asyncio.Lock] = {}


def _lock_key(org_id: str, project_id: str) -> str:
    return f"{org_id}:{project_id}"


def _get_pipeline_lock(org_id: str, project_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific org+project."""
    key = _lock_key(org_id, project_id)
    return _pipeline_locks.setdefault(key, asyncio.Lock())


ALL_STAGES: list[PipelineStage] = list(PipelineStage)


async def run_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
    org_id: str = SENTINEL_ORG_ID,
    stages: list[PipelineStage] | None = None,
    request_id: str | None = None,
    force_regenerate: bool = False,
    cached_test_cases: list[Any] | None = None,
) -> None:
    """Run a (possibly partial) pipeline as a background task.

    Args:
        project_id: The project identifier.
        url: The target URL.
        rules_yaml: Optional YAML rules for the pipeline.
        org_id: Organisation identifier for multi-tenant scoping.
        stages: Ordered list of ``PipelineStage`` values to execute.
            Defaults to all five stages when ``None``.
        request_id: Optional request correlation ID for structured logging.
        force_regenerate: When True, skip cache check and force LLM regeneration.
    """
    import structlog.contextvars

    from breakthevibe.web.pipeline import build_pipeline
    from breakthevibe.web.sse import PipelineProgressEvent, progress_bus

    active_stages = stages if stages is not None else ALL_STAGES

    if request_id:
        structlog.contextvars.bind_contextvars(request_id=request_id)

    # Validate and parse project_id once; all int-typed downstream calls use pid.
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        logger.error("invalid_project_id", project_id=project_id)
        return

    lock = _get_pipeline_lock(org_id, project_id)
    if lock.locked():
        logger.warning("pipeline_already_running", project_id=project_id, org_id=org_id)
        return

    try:
        async with lock:
            logger.info(
                "pipeline_background_start",
                project_id=project_id,
                org_id=org_id,
                url=url,
                stages=[s.value for s in active_stages],
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
                # Cache check: skip CRAWL/MAP/GENERATE if cached tests are valid
                pre_context: dict[str, Any] | None = None
                # Explicit cached cases from run-cached endpoint
                if cached_test_cases:
                    pre_context = {"test_cases": cached_test_cases}
                    logger.info(
                        "using_explicit_cached_cases",
                        project_id=project_id,
                        count=len(cached_test_cases),
                    )
                elif not force_regenerate and PipelineStage.RUN in active_stages:
                    cache_meta = await test_case_repo.get_cache_meta(pid, org_id)
                    if cache_meta:
                        latest_crawl = await crawl_run_repo.get_latest_for_project(pid, org_id)
                        if (
                            latest_crawl
                            and latest_crawl.get("sitemap_hash") == cache_meta["sitemap_hash"]
                        ):
                            cached_cases = await test_case_repo.load_for_project(pid, org_id)
                            if cached_cases:
                                logger.info(
                                    "cache_hit",
                                    project_id=project_id,
                                    count=len(cached_cases),
                                    sitemap_hash=cache_meta["sitemap_hash"],
                                )
                                active_stages = [
                                    PipelineStage.RUN,
                                    PipelineStage.REPORT,
                                ]
                                pre_context = {"test_cases": cached_cases}

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
                    org_id=org_id,
                    active_stages=active_stages,
                    pre_context=pre_context,
                )

                logger.info(
                    "pipeline_stages_summary",
                    project_id=project_id,
                    requested_stages=[s.value for s in active_stages],
                    completed_stages=[s.value for s in result.completed_stages],
                    failed_stage=(result.failed_stage.value if result.failed_stage else None),
                )

                # Build rich result data including report details
                report = result.report
                logger.info(
                    "pipeline_report_check",
                    project_id=project_id,
                    report_exists=report is not None,
                    overall_status=(report.overall_status.value if report else None),
                    total_suites=(report.total_suites if report else 0),
                    passed_suites=(report.passed_suites if report else 0),
                    failed_suites=(report.failed_suites if report else 0),
                )
                result_data: dict[str, Any] = {
                    "run_id": result.run_id,
                    "success": result.success,
                    "completed_stages": [s.value for s in result.completed_stages],
                    "failed_stage": (result.failed_stage.value if result.failed_stage else None),
                    "error_message": result.error_message,
                    "duration_seconds": result.duration_seconds,
                    "warnings": result.warnings,
                }
                if report:
                    result_data["total"] = report.total_suites
                    result_data["passed"] = report.passed_suites
                    result_data["failed"] = report.failed_suites
                    result_data["status"] = report.overall_status.value
                    result_data["heal_warnings"] = report.heal_warnings
                    result_data["diffs"] = report.diffs
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
                                    "diff_result": sc.diff_result,
                                    "heal_info": sc.heal_info,
                                }
                                for sc in r.step_captures
                            ],
                        }
                        for r in report.results
                    ]

                # Persist to DB — only save a TestRun when tests actually executed
                # (skip for generate-only runs that produce no report)
                if report:
                    try:
                        await test_run_repo.save_pipeline_result(
                            project_id=pid,
                            org_id=org_id,
                            result_data=result_data,
                        )
                    except (ValueError, TypeError, OSError) as persist_err:
                        logger.warning("test_run_persist_failed", error=str(persist_err))

                if report:
                    status = "completed" if result.success else "failed"
                    await project_repo.update(
                        project_id, org_id=org_id, status=status, last_run_id=result.run_id
                    )
                else:
                    # Generate-only run — mark as ready, not completed
                    await project_repo.update(project_id, org_id=org_id, status="ready")
                logger.info(
                    "pipeline_background_done",
                    project_id=project_id,
                    org_id=org_id,
                    success=result.success,
                )

            except Exception as e:
                # Broad catch: top-level background task must catch all exceptions to
                # ensure the progress bus is always notified on failure regardless of cause.
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
                        project_id=pid,
                        org_id=org_id,
                        result_data={"success": False, "error_message": str(e)},
                    )
                except (ValueError, TypeError, OSError) as persist_err:
                    logger.warning("test_run_persist_failed", error=str(persist_err))
    finally:
        # Clean up the lock entry once the pipeline is done so _pipeline_locks
        # doesn't grow unbounded over the lifetime of the process (#4).
        _pipeline_locks.pop(_lock_key(org_id, project_id), None)
