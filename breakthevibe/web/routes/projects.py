"""Project CRUD API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl

from breakthevibe.config.settings import get_settings
from breakthevibe.utils.sanitize import is_safe_url
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import project_repo

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    rules_yaml: str = ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    url: str
    rules_yaml: str = ""
    created_at: str
    last_run_at: str | None = None
    status: str = "created"


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: CreateProjectRequest,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.allow_private_urls and not is_safe_url(str(body.url)):
        raise HTTPException(
            status_code=422,
            detail="URL targets a private or reserved IP address",
        )
    project = await project_repo.create(
        name=body.name,
        url=str(body.url),
        rules_yaml=body.rules_yaml,
        org_id=tenant.org_id,
    )
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    tenant: TenantContext = Depends(get_tenant),
) -> list[dict[str, Any]]:
    return await project_repo.list_all(org_id=tenant.org_id)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> Response:
    deleted = await project_repo.delete(project_id, org_id=tenant.org_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=204)
