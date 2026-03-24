"""Test generation and execution API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from breakthevibe.agent.orchestrator import PipelineStage
from breakthevibe.audit.logger import audit
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import project_repo, run_pipeline, test_case_repo

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
        stages=[PipelineStage.CRAWL, PipelineStage.MAP, PipelineStage.GENERATE],
        request_id=request.headers.get("x-request-id"),
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
        stages=[
            PipelineStage.CRAWL,
            PipelineStage.MAP,
            PipelineStage.GENERATE,
            PipelineStage.RUN,
            PipelineStage.REPORT,
        ],
        request_id=request.headers.get("x-request-id"),
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


@router.post("/api/projects/{project_id}/run-cached")
async def trigger_run_cached(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    """Re-run using cached test cases — skips crawl, map, and LLM generation."""
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid project ID")  # noqa: B904

    cache_meta = await test_case_repo.get_cache_meta(pid, org_id=tenant.org_id)
    if not cache_meta:
        raise HTTPException(
            status_code=409,
            detail="No cached test cases. Run a full pipeline first.",
        )

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
        org_id=tenant.org_id,
        stages=[PipelineStage.RUN, PipelineStage.REPORT],
        request_id=request.headers.get("x-request-id"),
    )

    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="pipeline.started",
        resource_type="project",
        resource_id=project_id,
        details={"trigger": "run-cached", "cached_tests": cache_meta["count"]},
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info(
        "run_cached_triggered",
        project_id=project_id,
        cached_tests=cache_meta["count"],
    )
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": f"Re-running {cache_meta['count']} cached tests",
    }


@router.post("/api/projects/{project_id}/regenerate")
async def trigger_regenerate(
    project_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    """Force full pipeline with fresh LLM generation, ignoring cache."""
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
        org_id=tenant.org_id,
        stages=[
            PipelineStage.CRAWL,
            PipelineStage.MAP,
            PipelineStage.GENERATE,
            PipelineStage.RUN,
            PipelineStage.REPORT,
        ],
        request_id=request.headers.get("x-request-id"),
        force_regenerate=True,
    )

    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="pipeline.started",
        resource_type="project",
        resource_id=project_id,
        details={"trigger": "regenerate"},
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("regenerate_triggered", project_id=project_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Full regeneration started",
    }


@router.get("/api/projects/{project_id}/test-cases")
async def list_test_cases(
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    """Return cached test cases and cache metadata."""
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid project ID")  # noqa: B904

    cache_meta = await test_case_repo.get_cache_meta(pid, org_id=tenant.org_id)
    if not cache_meta:
        return {"project_id": project_id, "cached": False, "test_cases": []}

    cases = await test_case_repo.load_for_project(pid, org_id=tenant.org_id)
    return {
        "project_id": project_id,
        "cached": True,
        "sitemap_hash": cache_meta["sitemap_hash"],
        "updated_at": str(cache_meta["updated_at"]),
        "count": cache_meta["count"],
        "test_cases": [
            {
                "name": c.name,
                "category": c.category.value,
                "description": c.description,
                "route": c.route,
                "steps": len(c.steps),
            }
            for c in cases
        ],
    }
