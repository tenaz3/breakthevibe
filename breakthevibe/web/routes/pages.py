"""Server-rendered HTML page routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from breakthevibe.web.dependencies import pipeline_results, project_repo

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def projects_page(request: Request) -> HTMLResponse:
    projects = await project_repo.list_all()
    return templates.TemplateResponse("projects.html", {"request": request, "projects": projects})


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
    return templates.TemplateResponse("sitemap.html", {"request": request, "project": project})


@router.get("/projects/{project_id}/runs", response_class=HTMLResponse)
async def test_runs_page(request: Request, project_id: str) -> HTMLResponse:
    project = await project_repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    result = pipeline_results.get(project_id, {})
    return templates.TemplateResponse(
        "test_runs.html", {"request": request, "project": project, "result": result}
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def test_result_detail_page(request: Request, run_id: str) -> HTMLResponse:
    # Find the result matching this run_id
    result = {}
    for _pid, res in pipeline_results.items():
        if res.get("run_id") == run_id:
            result = res
            break
    return templates.TemplateResponse(
        "test_result_detail.html", {"request": request, "run_id": run_id, "result": result}
    )
