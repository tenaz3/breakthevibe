# Phase 1: Multi-Tenancy Foundation

> **Status**: Not started
> **Depends on**: Nothing (first phase)
> **Estimated scope**: ~18 files modified/created
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Add organization, user, and membership models to the database. Add `org_id` to all 7 existing data tables. Refactor the repository layer to enforce tenant-scoped queries on every operation. Introduce a `TenantContext` dataclass and RBAC dependencies. Maintain full backward compatibility with `AUTH_MODE=single`.

---

## 2. Prerequisites

- PostgreSQL running locally or via Docker
- Existing migration `2fbda022df84` applied
- All current tests passing

---

## 3. Detailed Implementation

### 3.1 TenantContext Dataclass

**Create: `breakthevibe/web/tenant_context.py`**

```python
"""TenantContext: the resolved identity for every authenticated request."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Resolved per-request identity after successful authentication.

    org_id is our internal UUID (from organizations table).
    clerk_org_id is Clerk's identifier, kept for logging/debugging.
    role is one of: admin | member | viewer
    """

    org_id: str
    clerk_org_id: str
    user_id: str
    clerk_user_id: str
    role: str
    email: str

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_at_least_member(self) -> bool:
        return self.role in ("admin", "member")

    def is_viewer(self) -> bool:
        return self.role == "viewer"
```

### 3.2 TenantScopedSession Wrapper

**Create: `breakthevibe/storage/tenant_session.py`**

```python
"""TenantScopedSession: wraps AsyncSession to enforce org_id on all writes."""

from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession


class TenantScopedSession:
    """Thin wrapper around AsyncSession that carries the org_id for the current request.

    Repositories receive this instead of a raw AsyncSession so that org_id
    is always available without being threaded through every method signature.
    """

    def __init__(self, session: AsyncSession | None, org_id: str) -> None:
        self._session = session
        self.org_id = org_id

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("No database session available (in-memory mode)")
        return self._session

    async def execute(self, statement: Any, **kwargs: Any) -> Any:
        return await self.session.execute(statement, **kwargs)

    def add(self, instance: object) -> None:
        self.session.add(instance)

    async def commit(self) -> None:
        await self.session.commit()

    async def refresh(self, instance: object) -> None:
        await self.session.refresh(instance)

    async def delete(self, instance: object) -> None:
        await self.session.delete(instance)

    async def get(self, model: type, pk: object) -> object | None:
        return await self.session.get(model, pk)
```

### 3.3 Settings Additions

**Modify: `breakthevibe/config/settings.py`**

Add these fields to the `Settings` class:

```python
# --- NEW FIELDS ---

# Auth mode: "single" = original HMAC cookie auth (default, backward compat)
#            "clerk"  = Clerk JWT multi-tenant auth
auth_mode: str = "single"

# Single-tenant: the fixed org UUID seeded in migration
single_tenant_org_id: str = "00000000-0000-0000-0000-000000000001"

# Clerk settings (only required when auth_mode = "clerk")
clerk_secret_key: str | None = None
clerk_publishable_key: str | None = None
clerk_webhook_secret: str | None = None
clerk_issuer: str | None = None
clerk_audience: str | None = None
clerk_jwks_url: str | None = None
```

Add validation in `get_settings()`:

```python
if settings.auth_mode == "clerk":
    required = ["clerk_secret_key", "clerk_webhook_secret",
                "clerk_issuer", "clerk_jwks_url"]
    for field_name in required:
        if not getattr(settings, field_name):
            raise RuntimeError(
                f"AUTH_MODE=clerk requires {field_name.upper()} to be set."
            )
```

**Full file after changes:**

```python
"""Application settings via Pydantic BaseSettings."""

import warnings
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    database_url: str = "postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe"
    use_database: bool = False

    # App
    secret_key: str = "change-me-in-production"
    debug: bool = False
    log_level: str = "INFO"
    artifacts_dir: str = "~/.breakthevibe/projects"

    # Auth mode: "single" = original HMAC cookie (backward compat)
    #            "clerk"  = Clerk JWT multi-tenant
    auth_mode: str = "single"

    # Single-tenant mode credentials (existing)
    admin_username: str | None = None
    admin_password: str | None = None

    # Single-tenant sentinel org UUID (seeded in migration)
    single_tenant_org_id: str = "00000000-0000-0000-0000-000000000001"

    # Clerk settings (required when auth_mode = "clerk")
    clerk_secret_key: str | None = None
    clerk_publishable_key: str | None = None
    clerk_webhook_secret: str | None = None
    clerk_issuer: str | None = None
    clerk_audience: str | None = None
    clerk_jwks_url: str | None = None

    # LLM Providers (all optional)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    settings = Settings()
    if settings.secret_key == "change-me-in-production":
        warnings.warn(
            "SECRET_KEY is using the insecure default. "
            "Set SECRET_KEY environment variable for production.",
            UserWarning,
            stacklevel=2,
        )
    if settings.auth_mode == "clerk":
        required_clerk = [
            "clerk_secret_key",
            "clerk_webhook_secret",
            "clerk_issuer",
            "clerk_jwks_url",
        ]
        for field_name in required_clerk:
            if not getattr(settings, field_name):
                raise RuntimeError(
                    f"AUTH_MODE=clerk requires {field_name.upper()} to be set."
                )
    return settings
```

