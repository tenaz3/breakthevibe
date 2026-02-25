"""Test generation and execution API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from breakthevibe.web.dependencies import project_repo

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["tests"])


@router.post("/api/projects/{project_id}/generate")
async def trigger_generate(project_id: str) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("generate_triggered", project_id=project_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Test generation started",
    }


@router.post("/api/projects/{project_id}/run")
async def trigger_run(project_id: str) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("run_triggered", project_id=project_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Test run started",
    }
