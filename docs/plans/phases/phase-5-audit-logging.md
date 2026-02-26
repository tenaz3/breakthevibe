# Phase 5: Audit Logging & Compliance

> **Status**: Not started
> **Depends on**: Phase 1 + Phase 2 (needs TenantContext and user identity)
> **Estimated scope**: ~4 files created, ~8 modified
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Record all significant actions for SOC 2 compliance and GDPR accountability. Every auth event, CRUD operation, pipeline execution, and settings change gets an audit log entry. Provide an admin-only query API for audit trail review.

---

## 2. AuditLog Model

**Add to: `breakthevibe/models/database.py`**

```python
class AuditLog(SQLModel, table=True):
    """Immutable audit trail for SOC 2 compliance."""

    __tablename__ = "audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str | None = Field(default=None, foreign_key="users.id")
    action: str = Field(index=True)
    resource_type: str
    resource_id: str | None = None
    details_json: str | None = None
    ip_address: str | None = None
    request_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
```

**Index strategy**: `(org_id, created_at DESC)` for efficient tenant-scoped queries. The `action` index supports filtering by event type.

---

## 3. Audit Logger Service

**Create: `breakthevibe/audit/__init__.py`** (empty)

**Create: `breakthevibe/audit/logger.py`**

```python
"""Audit logger — records events to the audit_logs table."""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from breakthevibe.models.database import AuditLog
from breakthevibe.storage.database import get_engine

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Records audit events. Uses its own session to ensure
    audit entries are written even if the request transaction rolls back."""

    async def log(
        self,
        org_id: str,
        user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Write an audit log entry."""
        try:
            async with AsyncSession(get_engine()) as session:
                entry = AuditLog(
                    org_id=org_id,
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details_json=json.dumps(details) if details else None,
                    ip_address=ip_address,
                    request_id=request_id,
                )
                session.add(entry)
                await session.commit()

            logger.debug(
                "audit_logged",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                org_id=org_id,
            )
        except Exception as e:
            # Audit logging must never break the request
            logger.error("audit_log_failed", action=action, error=str(e))


# Singleton — audit logger doesn't hold request state
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger  # noqa: PLW0603
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
```

**Helper for route handlers:**

```python
async def audit(
    tenant: TenantContext,
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Convenience function for audit logging from route handlers."""
    from structlog.contextvars import get_contextvars
    ctx = get_contextvars()
    await get_audit_logger().log(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=request.client.host if request.client else None,
        request_id=ctx.get("request_id"),
    )
```

---

## 4. Events to Audit

| Action | Resource Type | Route/Location | Details |
|---|---|---|---|
| `auth.login` | session | `POST /api/auth/login` | `{"username": "..."}` |
| `auth.logout` | session | `POST /api/auth/logout` | — |
| `auth.login_failed` | session | `POST /api/auth/login` | `{"username": "...", "reason": "..."}` |
| `project.created` | project | `POST /api/projects` | `{"name": "...", "url": "..."}` |
| `project.deleted` | project | `DELETE /api/projects/{id}` | — |
| `project.updated` | project | (future) | `{"fields": [...]}` |
| `pipeline.started` | pipeline | `POST .../crawl\|generate\|run` | `{"url": "..."}` |
| `pipeline.completed` | pipeline | `run_pipeline()` | `{"success": true, "duration": ...}` |
| `pipeline.failed` | pipeline | `run_pipeline()` | `{"error": "..."}` |
| `settings.llm_updated` | settings | `PUT /api/settings/llm` | `{"provider": "..."}` |
| `rules.updated` | rules | `PUT /api/projects/{id}/rules` | — |
| `member.joined` | membership | Clerk webhook | `{"role": "..."}` |
| `member.removed` | membership | Clerk webhook | — |
| `member.role_changed` | membership | Clerk webhook | `{"old": "...", "new": "..."}` |
| `data.purge_requested` | gdpr | Admin API (future) | — |
| `data.purge_completed` | gdpr | Purge workflow (future) | `{"tables_purged": 14}` |

---

## 5. Route Integration Examples

### projects.py

```python
@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: CreateProjectRequest,
    request: Request,
    tenant: TenantContext = Depends(require_member),
    project_repo: Any = Depends(get_project_repo),
) -> dict:
    if not is_safe_url(str(body.url)):
        raise HTTPException(...)
    project = await project_repo.create(...)

    # Audit log
    await audit(tenant, request, "project.created", "project",
                resource_id=project["id"],
                details={"name": body.name, "url": str(body.url)})

    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    request: Request,
    tenant: TenantContext = Depends(require_member),
    project_repo: Any = Depends(get_project_repo),
) -> None:
    deleted = await project_repo.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    await audit(tenant, request, "project.deleted", "project",
                resource_id=project_id)
```

