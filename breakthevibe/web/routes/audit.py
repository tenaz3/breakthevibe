"""Audit log query API routes (admin-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.models.database import AuditLog
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

    stmt = (
        select(AuditLog)
        .where(col(AuditLog.org_id) == tenant.org_id)
        .order_by(col(AuditLog.created_at).desc())
        .limit(limit)
        .offset(offset)
    )
    if action:
        stmt = stmt.where(col(AuditLog.action) == action)
    if resource_type:
        stmt = stmt.where(col(AuditLog.resource_type) == resource_type)

    async with AsyncSession(engine) as session:
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "org_id": r.org_id,
                "user_id": r.user_id,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "details_json": r.details_json,
                "ip_address": r.ip_address,
                "request_id": r.request_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
