"""Server-rendered HTML page routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from breakthevibe.config.settings import get_settings
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import project_repo, test_run_repo
from breakthevibe.web.template_engine import templates

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def projects_page(
    request: Request,
    page: int = 1,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    per_page = 24
    offset = (max(1, page) - 1) * per_page
    projects = await project_repo.list_all(org_id=tenant.org_id, limit=per_page, offset=offset)
    total = await project_repo.count(org_id=tenant.org_id)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(
        request,
        "projects.html",
        {
            "projects": projects,
            "page": max(1, page),
            "total_pages": total_pages,
            "total": total,
            "base_url": "/",
        },
    )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "status_code": 404,
                "title": "Project Not Found",
                "message": "The project you requested could not be found.",
            },
            status_code=404,
        )
    from breakthevibe.config.settings import get_settings
    from breakthevibe.web.dependencies import llm_settings_repo

    settings = get_settings()

    # Check both env vars and DB-stored keys
    llm_configured = settings.llm_configured
    if not llm_configured:
        try:
            db_settings = await llm_settings_repo.get_all(org_id=tenant.org_id)
            llm_configured = bool(
                db_settings.get("anthropic_api_key")
                or db_settings.get("openai_api_key")
                or db_settings.get("google_api_key")
            )
        except (OSError, ValueError, KeyError):
            pass

    # Check test case cache status
    from breakthevibe.web.dependencies import crawl_run_repo, test_case_repo

    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        pid = 0
    cache_meta = await test_case_repo.get_cache_meta(pid, org_id=tenant.org_id)
    cache_stale = False
    if cache_meta:
        latest_crawl = await crawl_run_repo.get_latest_for_project(pid, org_id=tenant.org_id)
        cache_stale = (
            latest_crawl is not None
            and latest_crawl.get("sitemap_hash") != cache_meta["sitemap_hash"]
        )

    return templates.TemplateResponse(
        request,
        "project_detail.html",
        {
            "project": project,
            "llm_configured": llm_configured,
            "cache_meta": cache_meta,
            "cache_stale": cache_stale,
        },
    )


@router.get("/projects/{project_id}/sitemap", response_class=HTMLResponse)
async def sitemap_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "status_code": 404,
                "title": "Project Not Found",
                "message": "The project you requested could not be found.",
            },
            status_code=404,
        )
    return templates.TemplateResponse(request, "sitemap.html", {"project": project})


@router.get("/projects/{project_id}/runs", response_class=HTMLResponse)
async def test_runs_page(
    request: Request,
    project_id: int,
    page: int = 1,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(str(project_id), org_id=tenant.org_id)
    if not project:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "status_code": 404,
                "title": "Project Not Found",
                "message": "The project you requested could not be found.",
            },
            status_code=404,
        )
    per_page = 24
    offset = (max(1, page) - 1) * per_page
    runs = await test_run_repo.list_for_project(
        project_id, org_id=tenant.org_id, limit=per_page, offset=offset
    )
    total = await test_run_repo.count_for_project(project_id, org_id=tenant.org_id)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(
        request,
        "test_runs.html",
        {
            "project": project,
            "runs": runs,
            "page": max(1, page),
            "total_pages": total_pages,
            "total": total,
            "base_url": f"/projects/{project_id}/runs",
        },
    )


@router.get("/projects/{project_id}/suites", response_class=HTMLResponse)
async def test_suites_page(
    request: Request,
    project_id: int,
    category: str = "",
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    """Test suite browser — browse by route/category, edit rules inline (#16)."""
    project = await project_repo.get(str(project_id), org_id=tenant.org_id)
    if not project:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "status_code": 404,
                "title": "Project Not Found",
                "message": "The project you requested could not be found.",
            },
            status_code=404,
        )

    result = await test_run_repo.get_latest_for_project(project_id, org_id=tenant.org_id)
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

    # Convert absolute screenshot paths to served URLs
    settings = get_settings()
    artifacts_base = str(Path(settings.artifacts_dir).expanduser().resolve())

    def _to_served_url(abs_path: str, pid: str) -> str:
        """Convert /home/.breakthevibe/projects/1/foo.png -> /artifacts/1/foo.png."""
        if not abs_path:
            return ""
        project_prefix = f"{artifacts_base}/{pid}/"
        if abs_path.startswith(project_prefix):
            return f"/artifacts/{pid}/{abs_path[len(project_prefix) :]}"
        return ""

    pid = str(result.get("project_id", ""))
    replay_steps = []
    for suite in suites:
        for step in suite.get("step_captures", []):
            replay_steps.append(
                {
                    "name": step.get("name", ""),
                    "screenshot_url": _to_served_url(step.get("screenshot_path", ""), pid),
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

    project_id = result.get("project_id", "")

    return templates.TemplateResponse(
        request,
        "test_result_detail.html",
        {
            "run_id": run_id,
            "project_id": project_id,
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
