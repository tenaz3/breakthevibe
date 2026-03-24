"""Test results API routes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from breakthevibe.config.settings import get_settings
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
    project_id: int,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    runs = await test_run_repo.list_for_project(project_id, org_id=tenant.org_id, limit=20)
    if not runs:
        return {"project_id": project_id, "status": "no_runs", "runs": []}
    return {
        "project_id": project_id,
        "status": "has_runs",
        "runs": [
            {
                "run_id": r.get("run_id"),
                "status": "completed" if r.get("success") else "failed",
                "completed_stages": r.get("completed_stages", []),
                "failed_stage": r.get("failed_stage"),
                "error_message": r.get("error_message", ""),
                "duration_seconds": r.get("duration_seconds", 0),
                "total": r.get("total", 0),
                "passed": r.get("passed", 0),
                "failed": r.get("failed", 0),
            }
            for r in runs
        ],
    }


@router.get("/artifacts/{project_id}/{rest_of_path:path}")
async def serve_artifact(
    project_id: str,
    rest_of_path: str,
    tenant: TenantContext = Depends(get_tenant),
) -> FileResponse:
    """Serve artifact files (screenshots, videos) with path traversal protection."""
    settings = get_settings()
    base = Path(settings.artifacts_dir).expanduser().resolve()
    file_path = (base / project_id / rest_of_path).resolve()
    # Path traversal protection
    if not str(file_path).startswith(str(base)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    # Determine media type
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webm": "video/webm",
        ".mp4": "video/mp4",
        ".json": "application/json",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)
