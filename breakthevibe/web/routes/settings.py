"""Settings API routes for rules and LLM configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from breakthevibe.audit.logger import audit
from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.utils.crypto import encrypt_value
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.dependencies import llm_settings_repo, project_repo
from breakthevibe.web.template_engine import templates

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])


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
    if len(str(rules_yaml)) > 65536:
        raise HTTPException(status_code=413, detail="Rules YAML too large")
    try:
        RulesConfig.from_yaml(str(rules_yaml))
    except (yaml.YAMLError, ValueError, ValidationError) as e:
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
    except (yaml.YAMLError, ValueError, ValidationError) as e:
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

    # Save API keys (#13) — encrypt sensitive values before persisting
    _sensitive_keys = ("api_key", "secret")
    for field in ("anthropic_api_key", "openai_api_key", "google_api_key"):
        raw = form.get(field)
        if raw:
            value = str(raw)
            if any(k in field for k in _sensitive_keys):
                value = encrypt_value(value)
            updates[field] = value
    if form.get("ollama_base_url"):
        updates["ollama_base_url"] = str(form["ollama_base_url"])

    # Per-module settings are stored as nested dicts.
    # Always save the value (even empty string) so "Use default" clears overrides.
    current = await llm_settings_repo.get_all(org_id=tenant.org_id)
    modules = current.get("modules", {})
    for module in ["mapper", "generator", "agent"]:
        provider = form.get(f"modules_{module}_provider")
        model = form.get(f"modules_{module}_model")
        modules.setdefault(module, {})["provider"] = str(provider) if provider else ""
        modules.setdefault(module, {})["model"] = str(model) if model else ""
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
