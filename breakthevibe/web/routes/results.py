"""Test results API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from breakthevibe.web.dependencies import pipeline_results

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["results"])


@router.get("/api/runs/{run_id}/results")
async def get_run_results(run_id: str) -> dict:
    # Search through pipeline results for matching run_id
    for _project_id, result in pipeline_results.items():
        if result.get("run_id") == run_id:
            return {
                "run_id": run_id,
                "status": "completed" if result.get("success") else "failed",
                "completed_stages": result.get("completed_stages", []),
                "failed_stage": result.get("failed_stage"),
                "error_message": result.get("error_message", ""),
                "duration_seconds": result.get("duration_seconds", 0),
            }

    return {
        "run_id": run_id,
        "status": "not_found",
        "suites": [],
        "total": 0,
        "passed": 0,
        "failed": 0,
    }


@router.get("/api/projects/{project_id}/results")
async def get_project_results(project_id: str) -> dict:
    result = pipeline_results.get(project_id)
    if not result:
        return {"project_id": project_id, "status": "no_runs"}
    return {
        "project_id": project_id,
        "run_id": result.get("run_id"),
        "status": "completed" if result.get("success") else "failed",
        "completed_stages": result.get("completed_stages", []),
        "error_message": result.get("error_message", ""),
        "duration_seconds": result.get("duration_seconds", 0),
    }
