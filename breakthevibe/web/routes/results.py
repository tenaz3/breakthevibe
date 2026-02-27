"""Test results API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Depends

from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import test_run_repo

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["results"])


@router.get("/api/runs/{run_id}/results")
async def get_run_results(
    run_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    result = await test_run_repo.get_by_run_uuid(run_id, org_id=tenant.org_id)
    if not result:
        return {
            "run_id": run_id,
            "status": "not_found",
            "suites": [],
            "total": 0,
            "passed": 0,
            "failed": 0,
        }
    return {
        "run_id": run_id,
        "status": "completed" if result.get("success") else "failed",
        "completed_stages": result.get("completed_stages", []),
        "failed_stage": result.get("failed_stage"),
        "error_message": result.get("error_message", ""),
        "duration_seconds": result.get("duration_seconds", 0),
        "total": result.get("total", 0),
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
    }


@router.get("/api/projects/{project_id}/results")
async def get_project_results(
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        return {"project_id": project_id, "status": "no_runs"}

    result = await test_run_repo.get_latest_for_project(pid, org_id=tenant.org_id)
    if not result:
        return {"project_id": project_id, "status": "no_runs"}
    return {
        "project_id": project_id,
        "run_id": result.get("run_id"),
        "status": "completed" if result.get("success") else "failed",
        "completed_stages": result.get("completed_stages", []),
        "failed_stage": result.get("failed_stage"),
        "error_message": result.get("error_message", ""),
        "duration_seconds": result.get("duration_seconds", 0),
        "total": result.get("total", 0),
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
    }
