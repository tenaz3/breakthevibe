"""Role-based access control dependencies for multi-tenant requests."""

from __future__ import annotations

import time

import structlog
from fastapi import Depends, HTTPException, Request
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.config.settings import SENTINEL_ORG_ID, SENTINEL_USER_ID, get_settings
from breakthevibe.web.auth.session import require_auth
from breakthevibe.web.tenant_context import TenantContext, get_single_tenant_context

logger = structlog.get_logger(__name__)

# Short-lived in-process cache for Clerk tenant resolution.
# Reduces DB round-trips from 3 sequential SELECTs to 0 for repeated requests
# within the TTL window (e.g. many API calls in a single page load).
_tenant_cache: dict[tuple[str, str], tuple[TenantContext, float]] = {}
_CACHE_TTL = 30.0  # seconds


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

    if settings.auth_mode == "passkey":
        return _resolve_passkey_tenant(_user)

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


def _resolve_passkey_tenant(user: dict[str, object]) -> TenantContext:
    """Build TenantContext from session data populated during passkey auth."""
    return TenantContext(
        org_id=str(user.get("org_id", SENTINEL_ORG_ID)),
        user_id=str(user.get("user_id", SENTINEL_USER_ID)),
        role=str(user.get("role", "admin")),
        email=str(user.get("email", "")),
    )


async def _resolve_clerk_tenant(request: Request) -> TenantContext:
    """Resolve tenant from Clerk JWT Bearer token.

    Combines the previous 3 sequential SELECT queries (user, org, membership)
    into a single JOIN query and caches the result for _CACHE_TTL seconds to
    reduce database round-trips on hot paths.
    """
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
        # Broad catch: Clerk JWT verification raises PyJWT errors, httpx errors, and
        # library-specific exceptions depending on the failure mode.
        logger.warning("clerk_token_invalid", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if not claims.org_id:
        raise HTTPException(status_code=400, detail="No organization context in token")

    # Check short-lived cache before hitting the database.
    cache_key = (claims.sub, claims.org_id)
    cached = _tenant_cache.get(cache_key)
    if cached and time.monotonic() - cached[1] < _CACHE_TTL:
        return cached[0]

    # Single JOIN query replacing 3 sequential SELECTs.
    async with AsyncSession(get_engine()) as session:
        stmt = (
            select(User, Organization, OrganizationMembership)
            .join(
                OrganizationMembership,
                col(OrganizationMembership.user_id) == col(User.id),
            )
            .join(
                Organization,
                col(Organization.id) == col(OrganizationMembership.org_id),
            )
            .where(
                col(User.clerk_user_id) == claims.sub,
                col(Organization.clerk_org_id) == claims.org_id,
            )
        )
        result = await session.execute(stmt)
        row = result.first()

    if not row:
        # Distinguish between "user not found", "org not found", and "not a member"
        # with a generic 401/403 to avoid information leakage.
        logger.warning(
            "clerk_tenant_not_resolved",
            clerk_user_id=claims.sub,
            clerk_org_id=claims.org_id,
        )
        raise HTTPException(status_code=403, detail="Access denied")

    user, org, membership = row

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    tenant = TenantContext(
        org_id=org.id,
        user_id=user.id,
        role=membership.role,
        email=user.email,
        clerk_org_id=claims.org_id,
        clerk_user_id=claims.sub,
    )
    _tenant_cache[cache_key] = (tenant, time.monotonic())
    return tenant
