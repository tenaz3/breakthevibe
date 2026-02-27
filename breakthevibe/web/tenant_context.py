"""Tenant context for multi-tenant request scoping."""

from __future__ import annotations

from dataclasses import dataclass

from breakthevibe.config.settings import SENTINEL_ORG_ID, SENTINEL_USER_ID


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable tenant context carried through each request."""

    org_id: str
    user_id: str
    role: str  # admin | member | viewer
    email: str
    clerk_org_id: str | None = None
    clerk_user_id: str | None = None


def get_single_tenant_context() -> TenantContext:
    """Return a TenantContext for single-tenant (self-hosted) mode."""
    return TenantContext(
        org_id=SENTINEL_ORG_ID,
        user_id=SENTINEL_USER_ID,
        role="admin",
        email="admin@localhost",
    )
