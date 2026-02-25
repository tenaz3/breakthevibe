"""Project CRUD API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from breakthevibe.web.dependencies import project_repo

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
async def create_project(body: CreateProjectRequest) -> dict:
    project = await project_repo.create(
        name=body.name,
        url=str(body.url),
        rules_yaml=body.rules_yaml,
    )
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects() -> list:
    return await project_repo.list_all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    deleted = await project_repo.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
