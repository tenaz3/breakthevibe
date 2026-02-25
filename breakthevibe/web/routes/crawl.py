"""Crawl trigger and sitemap API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from breakthevibe.web.dependencies import project_repo

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["crawl"])


@router.post("/api/projects/{project_id}/crawl")
async def trigger_crawl(project_id: str) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("crawl_triggered", project_id=project_id)
    return {"status": "accepted", "project_id": project_id, "message": "Crawl started"}


@router.get("/api/projects/{project_id}/sitemap")
async def get_sitemap(project_id: str) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "pages": [], "api_endpoints": []}
