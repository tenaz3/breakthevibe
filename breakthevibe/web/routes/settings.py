"""Settings API routes for rules and LLM configuration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from breakthevibe.audit.logger import audit
from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import llm_settings_repo, project_repo

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


class ValidateRulesRequest(BaseModel):
    yaml: str


@router.get("/projects/{project_id}/rules", response_class=HTMLResponse)
async def rules_editor_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "rules_editor.html",
        {
            "project": project,
            "rules_yaml": project.get("rules_yaml", ""),
        },
    )


@router.put("/api/projects/{project_id}/rules")
async def update_rules(
    project_id: str,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    rules_yaml = form.get("rules_yaml", "")
    try:
        RulesConfig.from_yaml(str(rules_yaml))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}") from e
    await project_repo.update(project_id, org_id=tenant.org_id, rules_yaml=str(rules_yaml))
    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="settings.updated",
        resource_type="project_rules",
        resource_id=project_id,
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    return {"status": "saved"}


@router.post("/api/rules/validate")
async def validate_rules(body: ValidateRulesRequest) -> dict[str, str | bool]:
    try:
        RulesConfig.from_yaml(body.yaml)
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.get("/settings/llm", response_class=HTMLResponse)
async def llm_settings_page(
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    settings = await llm_settings_repo.get_all(org_id=tenant.org_id)
    return templates.TemplateResponse(request, "llm_settings.html", {"settings": settings})


@router.put("/api/settings/llm")
async def update_llm_settings(
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, str]:
    form = await request.form()
    updates: dict[str, Any] = {}
    if form.get("default_provider"):
        updates["default_provider"] = str(form["default_provider"])
    if form.get("default_model"):
        updates["default_model"] = str(form["default_model"])

    # Save API keys (#13)
    if form.get("anthropic_api_key"):
        updates["anthropic_api_key"] = str(form["anthropic_api_key"])
    if form.get("openai_api_key"):
        updates["openai_api_key"] = str(form["openai_api_key"])
    if form.get("ollama_base_url"):
        updates["ollama_base_url"] = str(form["ollama_base_url"])

    # Per-module settings are stored as nested dicts
    current = await llm_settings_repo.get_all(org_id=tenant.org_id)
    modules = current.get("modules", {})
    for module in ["mapper", "generator", "agent"]:
        provider = form.get(f"modules_{module}_provider")
        model = form.get(f"modules_{module}_model")
        if provider:
            modules.setdefault(module, {})["provider"] = str(provider)
        if model:
            modules.setdefault(module, {})["model"] = str(model)
    updates["modules"] = modules

    await llm_settings_repo.set_many(updates, org_id=tenant.org_id)
    await audit(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action="settings.updated",
        resource_type="llm_settings",
        details={"keys_changed": list(updates.keys())},
        ip_address=request.client.host if request.client else "",
        request_id=request.headers.get("x-request-id", ""),
    )
    logger.info("llm_settings_updated", org_id=tenant.org_id)
    return {"status": "saved"}
