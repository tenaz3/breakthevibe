"""Test generation and execution API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from breakthevibe.audit.logger import audit
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import project_repo, run_pipeline

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["tests"])


@router.post("/api/projects/{project_id}/generate")
async def trigger_generate(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
        org_id=tenant.org_id,
    )

    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="pipeline.started",
        resource_type="project",
        resource_id=project_id,
        details={"trigger": "generate"},
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("generate_triggered", project_id=project_id, org_id=tenant.org_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Test generation started",
    }


@router.post("/api/projects/{project_id}/run")
async def trigger_run(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
        org_id=tenant.org_id,
    )

    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="pipeline.started",
        resource_type="project",
        resource_id=project_id,
        details={"trigger": "run"},
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("run_triggered", project_id=project_id, org_id=tenant.org_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Test run started",
    }
