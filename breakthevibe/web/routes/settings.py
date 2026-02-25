"""Settings API routes for rules and LLM configuration."""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.web.dependencies import llm_settings_repo, project_repo

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


class ValidateRulesRequest(BaseModel):
    yaml: str


@router.get("/projects/{project_id}/rules", response_class=HTMLResponse)
async def rules_editor_page(request: Request, project_id: str) -> HTMLResponse:
    project = await project_repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse(
        "rules_editor.html",
        {
            "request": request,
            "project": project,
            "rules_yaml": project.get("rules_yaml", ""),
        },
    )


@router.put("/api/projects/{project_id}/rules")
async def update_rules(project_id: str, request: Request) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    rules_yaml = form.get("rules_yaml", "")
    try:
        RulesConfig.from_yaml(str(rules_yaml))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}") from e
    await project_repo.update(project_id, rules_yaml=str(rules_yaml))
    return {"status": "saved"}


@router.post("/api/rules/validate")
async def validate_rules(body: ValidateRulesRequest) -> dict:
    try:
        RulesConfig.from_yaml(body.yaml)
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.get("/settings/llm", response_class=HTMLResponse)
async def llm_settings_page(request: Request) -> HTMLResponse:
    settings = await llm_settings_repo.get_all()
    return templates.TemplateResponse(
        "llm_settings.html", {"request": request, "settings": settings}
    )


@router.put("/api/settings/llm")
async def update_llm_settings(request: Request) -> dict:
    form = await request.form()
    updates: dict[str, str] = {}
    if form.get("default_provider"):
        updates["default_provider"] = str(form["default_provider"])
    if form.get("default_model"):
        updates["default_model"] = str(form["default_model"])

    # Per-module settings are stored as nested dicts
    current = await llm_settings_repo.get_all()
    modules = current.get("modules", {})
    for module in ["mapper", "generator", "agent"]:
        provider = form.get(f"modules_{module}_provider")
        model = form.get(f"modules_{module}_model")
        if provider:
            modules.setdefault(module, {})["provider"] = str(provider)
        if model:
            modules.setdefault(module, {})["model"] = str(model)
    updates["modules"] = modules  # type: ignore[assignment]

    await llm_settings_repo.set_many(updates)
    logger.info("llm_settings_updated")
    return {"status": "saved"}
