"""Role-based access control dependencies for multi-tenant requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request

from breakthevibe.config.settings import get_settings
from breakthevibe.web.auth.session import require_auth
from breakthevibe.web.tenant_context import get_single_tenant_context

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext


async def get_tenant(
    request: Request,
    _user: dict[str, object] = Depends(require_auth),
) -> TenantContext:
    """Resolve the current tenant context from the request.

    In single-tenant mode, returns the sentinel org/user context.
    In clerk mode, extracts tenant info from the JWT (implemented in Phase 2).
    """
    settings = get_settings()

    if settings.auth_mode == "single":
        return get_single_tenant_context()

    # Clerk mode — placeholder until Phase 2 implements JWT extraction
    raise HTTPException(  # pragma: no cover
        status_code=501,
        detail="Clerk authentication not yet implemented",
    )


async def require_viewer(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Require at least viewer role."""
    return tenant


async def require_member(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Require at least member role (blocks viewers)."""
    if tenant.role == "viewer":
        raise HTTPException(status_code=403, detail="Member access required")
    return tenant


async def require_admin(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Require admin role."""
    if tenant.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return tenant