### auth.py

```python
@router.post("/api/auth/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    # ... existing validation ...

    # Audit — use sentinel org/user for single-tenant
    from breakthevibe.config.settings import get_settings
    settings = get_settings()
    await get_audit_logger().log(
        org_id=settings.single_tenant_org_id,
        user_id=None,
        action="auth.login",
        resource_type="session",
        details={"username": body.username},
        ip_address=request.client.host if request.client else None,
    )
    return {"status": "ok", "username": body.username}
```

---

## 6. Audit Query API

**Create: `breakthevibe/web/routes/audit.py`**

```python
"""Audit log query API — admin only."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlmodel import select

from breakthevibe.models.database import AuditLog
from breakthevibe.web.auth.rbac import require_admin
from breakthevibe.web.dependencies import get_scoped_session
from breakthevibe.web.tenant_context import TenantContext
from breakthevibe.storage.tenant_session import TenantScopedSession

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    tenant: TenantContext = Depends(require_admin),
    session: TenantScopedSession = Depends(get_scoped_session),
    action: str | None = Query(None, description="Filter by action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List audit logs for this organization. Admin only."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.org_id == tenant.org_id)
        .order_by(AuditLog.created_at.desc())
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    stmt = stmt.offset((page - 1) * limit).limit(limit)
    results = (await session.execute(stmt)).scalars().all()

    return {
        "page": page,
        "limit": limit,
        "entries": [
            {
                "id": log.id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "user_id": log.user_id,
                "ip_address": log.ip_address,
                "details": log.details_json,
                "created_at": log.created_at.isoformat(),
            }
            for log in results
        ],
    }
```

**Register in `app.py`**:

```python
from breakthevibe.web.routes.audit import router as audit_router
# Add to protected routers list
```

---

## 7. Alembic Migration

```python
"""add audit_logs table"""

def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index(
        "ix_audit_logs_org_created",
        "audit_logs",
        ["org_id", sa.text("created_at DESC")],
    )
```

---

## 8. SOC 2 Compliance Notes

- **Immutability**: Audit logs are INSERT-only. No UPDATE or DELETE operations exposed.
- **Retention**: Logs stored indefinitely by default. Add a retention policy job (e.g., archive after 1 year) as a future enhancement.
- **Completeness**: Every route handler, webhook handler, and pipeline event logs an audit entry.
- **Integrity**: Audit logger uses its own session — writes succeed even if the request transaction rolls back.
- **Access control**: Only org admins can query audit logs via the API.

---

## 9. Verification Checklist

- [ ] Creating a project produces an audit log entry
- [ ] Deleting a project produces an audit log entry
- [ ] Login produces an audit log entry
- [ ] Pipeline start/complete/fail produce audit entries
- [ ] LLM settings update produces an audit entry
- [ ] Clerk webhook events produce audit entries
- [ ] `GET /api/audit-logs` returns entries for the current org only
- [ ] `GET /api/audit-logs` requires admin role (403 for member/viewer)
- [ ] Audit entries include request_id for correlation
- [ ] Audit logging failure does not break the request

---

## 10. Files Summary

| Action | File |
|---|---|
| CREATE | `breakthevibe/audit/__init__.py` |
| CREATE | `breakthevibe/audit/logger.py` (~80 lines) |
| CREATE | `breakthevibe/web/routes/audit.py` (~60 lines) |
| CREATE | migration: `add_audit_logs_table.py` |
| MODIFY | `breakthevibe/models/database.py` (AuditLog model) |
| MODIFY | `breakthevibe/web/app.py` (register audit router) |
| MODIFY | `breakthevibe/web/routes/projects.py` (audit calls) |
| MODIFY | `breakthevibe/web/routes/crawl.py` (audit calls) |
| MODIFY | `breakthevibe/web/routes/tests.py` (audit calls) |
| MODIFY | `breakthevibe/web/routes/settings.py` (audit calls) |
| MODIFY | `breakthevibe/web/routes/auth.py` (audit calls) |
| MODIFY | `breakthevibe/web/auth/webhook.py` (audit calls) |
| MODIFY | `breakthevibe/web/dependencies.py` (audit pipeline events) |
| MODIFY | `breakthevibe/storage/migrations/env.py` (import AuditLog) |
