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


@router.get("/projects/{project_id}/suites", response_class=HTMLResponse)
async def test_suites_page(request: Request, project_id: str, category: str = "") -> HTMLResponse:
    """Test suite browser — browse by route/category, edit rules inline (#16)."""
    project = await project_repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)

    result = pipeline_results.get(project_id, {})
    suites = result.get("suites", [])

    # Group suites by route, optionally filtering by category
    suites_by_route: dict[str, list[dict]] = {}
    for s in suites:
        suite_name: str = s.get("name", "unknown")
        # Infer category from suite name suffix (e.g., "home_functional" -> "functional")
        parts = suite_name.rsplit("_", 1)
        suite_category = parts[-1] if len(parts) > 1 else "functional"
        if category and suite_category != category:
            continue
        # Infer route from suite name prefix
        route = "/" + parts[0].replace("_", "/") if len(parts) > 1 else "/" + suite_name
        suite_entry = {
            "name": suite_name,
            "category": suite_category,
            "step_count": len(s.get("step_captures", [])),
            "code": s.get("stdout", "")[:2000],
        }
        suites_by_route.setdefault(route, []).append(suite_entry)

    return templates.TemplateResponse(
        "test_suites.html",
        {
            "request": request,
            "project": project,
            "suites_by_route": suites_by_route,
            "category": category,
            "rules_yaml": project.get("rules_yaml", ""),
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def test_result_detail_page(request: Request, run_id: str) -> HTMLResponse:
    # Find the result matching this run_id
    result: dict = {}
    for _pid, res in pipeline_results.items():
        if res.get("run_id") == run_id:
            result = res
            break

    # Extract template variables from report data
    suites = result.get("suites", [])
    status = result.get("status", "passed" if result.get("success") else "failed")
    total = result.get("total", len(suites))
    passed = result.get("passed", sum(1 for s in suites if s.get("success")))
    failed = result.get("failed", sum(1 for s in suites if not s.get("success")))
    duration = f"{result.get('duration_seconds', 0):.1f}s"
    heal_warnings = result.get("heal_warnings", [])

    # Build step replay data for JS
    import json

    replay_steps = []
    for suite in suites:
        for step in suite.get("step_captures", []):
            replay_steps.append(
                {
                    "name": step.get("name", ""),
                    "screenshot": step.get("screenshot_path", ""),
                    "network_requests": step.get("network_calls", []),
                    "console": step.get("console_logs", []),
                }
            )

    return templates.TemplateResponse(
        "test_result_detail.html",
        {
            "request": request,
            "run_id": run_id,
            "result": result,
            "status": status,
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration": duration,
            "suites": suites,
            "heal_warnings": heal_warnings,
            "diffs": [],
            "video_url": None,
            "replay_steps_json": json.dumps(replay_steps),
        },
    )
