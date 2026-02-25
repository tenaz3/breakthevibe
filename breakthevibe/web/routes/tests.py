"""Test generation and execution API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException

from breakthevibe.web.dependencies import project_repo, run_pipeline

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["tests"])


@router.post("/api/projects/{project_id}/generate")
async def trigger_generate(project_id: str, background_tasks: BackgroundTasks) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
    )

    logger.info("generate_triggered", project_id=project_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Test generation started",
    }


@router.post("/api/projects/{project_id}/run")
async def trigger_run(project_id: str, background_tasks: BackgroundTasks) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
    )

    logger.info("run_triggered", project_id=project_id)
    return {
        "status": "accepted",
        "project_id": project_id,
        "message": "Test run started",
    }