### 3.4 New Database Models

**Modify: `breakthevibe/models/database.py`**

Add imports and helper at top:

```python
"""SQLModel database table models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _new_uuid() -> str:
    return str(uuid.uuid4())
```

Add three new models BEFORE existing models:

```python
# ---------------------------------------------------------------------------
# Multi-tenancy models
# ---------------------------------------------------------------------------


class Organization(SQLModel, table=True):
    """One row per subscribing company."""

    __tablename__ = "organizations"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        sa_column=Column(sa.String(36), primary_key=True),
    )
    clerk_org_id: str = Field(index=True, unique=True)
    name: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    plan: str = Field(default="free")
    is_active: bool = Field(default=True)
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class User(SQLModel, table=True):
    """Mirrors Clerk user records, synced via webhook."""

    __tablename__ = "users"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        sa_column=Column(sa.String(36), primary_key=True),
    )
    clerk_user_id: str = Field(index=True, unique=True)
    email: str = Field(index=True)
    display_name: str | None = None
    avatar_url: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class OrganizationMembership(SQLModel, table=True):
    """Maps users to organizations with a role."""

    __tablename__ = "organization_memberships"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        sa_column=Column(sa.String(36), primary_key=True),
    )
    org_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    clerk_membership_id: str = Field(index=True, unique=True)
    role: str = Field(default="member")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

Add `org_id` to ALL 7 existing models:

```python
class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    name: str = Field(index=True)
    url: str
    config_yaml: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class CrawlRun(SQLModel, table=True):
    __tablename__ = "crawl_runs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    site_map_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class Route(SQLModel, table=True):
    __tablename__ = "routes"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    crawl_run_id: int = Field(foreign_key="crawl_runs.id", index=True)
    url: str
    path: str
    title: str | None = None
    components_json: str | None = None
    interactions_json: str | None = None
    api_calls_json: str | None = None
    screenshot_path: str | None = None
    video_path: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class TestCase(SQLModel, table=True):
    __tablename__ = "test_cases"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    project_id: int = Field(foreign_key="projects.id", index=True)
    name: str
    category: str
    route_path: str
    steps_json: str | None = None
    code: str | None = None
    selectors_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class TestRun(SQLModel, table=True):
    __tablename__ = "test_runs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending")
    execution_mode: str = Field(default="smart")
    total: int = Field(default=0)
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    healed: int = Field(default=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class TestResult(SQLModel, table=True):
    __tablename__ = "test_results"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    test_run_id: int = Field(foreign_key="test_runs.id", index=True)
    test_case_id: int = Field(foreign_key="test_cases.id", index=True)
    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    steps_log_json: str | None = None
    screenshot_paths_json: str | None = None
    video_path: str | None = None
    network_log_json: str | None = None
    console_log_json: str | None = None
    healed_selectors_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class LlmSetting(SQLModel, table=True):
    __tablename__ = "llm_settings"
    __table_args__ = (
        sa.UniqueConstraint("org_id", "key", name="uq_llm_settings_org_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)  # NEW
    key: str = Field(index=True)  # NOTE: no longer unique alone
    value_json: str
    updated_at: datetime = Field(default_factory=_utc_now)
```

### 3.5 Alembic Migration 1: Tenancy Tables

**Create: `breakthevibe/storage/migrations/versions/<auto>_add_tenancy_tables.py`**

```python
"""add tenancy tables

Revision ID: <auto-generated>
Revises: 2fbda022df84
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<auto>"
down_revision: Union[str, Sequence[str], None] = "2fbda022df84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("clerk_org_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_clerk_org_id", "organizations", ["clerk_org_id"], unique=True)
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("clerk_user_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)
    op.create_index("ix_users_email", "users", ["email"])

    # Organization Memberships
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("clerk_membership_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_om_org_id", "organization_memberships", ["org_id"])
    op.create_index("ix_om_user_id", "organization_memberships", ["user_id"])
    op.create_index(
        "ix_om_clerk_membership_id",
        "organization_memberships",
        ["clerk_membership_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("organization_memberships")
    op.drop_table("users")
    op.drop_table("organizations")
```

### 3.6 Alembic Migration 2: Add org_id to Data Tables

**Create: `breakthevibe/storage/migrations/versions/<auto>_add_org_id_to_data_tables.py`**

```python
"""add org_id to all data tables

Revision ID: <auto>
Revises: <migration-1-id>

Strategy:
  1. Seed a sentinel organization for backward compat.
  2. Add org_id as nullable to all 7 tables.
  3. Backfill existing rows with sentinel org_id.
  4. Set NOT NULL + FK constraints.
  5. Update llm_settings unique constraint from (key) to (org_id, key).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<auto>"
down_revision: Union[str, Sequence[str], None] = "<migration-1-id>"
branch_labels = None
depends_on = None

SENTINEL_ORG_ID = "00000000-0000-0000-0000-000000000001"
SENTINEL_CLERK_ORG_ID = "org_single_tenant"

DATA_TABLES = [
    "projects",
    "crawl_runs",
    "routes",
    "test_cases",
    "test_runs",
    "test_results",
    "llm_settings",
]


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Seed sentinel organization
    conn.execute(
        sa.text(
            """
            INSERT INTO organizations
                (id, clerk_org_id, name, slug, plan, is_active, created_at, updated_at)
            VALUES
                (:id, :clerk_org_id, 'Default Organization', 'default',
                 'free', true, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": SENTINEL_ORG_ID, "clerk_org_id": SENTINEL_CLERK_ORG_ID},
    )

    # Step 2: Add org_id as nullable
    for table in DATA_TABLES:
        op.add_column(table, sa.Column("org_id", sa.String(36), nullable=True))

    # Step 3: Backfill existing rows
    for table in DATA_TABLES:
        conn.execute(
            sa.text(f"UPDATE {table} SET org_id = :org_id WHERE org_id IS NULL"),
            {"org_id": SENTINEL_ORG_ID},
        )

    # Step 4: Set NOT NULL + FK + index
    for table in DATA_TABLES:
        op.alter_column(table, "org_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_org_id", table, "organizations", ["org_id"], ["id"]
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])

    # Step 5: Update llm_settings unique constraint
    # Drop old unique index on key alone
    op.drop_index("ix_llm_settings_key", table_name="llm_settings")
    # Re-create as non-unique index
    op.create_index("ix_llm_settings_key", "llm_settings", ["key"])
    # Add composite unique constraint
    op.create_unique_constraint(
        "uq_llm_settings_org_key", "llm_settings", ["org_id", "key"]
    )


def downgrade() -> None:
    # Reverse step 5
    op.drop_constraint("uq_llm_settings_org_key", "llm_settings", type_="unique")
    op.drop_index("ix_llm_settings_key", table_name="llm_settings")
    op.create_index("ix_llm_settings_key", "llm_settings", ["key"], unique=True)

    # Reverse steps 4, 3, 2
    for table in DATA_TABLES:
        op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
```

### 3.7 Update Alembic env.py

**Modify: `breakthevibe/storage/migrations/env.py`**

Add new model imports:

```python
from breakthevibe.models.database import (  # noqa: F401
    CrawlRun,
    LlmSetting,
    Organization,               # NEW
    OrganizationMembership,     # NEW
    Project,
    Route,
    TestCase,
    TestResult,
    TestRun,
    User,                       # NEW
)
```

### 3.8 Single-Tenant Auth Shim

**Create: `breakthevibe/web/auth/single_tenant.py`**

```python
"""Single-tenant auth shim — backward compatibility for AUTH_MODE=single."""

from __future__ import annotations

from fastapi import HTTPException, Request

from breakthevibe.web.auth.session import get_session_auth
from breakthevibe.web.tenant_context import TenantContext


async def require_single_tenant_auth(request: Request) -> TenantContext:
    """FastAPI dependency for single-tenant (legacy) authentication.

    Validates the existing HMAC session cookie and returns a synthetic
    TenantContext with the sentinel org UUID and admin role.
    """
    from breakthevibe.config.settings import get_settings

    settings = get_settings()

    auth = get_session_auth()
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_data = auth.validate_session(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return TenantContext(
        org_id=settings.single_tenant_org_id,
        clerk_org_id="org_single_tenant",
        user_id="00000000-0000-0000-0000-000000000002",
        clerk_user_id="user_single_tenant",
        role="admin",
        email=user_data.get("username", "admin@localhost"),
    )
```

### 3.9 RBAC Dependencies

**Create: `breakthevibe/web/auth/rbac.py`**

```python
"""Role-based access control dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from breakthevibe.web.tenant_context import TenantContext


def _get_auth_dependency():  # type: ignore[no-untyped-def]
    """Return the correct auth dependency based on AUTH_MODE setting."""
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    if settings.auth_mode == "clerk":
        from breakthevibe.web.auth.clerk import require_clerk_auth

        return require_clerk_auth
    from breakthevibe.web.auth.single_tenant import require_single_tenant_auth

    return require_single_tenant_auth


_auth_dep = _get_auth_dependency()


async def get_tenant(
    tenant: TenantContext = Depends(_auth_dep),
) -> TenantContext:
    """Base dependency — resolves TenantContext from whichever auth mode is active."""
    return tenant


async def require_viewer(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Any authenticated user (viewer, member, admin)."""
    return tenant


async def require_member(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Requires member or admin role."""
    if not tenant.is_at_least_member():
        raise HTTPException(status_code=403, detail="Member access required")
    return tenant


async def require_admin(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Requires admin role within the organization."""
    if not tenant.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return tenant
```

### 3.10 In-Memory Tenant-Partitioned Repository

**Create: `breakthevibe/storage/repositories/in_memory_projects.py`**

```python
"""Tenant-scoped in-memory project repository for dev mode."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Global store: org_id -> {project_id -> project_dict}
_STORES: dict[str, dict[str, dict[str, Any]]] = {}


def get_in_memory_store(org_id: str) -> dict[str, dict[str, Any]]:
    """Get or create the per-org in-memory store."""
    if org_id not in _STORES:
        _STORES[org_id] = {}
    return _STORES[org_id]


class InMemoryProjectRepository:
    """Tenant-partitioned in-memory project store."""

    def __init__(self, store: dict[str, dict[str, Any]], org_id: str) -> None:
        self._projects = store
        self._org_id = org_id

    async def create(self, name: str, url: str, rules_yaml: str = "") -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        project = {
            "id": project_id,
            "name": name,
            "url": url,
            "rules_yaml": rules_yaml,
            "created_at": datetime.now(UTC).isoformat(),
            "last_run_at": None,
            "status": "created",
        }
        self._projects[project_id] = project
        logger.info("project_created", id=project_id, name=name, org_id=self._org_id)
        return project

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self._projects.values())

    async def get(self, project_id: str) -> dict[str, Any] | None:
        return self._projects.get(project_id)

    async def delete(self, project_id: str) -> bool:
        if project_id in self._projects:
            del self._projects[project_id]
            logger.info("project_deleted", id=project_id, org_id=self._org_id)
            return True
        return False

    async def update(self, project_id: str, **updates: Any) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if project:
            project.update(updates)
            return project
        return None
```

### 3.11 Refactored DatabaseProjectRepository

**Modify: `breakthevibe/storage/repositories/db_projects.py`**

Full replacement:

```python
"""Database-backed project repository with mandatory tenant scoping."""

from __future__ import annotations

from typing import Any

import structlog
from sqlmodel import select

from breakthevibe.models.database import Project
from breakthevibe.storage.tenant_session import TenantScopedSession

logger = structlog.get_logger(__name__)


class DatabaseProjectRepository:
    """PostgreSQL-backed project store, scoped to a single organization."""

    def __init__(self, scoped_session: TenantScopedSession) -> None:
        self._db = scoped_session

    def _to_dict(self, project: Project) -> dict[str, Any]:
        return {
            "id": str(project.id),
            "name": project.name,
            "url": project.url,
            "rules_yaml": project.config_yaml or "",
            "created_at": project.created_at.isoformat(),
            "last_run_at": None,
            "status": "created",
        }

    async def create(self, name: str, url: str, rules_yaml: str = "") -> dict[str, Any]:
        project = Project(
            org_id=self._db.org_id,
            name=name,
            url=url,
            config_yaml=rules_yaml or None,
        )
        self._db.add(project)
        await self._db.commit()
        await self._db.refresh(project)
        result = self._to_dict(project)
        logger.info("project_created", id=result["id"], name=name, org_id=self._db.org_id)
        return result

    async def list_all(self) -> list[dict[str, Any]]:
        stmt = (
            select(Project)
            .where(Project.org_id == self._db.org_id)
            .order_by(Project.created_at.desc())
        )
        results = await self._db.execute(stmt)
        return [self._to_dict(p) for p in results.scalars().all()]

    async def get(self, project_id: str) -> dict[str, Any] | None:
        stmt = select(Project).where(
            Project.id == int(project_id),
            Project.org_id == self._db.org_id,
        )
        result = (await self._db.execute(stmt)).scalars().first()
        return self._to_dict(result) if result else None

    async def delete(self, project_id: str) -> bool:
        stmt = select(Project).where(
            Project.id == int(project_id),
            Project.org_id == self._db.org_id,
        )
        project = (await self._db.execute(stmt)).scalars().first()
        if not project:
            return False
        await self._db.delete(project)
        await self._db.commit()
        logger.info("project_deleted", id=project_id, org_id=self._db.org_id)
        return True

    async def update(self, project_id: str, **updates: Any) -> dict[str, Any] | None:
        stmt = select(Project).where(
            Project.id == int(project_id),
            Project.org_id == self._db.org_id,
        )
        project = (await self._db.execute(stmt)).scalars().first()
        if not project:
            return None
        if "name" in updates:
            project.name = updates["name"]
        if "url" in updates:
            project.url = updates["url"]
        if "rules_yaml" in updates:
            project.config_yaml = updates["rules_yaml"]
        self._db.add(project)
        await self._db.commit()
        await self._db.refresh(project)
        result = self._to_dict(project)
        for key in ("status", "last_run_id", "last_run_at"):
            if key in updates:
                result[key] = updates[key]
        return result
```

### 3.12 Refactored LlmSettingsRepository

**Modify: `breakthevibe/storage/repositories/llm_settings.py`**

Key changes:
- `LlmSettingsRepository.__init__` takes `TenantScopedSession` instead of `AsyncEngine`
- All queries add `WHERE org_id = :org_id`
- `InMemoryLlmSettingsRepository` becomes tenant-partitioned

```python
"""LLM settings repository — tenant-scoped."""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlmodel import select

from breakthevibe.models.database import LlmSetting
from breakthevibe.storage.tenant_session import TenantScopedSession

logger = structlog.get_logger(__name__)

_DEFAULTS: dict[str, Any] = {
    "default_provider": "anthropic",
    "default_model": "claude-sonnet-4-20250514",
    "modules": {
        "mapper": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        "generator": {"provider": "anthropic", "model": "claude-opus-4-0-20250115"},
        "agent": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    },
    "providers": {
        "anthropic": {"api_key": ""},
        "openai": {"api_key": ""},
        "ollama": {"base_url": "http://localhost:11434"},
    },
}

# In-memory stores partitioned by org_id
_IN_MEMORY_STORES: dict[str, dict[str, Any]] = {}


def get_in_memory_llm_store(org_id: str) -> dict[str, Any]:
    if org_id not in _IN_MEMORY_STORES:
        _IN_MEMORY_STORES[org_id] = _DEFAULTS.copy()
    return _IN_MEMORY_STORES[org_id]


class LlmSettingsRepository:
    """Tenant-scoped LLM settings stored in PostgreSQL."""

    def __init__(self, scoped_session: TenantScopedSession) -> None:
        self._db = scoped_session

    async def get_all(self) -> dict[str, Any]:
        stmt = select(LlmSetting).where(LlmSetting.org_id == self._db.org_id)
        results = await self._db.execute(stmt)
        settings = _DEFAULTS.copy()
        for row in results.scalars().all():
            settings[row.key] = json.loads(row.value_json)
        return settings

    async def set(self, key: str, value: Any) -> None:
        stmt = select(LlmSetting).where(
            LlmSetting.org_id == self._db.org_id,
            LlmSetting.key == key,
        )
        existing = (await self._db.execute(stmt)).scalars().first()
        if existing:
            existing.value_json = json.dumps(value)
            self._db.add(existing)
        else:
            self._db.add(
                LlmSetting(
                    org_id=self._db.org_id,
                    key=key,
                    value_json=json.dumps(value),
                )
            )
        await self._db.commit()
        logger.debug("llm_setting_saved", key=key, org_id=self._db.org_id)

    async def set_many(self, updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            await self.set(key, value)


class InMemoryLlmSettingsRepository:
    """Tenant-partitioned in-memory fallback."""

    def __init__(self, store: dict[str, Any]) -> None:
        self._settings = store

    async def get_all(self) -> dict[str, Any]:
        return self._settings.copy()

    async def set(self, key: str, value: Any) -> None:
        self._settings[key] = value

    async def set_many(self, updates: dict[str, Any]) -> None:
        self._settings.update(updates)
```

### 3.13 Rewritten dependencies.py

**Modify: `breakthevibe/web/dependencies.py`**

Full replacement — module-level singletons replaced with `Depends()` factories:

```python
"""FastAPI dependency injection for tenant-scoped repositories."""

from __future__ import annotations

from typing import Any, AsyncGenerator

import structlog
from fastapi import Depends
from structlog.contextvars import bind_contextvars

from breakthevibe.config.settings import get_settings
from breakthevibe.storage.tenant_session import TenantScopedSession
from breakthevibe.web.auth.rbac import get_tenant
from breakthevibe.web.tenant_context import TenantContext

logger = structlog.get_logger(__name__)

# Pipeline results cache — keyed by "org_id:project_id"
pipeline_results: dict[str, dict[str, Any]] = {}


async def get_scoped_session(
    tenant: TenantContext = Depends(get_tenant),
) -> AsyncGenerator[TenantScopedSession, None]:
    """Yield a TenantScopedSession for the current request."""
    settings = get_settings()

    # Bind tenant to structlog for audit trail
    bind_contextvars(tenant_org_id=tenant.org_id, tenant_user_id=tenant.user_id)

    if not settings.use_database:
        yield TenantScopedSession(session=None, org_id=tenant.org_id)
        return

    from breakthevibe.storage.database import get_engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    engine = get_engine()
    async with AsyncSession(engine) as session:
        yield TenantScopedSession(session=session, org_id=tenant.org_id)


def get_project_repo(
    scoped_session: TenantScopedSession = Depends(get_scoped_session),
) -> Any:
    """Return a tenant-scoped project repository."""
    settings = get_settings()
    if settings.use_database:
        from breakthevibe.storage.repositories.db_projects import DatabaseProjectRepository

        return DatabaseProjectRepository(scoped_session)
    from breakthevibe.storage.repositories.in_memory_projects import (
        InMemoryProjectRepository,
        get_in_memory_store,
    )

    return InMemoryProjectRepository(
        store=get_in_memory_store(scoped_session.org_id),
        org_id=scoped_session.org_id,
    )


def get_llm_settings_repo(
    scoped_session: TenantScopedSession = Depends(get_scoped_session),
) -> Any:
    """Return a tenant-scoped LLM settings repository."""
    settings = get_settings()
    if settings.use_database:
        from breakthevibe.storage.repositories.llm_settings import LlmSettingsRepository

        return LlmSettingsRepository(scoped_session)
    from breakthevibe.storage.repositories.llm_settings import (
        InMemoryLlmSettingsRepository,
        get_in_memory_llm_store,
    )

    return InMemoryLlmSettingsRepository(
        store=get_in_memory_llm_store(scoped_session.org_id)
    )


async def run_pipeline(
    project_id: str,
    url: str,
    rules_yaml: str = "",
    org_id: str = "",
) -> None:
    """Run the full pipeline as a background task."""
    from breakthevibe.web.pipeline import build_pipeline

    logger.info("pipeline_background_start", project_id=project_id, url=url, org_id=org_id)
    try:
        orchestrator = build_pipeline(
            project_id=project_id, url=url, rules_yaml=rules_yaml
        )
        result = await orchestrator.run(
            project_id=project_id, url=url, rules_yaml=rules_yaml
        )

        report = result.report
        result_data: dict[str, Any] = {
            "run_id": result.run_id,
            "success": result.success,
            "completed_stages": [s.value for s in result.completed_stages],
            "failed_stage": result.failed_stage.value if result.failed_stage else None,
            "error_message": result.error_message,
            "duration_seconds": result.duration_seconds,
        }
        if report:
            result_data.update(
                {
                    "total": report.total_suites,
                    "passed": report.passed_suites,
                    "failed": report.failed_suites,
                    "status": report.overall_status.value,
                    "heal_warnings": report.heal_warnings,
                    "suites": [
                        {
                            "name": r.suite_name,
                            "success": r.success,
                            "stdout": r.stdout,
                            "duration": r.duration_seconds,
                            "step_captures": [
                                {
                                    "name": sc.name,
                                    "screenshot_path": sc.screenshot_path,
                                    "network_calls": sc.network_calls,
                                    "console_logs": sc.console_logs,
                                }
                                for sc in r.step_captures
                            ],
                        }
                        for r in report.results
                    ],
                }
            )

        # Key by "org_id:project_id" to prevent cross-tenant reads
        cache_key = f"{org_id}:{project_id}" if org_id else project_id
        pipeline_results[cache_key] = result_data

        if org_id and get_settings().use_database:
            await _persist_test_run(org_id, project_id, result_data)

        logger.info(
            "pipeline_background_done",
            project_id=project_id,
            success=result.success,
        )

    except Exception as e:
        logger.error("pipeline_background_error", project_id=project_id, error=str(e))
        cache_key = f"{org_id}:{project_id}" if org_id else project_id
        pipeline_results[cache_key] = {"success": False, "error_message": str(e)}


async def _persist_test_run(
    org_id: str, project_id: str, result_data: dict[str, Any]
) -> None:
    """Persist test run results to DB."""
    try:
        from sqlmodel.ext.asyncio.session import AsyncSession

        from breakthevibe.models.database import TestRun
        from breakthevibe.storage.database import get_engine

        async with AsyncSession(get_engine()) as session:
            test_run = TestRun(
                org_id=org_id,
                project_id=int(project_id),
                status="completed" if result_data.get("success") else "failed",
                execution_mode="smart",
                total=len(result_data.get("completed_stages", [])),
                passed=1 if result_data.get("success") else 0,
                failed=0 if result_data.get("success") else 1,
            )
            session.add(test_run)
            await session.commit()
            logger.info("test_run_persisted", project_id=project_id, org_id=org_id)
    except Exception as e:
        logger.warning("test_run_persist_failed", error=str(e))
```

### 3.14 Route File Changes

Each route file follows the same pattern. Here are the complete diffs:

#### `breakthevibe/web/routes/projects.py`

**BEFORE (line 6-10)**:
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from breakthevibe.utils.sanitize import is_safe_url
from breakthevibe.web.dependencies import project_repo
```

**AFTER**:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from breakthevibe.utils.sanitize import is_safe_url
from breakthevibe.web.auth.rbac import require_member, require_viewer
from breakthevibe.web.dependencies import get_project_repo
from breakthevibe.web.tenant_context import TenantContext
```

**BEFORE (line 33-43)** — create_project:
```python
@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(body: CreateProjectRequest) -> dict:
    if not is_safe_url(str(body.url)):
        raise HTTPException(status_code=422, detail="URL targets a private or reserved IP address")
    project = await project_repo.create(
        name=body.name,
        url=str(body.url),
        rules_yaml=body.rules_yaml,
    )
    return project
```

**AFTER**:
```python
@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: CreateProjectRequest,
    tenant: TenantContext = Depends(require_member),
    project_repo: Any = Depends(get_project_repo),
) -> dict:
    if not is_safe_url(str(body.url)):
        raise HTTPException(status_code=422, detail="URL targets a private or reserved IP address")
    project = await project_repo.create(
        name=body.name,
        url=str(body.url),
        rules_yaml=body.rules_yaml,
    )
    return project
```

**Same pattern for all other route functions** — add `tenant: TenantContext = Depends(require_viewer/require_member)` and `project_repo = Depends(get_project_repo)`.

#### `breakthevibe/web/routes/crawl.py`

```python
# BEFORE
from breakthevibe.web.dependencies import project_repo, run_pipeline

# AFTER
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from breakthevibe.web.auth.rbac import require_member, require_viewer
from breakthevibe.web.dependencies import get_project_repo, run_pipeline
from breakthevibe.web.tenant_context import TenantContext
```

In `trigger_crawl`, add tenant context and pass `org_id` to `run_pipeline`:

```python
@router.post("/api/projects/{project_id}/crawl")
async def trigger_crawl(
    project_id: str,
    background_tasks: BackgroundTasks,
    tenant: TenantContext = Depends(require_member),
    project_repo: Any = Depends(get_project_repo),
) -> dict:
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(
        run_pipeline,
        project_id=project_id,
        url=project["url"],
        rules_yaml=project.get("rules_yaml", ""),
        org_id=tenant.org_id,
    )

    await project_repo.update(project_id, status="crawling")
    logger.info("crawl_triggered", project_id=project_id, org_id=tenant.org_id)
    return {"status": "accepted", "project_id": project_id, "message": "Crawl started"}
```

#### `breakthevibe/web/routes/results.py`

Change `pipeline_results` lookups to use `f"{tenant.org_id}:{project_id}"`:

```python
@router.get("/api/projects/{project_id}/results")
async def get_project_results(
    project_id: str,
    tenant: TenantContext = Depends(require_viewer),
) -> dict:
    cache_key = f"{tenant.org_id}:{project_id}"
    result = pipeline_results.get(cache_key)
    if not result:
        return {"project_id": project_id, "status": "no_runs"}
    return {
        "project_id": project_id,
        "run_id": result.get("run_id"),
        "status": "completed" if result.get("success") else "failed",
        "completed_stages": result.get("completed_stages", []),
        "error_message": result.get("error_message", ""),
        "duration_seconds": result.get("duration_seconds", 0),
    }
```

#### `breakthevibe/web/routes/settings.py`

Change `llm_settings_repo` from import to `Depends(get_llm_settings_repo)`, use `require_admin` for LLM settings:

```python
from breakthevibe.web.auth.rbac import require_admin, require_member, require_viewer
from breakthevibe.web.dependencies import get_llm_settings_repo, get_project_repo

@router.put("/api/settings/llm")
async def update_llm_settings(
    request: Request,
    tenant: TenantContext = Depends(require_admin),
    llm_settings_repo: Any = Depends(get_llm_settings_repo),
) -> dict:
    # ... existing logic unchanged ...
```

#### `breakthevibe/web/routes/pages.py`

All page routes get tenant + repo injection. Pipeline results use namespaced keys:

```python
from breakthevibe.web.auth.rbac import require_viewer
from breakthevibe.web.dependencies import get_project_repo, pipeline_results

@router.get("/projects/{project_id}/runs", response_class=HTMLResponse)
async def test_runs_page(
    request: Request,
    project_id: str,
    tenant: TenantContext = Depends(require_viewer),
    project_repo: Any = Depends(get_project_repo),
) -> HTMLResponse:
    project = await project_repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    cache_key = f"{tenant.org_id}:{project_id}"
    result = pipeline_results.get(cache_key, {})
    # ... rest unchanged ...
```

### 3.15 App Factory Changes

**Modify: `breakthevibe/web/app.py`**

Remove the global `Depends(require_auth)` from the protected router group (each route now has its own RBAC dependency):

```python
# BEFORE (line 57-60):
protected = [projects_router, crawl_router, tests_router, results_router, settings_router]
for router in protected:
    app.include_router(router, dependencies=[Depends(require_auth)])

# AFTER:
protected = [projects_router, crawl_router, tests_router, results_router, settings_router]
for router in protected:
    app.include_router(router)  # Auth is per-route via Depends(require_member/viewer/admin)
```

Remove the `require_auth` import. Add auth_mode to health check:

```python
@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "healthy", "version": "0.1.0", "auth_mode": settings.auth_mode}
```

---

## 4. RBAC Permission Matrix

| Route | Method | Current Auth | New RBAC |
|---|---|---|---|
| `POST /api/auth/login` | POST | None (public) | None (public) |
| `POST /api/auth/logout` | POST | None (public) | None (public) |
| `GET /api/health` | GET | None (public) | None (public) |
| `GET /api/projects` | GET | `require_auth` | `require_viewer` |
| `POST /api/projects` | POST | `require_auth` | `require_member` |
| `GET /api/projects/{id}` | GET | `require_auth` | `require_viewer` |
| `DELETE /api/projects/{id}` | DELETE | `require_auth` | `require_member` |
| `POST /api/projects/{id}/crawl` | POST | `require_auth` | `require_member` |
| `GET /api/projects/{id}/sitemap` | GET | `require_auth` | `require_viewer` |
| `POST /api/projects/{id}/generate` | POST | `require_auth` | `require_member` |
| `POST /api/projects/{id}/run` | POST | `require_auth` | `require_member` |
| `GET /api/runs/{id}/results` | GET | `require_auth` | `require_viewer` |
| `GET /api/projects/{id}/results` | GET | `require_auth` | `require_viewer` |
| `PUT /api/projects/{id}/rules` | PUT | `require_auth` | `require_member` |
| `POST /api/rules/validate` | POST | `require_auth` | `require_member` |
| `PUT /api/settings/llm` | PUT | `require_auth` | `require_admin` |
| `GET /settings/llm` | GET | per-route | `require_admin` |
| `GET /` | GET | per-route | `require_viewer` |
| `GET /projects/{id}` | GET | per-route | `require_viewer` |
| `GET /projects/{id}/runs` | GET | per-route | `require_viewer` |
| `GET /projects/{id}/suites` | GET | per-route | `require_viewer` |
| `GET /runs/{id}` | GET | per-route | `require_viewer` |
| `GET /projects/{id}/rules` | GET | per-route | `require_viewer` |

---

## 5. Verification Checklist

- [ ] `AUTH_MODE=single` (default): all existing routes work identically
- [ ] `USE_DATABASE=false`: in-memory repos work with tenant partitioning
- [ ] `USE_DATABASE=true`: DB repos filter all queries by `org_id`
- [ ] Alembic migrations apply cleanly on empty DB
- [ ] Alembic migrations apply cleanly on DB with existing data (backfill works)
- [ ] Existing tests pass without modification
- [ ] New test: TenantContext role checks
- [ ] New test: RBAC deps reject unauthorized roles
- [ ] New test: Tenant A cannot read Tenant B's projects (DB mode)
- [ ] New test: Tenant A cannot read Tenant B's projects (in-memory mode)
- [ ] `mypy breakthevibe/` passes
- [ ] `ruff check` passes
- [ ] Pipeline results use namespaced cache keys

---

## 6. Files Summary

| Action | File | Lines Changed (est.) |
|---|---|---|
| CREATE | `breakthevibe/web/tenant_context.py` | ~35 |
| CREATE | `breakthevibe/storage/tenant_session.py` | ~40 |
| CREATE | `breakthevibe/web/auth/single_tenant.py` | ~35 |
| CREATE | `breakthevibe/web/auth/rbac.py` | ~50 |
| CREATE | `breakthevibe/storage/repositories/in_memory_projects.py` | ~60 |
| CREATE | migration: `add_tenancy_tables.py` | ~70 |
| CREATE | migration: `add_org_id_to_data_tables.py` | ~70 |
| MODIFY | `breakthevibe/models/database.py` | ~80 new lines |
| MODIFY | `breakthevibe/config/settings.py` | ~25 new lines |
| MODIFY | `breakthevibe/web/dependencies.py` | Full rewrite (~130 lines) |
| MODIFY | `breakthevibe/storage/repositories/db_projects.py` | Full rewrite (~80 lines) |
| MODIFY | `breakthevibe/storage/repositories/llm_settings.py` | Full rewrite (~80 lines) |
| MODIFY | `breakthevibe/web/app.py` | ~10 lines changed |
| MODIFY | `breakthevibe/web/routes/projects.py` | ~15 lines changed |
| MODIFY | `breakthevibe/web/routes/crawl.py` | ~15 lines changed |
| MODIFY | `breakthevibe/web/routes/tests.py` | ~15 lines changed |
| MODIFY | `breakthevibe/web/routes/results.py` | ~20 lines changed |
| MODIFY | `breakthevibe/web/routes/settings.py` | ~20 lines changed |
| MODIFY | `breakthevibe/web/routes/pages.py` | ~30 lines changed |
| MODIFY | `breakthevibe/storage/migrations/env.py` | 3 new imports |
