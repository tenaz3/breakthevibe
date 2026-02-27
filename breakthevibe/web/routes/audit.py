"""Audit log query API routes (admin-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from breakthevibe.web.auth.rbac import get_tenant, require_admin

if TYPE_CHECKING:
    from breakthevibe.web.tenant_context import TenantContext

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", dependencies=[Depends(require_admin)])
async def list_audit_logs(
    tenant: TenantContext = Depends(get_tenant),
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Query audit logs for the current org. Requires admin role."""
    from breakthevibe.storage.database import get_engine

    engine = get_engine()

    clauses = ["org_id = :org_id"]
    params: dict[str, Any] = {"org_id": tenant.org_id, "limit": limit, "offset": offset}

    if action:
        clauses.append("action = :action")
        params["action"] = action
    if resource_type:
        clauses.append("resource_type = :resource_type")
        params["resource_type"] = resource_type

    where = " AND ".join(clauses)

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"SELECT id, org_id, user_id, action, resource_type, resource_id, "  # noqa: S608
                f"details_json, ip_address, request_id, created_at "
                f"FROM audit_logs WHERE {where} "
                f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]
