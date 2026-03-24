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


@router.post("/api/projects/{project_id}/generate-rules")
async def generate_rules_from_sitemap(
    project_id: str,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> dict[str, Any]:
    """Use LLM to generate optimized rules YAML from the project's sitemap."""
    from breakthevibe.web.dependencies import crawl_run_repo

    project = await project_repo.get(project_id, org_id=tenant.org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sitemap = await crawl_run_repo.get_latest_sitemap(int(project_id), org_id=tenant.org_id)
    if not sitemap:
        raise HTTPException(
            status_code=400,
            detail="No sitemap found. Crawl the site first.",
        )

    # Resolve LLM provider
    from breakthevibe.web.pipeline import _create_llm_for_rules

    llm = await _create_llm_for_rules(org_id=tenant.org_id)
    if not llm:
        raise HTTPException(
            status_code=400,
            detail="No LLM provider configured. Set an API key in Settings.",
        )

    pages = sitemap.get("pages", [])
    api_endpoints = sitemap.get("api_endpoints", [])

    # Build a compact summary of the sitemap for the prompt
    page_paths = [p.get("url", p.get("path", "")) for p in pages[:50]]
    endpoint_summary = [f"{e.get('method', 'GET')} {e.get('path', '')}" for e in api_endpoints[:30]]

    prompt = f"""Analyze this website's sitemap and generate an optimized \
BreakTheVibe rules YAML configuration.

Site URL: {project.get("url", "")}

Discovered Pages ({len(pages)} total):
{chr(10).join("- " + p for p in page_paths)}

API Endpoints ({len(api_endpoints)} total):
{chr(10).join("- " + e for e in endpoint_summary) if endpoint_summary else "- None discovered"}

Generate a YAML rules configuration that:
1. Sets appropriate crawl depth based on site structure
2. Skips admin, internal, and non-essential URLs (analytics, tracking)
3. Provides realistic form input values based on the site's purpose
4. Configures interaction handling (cookie banners, modals)
5. Sets smart execution modes (sequential for auth flows, parallel for independent pages)
6. Skips visual tests on dynamic/personalized pages
7. Ignores analytics/tracking API endpoints

Return ONLY valid YAML, no markdown fences, no explanation. Use this exact structure:

crawl:
  max_depth: <number>
  skip_urls: [<patterns>]
  scroll_behavior: <incremental|none>
  wait_times:
    page_load: <ms>
    after_click: <ms>
  viewport:
    width: <number>
    height: <number>

inputs:
  <field>: "<value>"

interactions:
  cookie_banner: <dismiss|close_on_appear>
  modals: <close_on_appear|dismiss>

tests:
  skip_visual: [<patterns>]

api:
  ignore_endpoints: [<patterns>]
  expected_overrides:
    "<METHOD> <path>": {{ status: <code> }}

execution:
  mode: <smart|parallel|sequential>
  max_retries: <number>
  suites:
    <name>:
      mode: <sequential|parallel>
      workers: <number>
"""

    try:
        logger.info(
            "rules_generation_started",
            project_id=project_id,
            page_count=len(pages),
            endpoint_count=len(api_endpoints),
        )
        response = await llm.generate(prompt)
        logger.debug(
            "rules_llm_response",
            model=response.model,
            tokens_used=response.tokens_used,
            content_length=len(response.content),
        )
        rules_yaml = response.content.strip()
        # Remove markdown fences if present
        if rules_yaml.startswith("```"):
            lines = rules_yaml.split("\n")
            rules_yaml = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        # Validate the generated YAML
        RulesConfig.from_yaml(rules_yaml)
        logger.info("rules_generation_succeeded", project_id=project_id)
        return {"status": "ok", "rules_yaml": rules_yaml}
    except (yaml.YAMLError, ValueError, ValidationError) as e:
        logger.warning(
            "generated_rules_invalid",
            error=str(e),
            raw_content=response.content[:500] if response else "",
        )
        return {"status": "error", "error": f"Generated rules were invalid: {e}"}
    except Exception as e:
        logger.error("rules_generation_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/settings/llm", response_class=HTMLResponse)
async def llm_settings_page(
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
) -> HTMLResponse:
    settings = await llm_settings_repo.get_all(org_id=tenant.org_id)
    from breakthevibe.config.settings import get_settings

    app_settings = get_settings()

    # Build a dict of which providers have keys configured (DB or env)
    key_status = {
        "anthropic": bool(settings.get("anthropic_api_key") or app_settings.anthropic_api_key),
        "openai": bool(settings.get("openai_api_key") or app_settings.openai_api_key),
        "gemini": bool(settings.get("google_api_key") or app_settings.google_api_key),
        "ollama": True,  # Ollama is always "available" (local)
    }
    return templates.TemplateResponse(
        request, "llm_settings.html", {"settings": settings, "key_status": key_status}
    )


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
