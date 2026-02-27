"""Crawl trigger and sitemap API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from breakthevibe.audit.logger import audit
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import (
    _cache_key,
    pipeline_results,
    project_repo,
    run_pipeline,
)

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["crawl"])


@router.post("/api/projects/{project_id}/crawl")
async def trigger_crawl(
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

    await project_repo.update(project_id, org_id=tenant.org_id, status="crawling")
    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="pipeline.started",
        resource_type="project",
        resource_id=project_id,
        details={"trigger": "crawl", "url": project["url"]},
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("crawl_triggered", project_id=project_id, org_id=tenant.org_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Crawl started",
    }


@router.get("/api/projects/{project_id}/sitemap")
async def get_sitemap(
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    key = _cache_key(tenant.org_id, project_id)
    result = pipeline_results.get(key, {})
    sitemap = result.get("sitemap", {})
    return {
        "project_id": project_id,
        "pages": sitemap.get("pages", []),
        "api_endpoints": sitemap.get("api_endpoints", []),
    }
