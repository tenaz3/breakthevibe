"""Crawl trigger and sitemap API routes."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException

from breakthevibe.web.dependencies import pipeline_results, project_repo, run_pipeline

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["crawl"])


@router.post("/api/projects/{project_id}/crawl")
async def trigger_crawl(project_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
    )

    await project_repo.update(project_id, status="crawling")
    logger.info("crawl_triggered", project_id=project_id)
    return {"status": "accepted", "project_id": project_id, "message": "Crawl started"}


@router.get("/api/projects/{project_id}/sitemap")
async def get_sitemap(project_id: str) -> dict[str, Any]:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Read sitemap from pipeline results cache (populated after crawl completes)
    result = pipeline_results.get(project_id, {})
    sitemap = result.get("sitemap", {})
    return {
        "project_id": project_id,
        "pages": sitemap.get("pages", []),
        "api_endpoints": sitemap.get("api_endpoints", []),
    }
