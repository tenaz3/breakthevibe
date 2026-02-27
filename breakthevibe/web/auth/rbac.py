"""Role-based access control dependencies for multi-tenant requests."""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException, Request
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.config.settings import get_settings
from breakthevibe.web.auth.session import require_auth
from breakthevibe.web.tenant_context import TenantContext, get_single_tenant_context

logger = structlog.get_logger(__name__)


async def get_tenant(
    request: Request,
    _user: dict[str, object] = Depends(require_auth),
) -> TenantContext:
    """Resolve the current tenant context from the request.

    In single-tenant mode, returns the sentinel org/user context.
    In clerk mode, extracts tenant info from the JWT Bearer token.
    """
    settings = get_settings()

    if settings.auth_mode == "single":
        return get_single_tenant_context()

    # Clerk mode — extract JWT from Authorization header
    return await _resolve_clerk_tenant(request)


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


async def _resolve_clerk_tenant(request: Request) -> TenantContext:
    """Resolve tenant from Clerk JWT Bearer token."""
    from breakthevibe.models.database import Organization, OrganizationMembership, User
    from breakthevibe.storage.database import get_engine
    from breakthevibe.web.auth.clerk import verify_clerk_token

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header[7:]
    try:
        claims = await verify_clerk_token(token)
    except Exception as exc:
        logger.warning("clerk_token_invalid", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    # Look up user
    async with AsyncSession(get_engine()) as session:
        user_stmt = select(User).where(col(User.clerk_user_id) == claims.sub)
        user_result = await session.execute(user_stmt)
        user = user_result.scalars().first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        # Resolve org context
        if not claims.org_id:
            raise HTTPException(status_code=400, detail="No organization context in token")

        org_stmt = select(Organization).where(col(Organization.clerk_org_id) == claims.org_id)
        org_result = await session.execute(org_stmt)
        org = org_result.scalars().first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check membership
        mem_stmt = select(OrganizationMembership).where(
            col(OrganizationMembership.org_id) == org.id,
            col(OrganizationMembership.user_id) == user.id,
        )
        mem_result = await session.execute(mem_stmt)
        membership = mem_result.scalars().first()
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this organization")

        return TenantContext(
            org_id=org.id,
            user_id=user.id,
            role=membership.role,
            email=user.email,
            clerk_org_id=claims.org_id,
            clerk_user_id=claims.sub,
        )
