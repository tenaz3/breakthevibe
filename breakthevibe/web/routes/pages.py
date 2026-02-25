"""Server-rendered HTML page routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from breakthevibe.web.dependencies import project_repo

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def projects_page(request: Request) -> HTMLResponse:
    projects = await project_repo.list_all()
    return templates.TemplateResponse(
        "projects.html", {"request": request, "projects": projects}
    )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(request: Request, project_id: str) -> HTMLResponse:
    project = await project_repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse(
        "project_detail.html", {"request": request, "project": project}
    )


@router.get("/projects/{project_id}/sitemap", response_class=HTMLResponse)
async def sitemap_page(request: Request, project_id: str) -> HTMLResponse:
    project = await project_repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse(
        "sitemap.html", {"request": request, "project": project}
    )
