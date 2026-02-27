"""Server-rendered HTML page routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import project_repo, test_run_repo

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def projects_page(
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    projects = await project_repo.list_all(org_id=tenant.org_id)
    return templates.TemplateResponse(request, "projects.html", {"projects": projects})


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse(request, "project_detail.html", {"project": project})


@router.get("/projects/{project_id}/sitemap", response_class=HTMLResponse)
async def sitemap_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse(request, "sitemap.html", {"project": project})


@router.get("/projects/{project_id}/runs", response_class=HTMLResponse)
async def test_runs_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        pid = 0
    runs = await test_run_repo.list_for_project(pid, org_id=tenant.org_id)
    return templates.TemplateResponse(request, "test_runs.html", {"project": project, "runs": runs})


@router.get("/projects/{project_id}/suites", response_class=HTMLResponse)
async def test_suites_page(
    request: Request,
    project_id: str,
    category: str = "",
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    """Test suite browser — browse by route/category, edit rules inline (#16)."""
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)

    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        pid = 0
    result = await test_run_repo.get_latest_for_project(pid, org_id=tenant.org_id)
    suites: list[dict[str, Any]] = result.get("suites", []) if result else []

    # Group suites by route, optionally filtering by category
    suites_by_route: dict[str, list[dict[str, Any]]] = {}
    for s in suites:
        suite_name: str = s.get("name", "unknown")
        parts = suite_name.rsplit("_", 1)
        suite_category = parts[-1] if len(parts) > 1 else "functional"
        if category and suite_category != category:
            continue
        route = "/" + parts[0].replace("_", "/") if len(parts) > 1 else "/" + suite_name
        suite_entry = {
            "name": suite_name,
            "category": suite_category,
            "step_count": len(s.get("step_captures", [])),
            "code": s.get("stdout", "")[:2000],
        }
        suites_by_route.setdefault(route, []).append(suite_entry)

    return templates.TemplateResponse(
        request,
        "test_suites.html",
        {
            "project": project,
            "suites_by_route": suites_by_route,
            "category": category,
            "rules_yaml": project.get("rules_yaml", ""),
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def test_result_detail_page(
    request: Request,
    run_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    result: dict[str, Any] = await test_run_repo.get_by_run_uuid(run_id, org_id=tenant.org_id) or {}

    suites = result.get("suites", [])
    status = result.get("status", "passed" if result.get("success") else "failed")
    total = result.get("total", len(suites))
    passed = result.get("passed", sum(1 for s in suites if s.get("success")))
    failed = result.get("failed", sum(1 for s in suites if not s.get("success")))
    duration = f"{result.get('duration_seconds', 0):.1f}s"
    heal_warnings = result.get("heal_warnings", [])

    replay_steps = []
    for suite in suites:
        for step in suite.get("step_captures", []):
            replay_steps.append(
                {
                    "name": step.get("name", ""),
                    "screenshot_url": step.get("screenshot_path", ""),
                    "network_requests": step.get("network_calls", []),
                    "console_logs": step.get("console_logs", []),
                }
            )

    diffs = result.get("diffs", [])

    video_url = result.get("video_url")
    if not video_url:
        for suite in suites:
            for step in suite.get("step_captures", []):
                if step.get("video_path"):
                    video_url = step["video_path"]
                    break
            if video_url:
                break

    return templates.TemplateResponse(
        request,
        "test_result_detail.html",
        {
            "run_id": run_id,
            "result": result,
            "status": status,
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration": duration,
            "suites": suites,
            "heal_warnings": heal_warnings,
            "diffs": diffs,
            "video_url": video_url,
            "replay_steps_json": json.dumps(replay_steps),
        },
    )
