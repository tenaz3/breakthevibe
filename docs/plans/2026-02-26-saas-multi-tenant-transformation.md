# BreakTheVibe: SaaS Multi-Tenant Transformation Plan

> **Date**: 2026-02-26
> **Status**: Planning
> **Branch**: `feat/multi-tenant-saas`

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Target Architecture Overview](#3-target-architecture-overview)
4. [Phase 1: Multi-Tenancy Foundation](#phase-1-multi-tenancy-foundation)
5. [Phase 2: Clerk Authentication Integration](#phase-2-clerk-authentication-integration)
6. [Phase 3: Billing & Usage Limits](#phase-3-billing--usage-limits)
7. [Phase 4: Infrastructure & Operations](#phase-4-infrastructure--operations)
8. [Phase 5: Audit Logging & Compliance](#phase-5-audit-logging--compliance)
9. [Phase 6: Pipeline Isolation & Job Queue](#phase-6-pipeline-isolation--job-queue)
10. [Phase 7: Object Storage (S3/R2)](#phase-7-object-storage-s3r2)
11. [Edge Cases & Configuration Review](#edge-cases--configuration-review)
12. [Migration Strategy](#migration-strategy)
13. [Testing Strategy](#testing-strategy)
14. [Implementation Sequence & Dependencies](#implementation-sequence--dependencies)

---

## 1. Executive Summary

Transform BreakTheVibe from a single-tenant, self-hosted QA platform into a multi-tenant SaaS product. Key decisions:

| Decision | Choice | Rationale |
|---|---|---|
| Tenancy model | Organization-based (company with multiple users) | Enterprise QA teams need shared projects |
| Data isolation | Shared DB with `org_id` column | Cost-effective, simplest ops, sufficient for GDPR/SOC 2 |
| Authentication | Clerk | Managed auth, org support built-in, webhook sync |
| Roles | admin / member / viewer per org | Matches QA team hierarchies |
| Billing | Stripe (later), plan model now | Ready for monetization without re-architecture |
| Tiers | free / starter / pro | Usage-limited tiers with enforcement |
| Artifact storage | S3/R2 with local fallback | Horizontal scaling, per-tenant isolation |
| Pipeline isolation | DB-backed job queue with per-tenant concurrency limits | Prevent noisy neighbors |
| Compliance | GDPR right to erasure, SOC 2 audit logging | Required for enterprise customers |
| Backward compat | `AUTH_MODE=single` preserves all existing behavior | Zero disruption for self-hosted users |

---

## 2. Current State Analysis

### What Exists Today

```
breakthevibe/
  config/settings.py          # Pydantic BaseSettings, env vars
  models/database.py          # 7 SQLModel tables (no tenant_id)
  web/
    app.py                    # FastAPI factory, CORS hardcoded to localhost
    dependencies.py           # Module-level singleton repos
    auth/session.py           # HMAC cookie sessions, in-memory store
    middleware.py              # In-memory rate limiter
    routes/                   # 7 route files import singleton repos
  storage/
    artifacts.py              # Local filesystem
    database.py               # AsyncEngine singleton
    repositories/
      projects.py             # In-memory ProjectRepository
      db_projects.py          # PostgreSQL DatabaseProjectRepository
      llm_settings.py         # LlmSettingsRepository + in-memory fallback
    migrations/versions/      # 1 initial migration
  agent/orchestrator.py       # 5-stage pipeline (crawl->map->gen->run->report)
```

### Critical Gaps for SaaS

| Gap | Impact | Phase to Address |
|---|---|---|
| No user model or user table | Cannot identify who did what | Phase 1 |
| No organization/tenant concept | All data is global | Phase 1 |
| No `org_id` on any data table | No data isolation | Phase 1 |
| Single admin user via env vars | Cannot serve multiple customers | Phase 2 |
| In-memory sessions | Lost on restart, no multi-worker | Phase 2 |
| No RBAC | All authenticated users are admin | Phase 2 |
| No usage limits or plans | Cannot monetize or prevent abuse | Phase 3 |
| No billing integration | Cannot charge customers | Phase 3 |
| In-memory rate limiter | Not shared across workers | Phase 4 |
| Local filesystem artifacts | Cannot scale horizontally | Phase 7 |
| No audit logging | Cannot prove compliance | Phase 5 |
| Pipeline runs as BackgroundTasks | No persistence, no isolation, no queue | Phase 6 |
| CORS hardcoded to localhost | Cannot deploy to custom domains | Phase 4 |
| No monitoring/alerting | Blind to production issues | Phase 4 |

---

## 3. Target Architecture Overview

### Data Model (Entity Relationship)

```
organizations ─────┬──── organization_memberships ────── users
    │               │
    │ org_id        │
    ├── projects    │
    │     ├── crawl_runs
    │     │     └── routes
    │     ├── test_cases
    │     ├── test_runs
    │     │     └── test_results
    │     └── pipeline_jobs
    │
    ├── llm_settings
    ├── subscriptions ──── plans
    ├── usage_records
    └── audit_logs
```

### Request Flow (Multi-Tenant)

```
Client (Bearer JWT from Clerk)
  │
  ▼
Nginx/Caddy (TLS, rate limit, proxy)
  │
  ▼
FastAPI App
  ├── RequestIDMiddleware (correlation ID)
  ├── TenantRateLimitMiddleware (per-org limits)
  │
  ├── Route Handler
  │     ├── Depends(require_member)
  │     │     └── Depends(get_tenant)
  │     │           └── require_clerk_auth(request)
  │     │                 ├── Extract Bearer token
  │     │                 ├── Verify RS256 JWT via Clerk JWKS
  │     │                 ├── Resolve org_id + user_id + role from DB
  │     │                 └── Return TenantContext(org_id, user_id, role)
  │     │
  │     ├── Depends(get_project_repo)
  │     │     └── Depends(get_scoped_session)
  │     │           └── TenantScopedSession(AsyncSession, org_id)
  │     │                 └── DatabaseProjectRepository(scoped_session)
  │     │                       └── SELECT ... WHERE org_id = :org_id
  │     │
  │     └── Depends(check_usage_limit)
  │           └── UsageEnforcer.check("projects", tenant)
  │
  └── AuditLogger.log(tenant, action, resource)
```

### Backward Compatibility (Single-Tenant)

```
Client (Cookie: session=<hmac_token>)
  │
  ▼
FastAPI App (AUTH_MODE=single)
  ├── require_single_tenant_auth(request)
  │     ├── Validate HMAC session cookie (existing logic)
  │     └── Return TenantContext(
  │           org_id="00000000-0000-0000-0000-000000000001",
  │           role="admin"
  │         )
  └── ... same Depends chain, using sentinel org_id
```

---

## Phase 1: Multi-Tenancy Foundation

> **Detailed Plan**: [phases/phase-1-multi-tenancy-foundation.md](phases/phase-1-multi-tenancy-foundation.md)

### Goal
Add organization, user, and membership models. Add `org_id` to all data tables. Refactor repositories to enforce tenant scoping on every query.

### 1.1 New Database Models

**File: `breakthevibe/models/database.py`**

#### Organization
```python
class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: str = Field(default_factory=_new_uuid, primary_key=True,
                    sa_column=Column(String(36)))
    clerk_org_id: str = Field(index=True, unique=True)
    name: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    plan: str = Field(default="free")     # free | starter | pro
    is_active: bool = Field(default=True)
    deleted_at: datetime | None = None    # GDPR soft-delete
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

#### User
```python
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_new_uuid, primary_key=True,
                    sa_column=Column(String(36)))
    clerk_user_id: str = Field(index=True, unique=True)
    email: str = Field(index=True)
    display_name: str | None = None
    avatar_url: str | None = None
    deleted_at: datetime | None = None    # GDPR erasure
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

#### OrganizationMembership
```python
class OrganizationMembership(SQLModel, table=True):
    __tablename__ = "organization_memberships"

    id: str = Field(default_factory=_new_uuid, primary_key=True,
                    sa_column=Column(String(36)))
    org_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    clerk_membership_id: str = Field(index=True, unique=True)
    role: str = Field(default="member")   # admin | member | viewer
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

### 1.2 Add `org_id` to All Existing Tables

Every data table gets a new column:

```python
org_id: str = Field(foreign_key="organizations.id", index=True)
```

**Tables affected**: `projects`, `crawl_runs`, `routes`, `test_cases`, `test_runs`, `test_results`, `llm_settings`

**Special case**: `llm_settings` unique constraint changes from `(key)` to `(org_id, key)` — each org configures its own LLM settings.

### 1.3 Alembic Migrations

**Migration 1**: `add_tenancy_tables` — creates `organizations`, `users`, `organization_memberships` tables with all indexes.

**Migration 2**: `add_org_id_to_data_tables` — seeds a sentinel organization (`00000000-0000-0000-0000-000000000001`), adds nullable `org_id` column to all 7 tables, backfills existing rows with sentinel org, adds NOT NULL + FK constraints, updates `llm_settings` unique constraint.

### 1.4 TenantContext Dataclass

**New file: `breakthevibe/web/tenant_context.py`**

```python
@dataclass(frozen=True, slots=True)
class TenantContext:
    org_id: str           # Internal UUID from organizations table
    clerk_org_id: str     # Clerk's org ID for logging
    user_id: str          # Internal UUID from users table
    clerk_user_id: str    # Clerk's user ID for logging
    role: str             # admin | member | viewer
    email: str

    def is_admin(self) -> bool: ...
    def is_at_least_member(self) -> bool: ...
    def is_viewer(self) -> bool: ...
```

### 1.5 TenantScopedSession

**New file: `breakthevibe/storage/tenant_session.py`**

Thin wrapper around `AsyncSession` that carries `org_id`:

```python
class TenantScopedSession:
    def __init__(self, session: AsyncSession, org_id: str) -> None:
        self._session = session
        self.org_id = org_id

    # Pass-throughs: execute(), add(), commit(), refresh(), delete(), get()
```

Repositories receive this instead of a raw engine/session, making tenant context impossible to forget.

### 1.6 Repository Refactor

**Current**: Module-level singletons created at import time in `dependencies.py`.

**Target**: Per-request instances created via `Depends()`:

```python
# dependencies.py
async def get_scoped_session(
    tenant: TenantContext = Depends(get_tenant),
) -> AsyncGenerator[TenantScopedSession, None]:
    engine = get_engine()
    async with AsyncSession(engine) as session:
        yield TenantScopedSession(session=session, org_id=tenant.org_id)

def get_project_repo(
    scoped_session: TenantScopedSession = Depends(get_scoped_session),
) -> DatabaseProjectRepository:
    return DatabaseProjectRepository(scoped_session)
```

**DatabaseProjectRepository changes**:
- Constructor takes `TenantScopedSession` instead of `AsyncEngine`
- `create()` sets `org_id=self._db.org_id` on new records
- `list_all()` adds `WHERE org_id = :org_id`
- `get()`, `delete()`, `update()` add `WHERE org_id = :org_id` (cross-tenant guard)

### 1.7 Route Refactor

All 7 route files change from:

```python
# OLD — imports module-level singleton
from breakthevibe.web.dependencies import project_repo

@router.get("")
async def list_projects() -> list:
    return await project_repo.list_all()
```

To:

```python
# NEW — per-request dependency injection
from breakthevibe.web.dependencies import get_project_repo

@router.get("")
async def list_projects(
    tenant: TenantContext = Depends(require_viewer),
    project_repo = Depends(get_project_repo),
) -> list:
    return await project_repo.list_all()
```

### 1.8 Files to Create/Modify

| Action | File | Purpose |
|---|---|---|
| CREATE | `breakthevibe/web/tenant_context.py` | TenantContext dataclass |
| CREATE | `breakthevibe/storage/tenant_session.py` | TenantScopedSession wrapper |
| CREATE | `breakthevibe/storage/repositories/in_memory_projects.py` | Tenant-partitioned in-memory repo |
| CREATE | `breakthevibe/web/auth/single_tenant.py` | Backward compat auth shim |
| CREATE | `breakthevibe/web/auth/rbac.py` | Role-based access control dependencies |
| CREATE | `migrations/.../add_tenancy_tables.py` | Migration: new tenancy tables |
| CREATE | `migrations/.../add_org_id_to_data_tables.py` | Migration: org_id on all tables |
| MODIFY | `breakthevibe/models/database.py` | Add 3 new models + org_id on 7 existing |
| MODIFY | `breakthevibe/config/settings.py` | Add auth_mode, single_tenant_org_id |
| MODIFY | `breakthevibe/web/dependencies.py` | Replace singletons with Depends factories |
| MODIFY | `breakthevibe/storage/repositories/db_projects.py` | Accept TenantScopedSession |
| MODIFY | `breakthevibe/storage/repositories/llm_settings.py` | Accept TenantScopedSession |
| MODIFY | `breakthevibe/web/app.py` | Remove global Depends(require_auth) |
| MODIFY | `breakthevibe/web/routes/projects.py` | Use Depends + RBAC |
| MODIFY | `breakthevibe/web/routes/crawl.py` | Use Depends + RBAC |
| MODIFY | `breakthevibe/web/routes/tests.py` | Use Depends + RBAC |
| MODIFY | `breakthevibe/web/routes/results.py` | Use Depends + namespaced cache |
| MODIFY | `breakthevibe/web/routes/settings.py` | Use Depends + require_admin |
| MODIFY | `breakthevibe/web/routes/pages.py` | Use Depends |
| MODIFY | `breakthevibe/storage/migrations/env.py` | Import new models |

### 1.9 RBAC Permission Matrix

| Route | Method | Required Role |
|---|---|---|
| `/api/projects` | GET | viewer |
| `/api/projects` | POST | member |
| `/api/projects/{id}` | GET | viewer |
| `/api/projects/{id}` | DELETE | member |
| `/api/projects/{id}/crawl` | POST | member |
| `/api/projects/{id}/generate` | POST | member |
| `/api/projects/{id}/run` | POST | member |
| `/api/projects/{id}/sitemap` | GET | viewer |
| `/api/projects/{id}/results` | GET | viewer |
| `/api/runs/{id}/results` | GET | viewer |
| `/api/settings/llm` | PUT | admin |
| `/api/projects/{id}/rules` | PUT | member |
| `/api/rules/validate` | POST | member |

---

## Phase 2: Clerk Authentication Integration

> **Detailed Plan**: [phases/phase-2-clerk-authentication.md](phases/phase-2-clerk-authentication.md)

### Goal
Replace the single-admin HMAC cookie auth with Clerk JWT validation for multi-tenant mode, while keeping the existing auth as a fallback.

### 2.1 Settings Additions

```python
# config/settings.py — new fields
auth_mode: str = "single"              # "single" | "clerk"
clerk_secret_key: str | None = None    # sk_live_XXX
clerk_publishable_key: str | None = None
clerk_webhook_secret: str | None = None # whsec_XXX
clerk_issuer: str | None = None        # https://<instance>.clerk.accounts.dev
clerk_audience: str | None = None
clerk_jwks_url: str | None = None      # https://<instance>.clerk.accounts.dev/.well-known/jwks.json
single_tenant_org_id: str = "00000000-0000-0000-0000-000000000001"
```

Validation: when `auth_mode=clerk`, all `clerk_*` fields are required at startup.

### 2.2 Clerk JWT Validation

**New file: `breakthevibe/web/auth/clerk.py`**

Flow:
1. Extract Bearer token from `Authorization` header or `__session` cookie
2. Fetch Clerk JWKS (cached 1 hour with `time.monotonic()` TTL)
3. Decode RS256 JWT using PyJWT, verify audience + issuer + expiry
4. Extract `sub` (clerk_user_id), `org_id` (clerk_org_id), `org_role`
5. Look up internal User, Organization, OrganizationMembership in DB
6. Return `TenantContext`

**Dependencies to add**: `PyJWT>=2.8.0`, `cryptography>=43.0.0`

**Key security details**:
- Constant-time HMAC comparison for JWKS kid matching
- JWKS cache TTL of 1 hour; forced refresh on verification failure (one retry)
- Reject tokens without `org_id` claim (user must select an org in Clerk)
- Reject tokens for inactive or soft-deleted orgs

### 2.3 Clerk Webhook Handler

**New file: `breakthevibe/web/auth/webhook.py`**

Public endpoint `POST /api/webhooks/clerk/` that:
1. Verifies Svix signature (HMAC-SHA256 with `CLERK_WEBHOOK_SECRET`)
2. Rejects replays older than 5 minutes
3. Dispatches to handler by event type:

| Event | Handler | Action |
|---|---|---|
| `user.created` | `_upsert_user` | INSERT/UPDATE users row |
| `user.updated` | `_upsert_user` | UPDATE email, name, avatar |
| `user.deleted` | `_soft_delete_user` | Anonymize PII, set deleted_at (GDPR) |
| `organization.created` | `_upsert_org` | INSERT organizations row |
| `organization.updated` | `_upsert_org` | UPDATE name, slug |
| `organization.deleted` | `_soft_delete_org` | Set is_active=false, deleted_at |
| `organizationMembership.created` | `_upsert_membership` | INSERT membership |
| `organizationMembership.updated` | `_upsert_membership` | UPDATE role |
| `organizationMembership.deleted` | `_deactivate_membership` | Set is_active=false |

**GDPR**: `user.deleted` anonymizes email to `deleted_{id}@erased.invalid`, nulls display_name and avatar_url, sets `deleted_at` timestamp.

**Idempotency**: All handlers use SELECT-then-INSERT/UPDATE pattern. Clerk unique IDs as DB unique indexes prevent duplicate inserts.

### 2.4 Single-Tenant Auth Shim

**New file: `breakthevibe/web/auth/single_tenant.py`**

When `AUTH_MODE=single`:
- Validates existing HMAC session cookie (reuses `session.py`)
- Returns synthetic `TenantContext` with sentinel org UUID and `role="admin"`
- Zero behavior change from current system

### 2.5 Auth Mode Selection

**File: `breakthevibe/web/auth/rbac.py`**

```python
def _get_auth_dependency():
    settings = get_settings()
    if settings.auth_mode == "clerk":
        from breakthevibe.web.auth.clerk import require_clerk_auth
        return require_clerk_auth
    else:
        from breakthevibe.web.auth.single_tenant import require_single_tenant_auth
        return require_single_tenant_auth
```

This is resolved once at module load time (settings are immutable after startup).

### 2.6 Files to Create/Modify

| Action | File |
|---|---|
| CREATE | `breakthevibe/web/auth/clerk.py` |
| CREATE | `breakthevibe/web/auth/webhook.py` |
| CREATE | `breakthevibe/web/auth/single_tenant.py` |
| CREATE | `breakthevibe/web/auth/rbac.py` |
| MODIFY | `breakthevibe/web/app.py` (conditional webhook router) |
| MODIFY | `breakthevibe/config/settings.py` (clerk fields) |
| MODIFY | `pyproject.toml` (PyJWT, cryptography deps) |

---

## Phase 3: Billing & Usage Limits

> **Detailed Plan**: [phases/phase-3-billing-usage-limits.md](phases/phase-3-billing-usage-limits.md)

### Goal
Define the plan/subscription data model now so it's ready for Stripe. Enforce usage limits immediately (even on free tier) to prevent abuse.

### 3.1 Plan Tiers

```python
PLAN_LIMITS = {
    "free": {
        "max_projects": 3,
        "max_crawls_per_month": 10,
        "max_test_runs_per_month": 20,
        "max_artifact_storage_mb": 500,
        "max_concurrent_pipelines": 1,
        "rate_limit_per_minute": 30,
    },
    "starter": {
        "max_projects": 20,
        "max_crawls_per_month": 100,
        "max_test_runs_per_month": 500,
        "max_artifact_storage_mb": 5_000,
        "max_concurrent_pipelines": 3,
        "rate_limit_per_minute": 120,
    },
    "pro": {
        "max_projects": -1,  # unlimited
        "max_crawls_per_month": -1,
        "max_test_runs_per_month": -1,
        "max_artifact_storage_mb": 50_000,
        "max_concurrent_pipelines": 10,
        "rate_limit_per_minute": 600,
    },
}
```

### 3.2 New Database Models

#### Subscription
```python
class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: str = Field(default_factory=_new_uuid, primary_key=True,
                    sa_column=Column(String(36)))
    org_id: str = Field(foreign_key="organizations.id", index=True, unique=True)
    plan: str = Field(default="free")
    status: str = Field(default="active")           # active | canceled | past_due
    stripe_subscription_id: str | None = None       # Stripe sub ID (future)
    stripe_customer_id: str | None = None            # Stripe customer ID (future)
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

#### UsageRecord
```python
class UsageRecord(SQLModel, table=True):
    __tablename__ = "usage_records"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    metric: str = Field(index=True)                  # projects | crawls | test_runs
    count: int = Field(default=0)
    period_start: datetime                           # First day of month
    period_end: datetime                             # Last day of month
    created_at: datetime = Field(default_factory=_utc_now)

    # Composite unique: (org_id, metric, period_start)
```

### 3.3 Usage Enforcement

**New file: `breakthevibe/web/usage.py`**

```python
class UsageEnforcer:
    """Checks usage against plan limits before allowing operations."""

    async def check(self, metric: str, tenant: TenantContext,
                    session: TenantScopedSession) -> None:
        """Raise HTTP 429 if usage limit exceeded for this metric."""
        plan = await self._get_plan(tenant.org_id, session)
        limit = PLAN_LIMITS[plan].get(f"max_{metric}")
        if limit == -1:
            return  # unlimited
        current = await self._get_current_usage(tenant.org_id, metric, session)
        if current >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Plan limit reached: {metric} ({current}/{limit})"
            )

    async def increment(self, metric: str, org_id: str,
                        session: TenantScopedSession) -> None:
        """Increment usage counter for this period."""
        ...
```

**Usage in routes**:

```python
@router.post("", status_code=201)
async def create_project(
    body: CreateProjectRequest,
    tenant: TenantContext = Depends(require_member),
    project_repo = Depends(get_project_repo),
    usage: UsageEnforcer = Depends(get_usage_enforcer),
):
    await usage.check("projects", tenant)
    result = await project_repo.create(...)
    await usage.increment("projects", tenant.org_id)
    return result
```

### 3.4 Stripe Integration (Future — Design Only)

When ready to add Stripe:
1. Add `stripe>=8.0.0` dependency
2. Create `breakthevibe/billing/stripe_service.py`:
   - Webhook handler for `customer.subscription.created/updated/deleted`
   - Sync subscription status to `subscriptions` table
   - Checkout session creation for plan upgrades
3. Create route `POST /api/billing/checkout` and `POST /api/webhooks/stripe/`
4. Update `Organization.plan` when Stripe subscription changes
5. Add `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` to settings

### 3.5 Files to Create/Modify

| Action | File |
|---|---|
| CREATE | `breakthevibe/billing/__init__.py` |
| CREATE | `breakthevibe/billing/plans.py` (PLAN_LIMITS config) |
| CREATE | `breakthevibe/web/usage.py` (UsageEnforcer) |
| CREATE | migration: `add_subscription_and_usage_tables.py` |
| MODIFY | `breakthevibe/models/database.py` (Subscription, UsageRecord) |
| MODIFY | Route files (add usage.check() calls) |

---

## Phase 4: Infrastructure & Operations

> **Detailed Plan**: [phases/phase-4-infrastructure-operations.md](phases/phase-4-infrastructure-operations.md)

### Goal
Make the Docker Compose stack production-ready for SaaS. Add proper CORS, TLS, multi-worker support, monitoring, and environment management.

### 4.1 Enhanced Settings

```python
# config/settings.py — infrastructure additions
environment: str = "development"          # development | staging | production
allowed_origins: list[str] = Field(default=["http://localhost:8000"])
                                          # CORS origins, env-configurable

# S3/R2 object storage
s3_bucket: str | None = None
s3_endpoint_url: str | None = None        # For R2/MinIO
s3_access_key_id: str | None = None
s3_secret_access_key: str | None = None
s3_region: str = "auto"
use_s3: bool = False                      # False = local filesystem (default)
```

### 4.2 Docker Compose Enhancements

**Profile-based configuration**:

```yaml
# docker-compose.yml — base (dev)
# docker-compose.prod.yml — production overlay
# docker-compose.clerk.yml — Clerk env vars overlay
```

Production overlay adds:
- **Caddy** reverse proxy (automatic HTTPS via Let's Encrypt)
- **App replicas**: `deploy.replicas: 2` with health checks
- **Resource limits**: CPU and memory caps per service
- **Volume mounts**: Separate data, logs directories
- **Network isolation**: Internal network for DB, external for app

### 4.3 Caddy Reverse Proxy

```
# Caddyfile
{$DOMAIN:localhost} {
    reverse_proxy app:8000 {
        lb_policy round_robin
        health_uri /api/health
        health_interval 10s
    }
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Content-Security-Policy "default-src 'self'"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

### 4.4 Database Connection Pooling

Current: `pool_size=5, max_overflow=10` (adequate for 1 worker).
Target:
- Per-worker: `pool_size=5, max_overflow=5`
- With 2 workers: 20 total connections
- Add `pool_pre_ping=True` for connection health checks
- Add `pool_recycle=3600` to avoid stale connections

For production scaling beyond 4 workers, add **PgBouncer** as a sidecar container:
```yaml
pgbouncer:
    image: edoburu/pgbouncer:latest
    environment:
        DATABASE_URL: postgresql://breakthevibe:breakthevibe@db:5432/breakthevibe
        MAX_CLIENT_CONN: 200
        DEFAULT_POOL_SIZE: 20
        POOL_MODE: transaction
```

### 4.5 Environment Configuration Strategy

| Setting | Dev | Staging | Production |
|---|---|---|---|
| `ENVIRONMENT` | development | staging | production |
| `DEBUG` | true | false | false |
| `USE_DATABASE` | false | true | true |
| `AUTH_MODE` | single | clerk | clerk |
| `LOG_LEVEL` | DEBUG | INFO | INFO |
| `ALLOWED_ORIGINS` | localhost:8000 | staging.breakthevibe.io | app.breakthevibe.io |
| `USE_S3` | false | true | true |
| `SECRET_KEY` | (default) | (random 64-char) | (random 64-char) |

### 4.6 CORS Configuration

Move from hardcoded to env-configurable:

```python
# app.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### 4.7 Security Headers

Add via Caddy (production) or middleware (development):
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`

### 4.8 Monitoring & Observability

| Component | Tool | Implementation |
|---|---|---|
| Structured logs | structlog JSON (existing) | Ship to CloudWatch/Loki via Fluent Bit |
| Health checks | `/api/health` (existing) | Add DB check, S3 check, Clerk check |
| Metrics | Prometheus client | Add `prometheus_fastapi_instrumentator` |
| Error tracking | Sentry | Add `sentry-sdk[fastapi]` |
| Uptime monitoring | External (Betterstack/Pingdom) | Check `/api/health` every 30s |

### 4.9 CI/CD Enhancements

Add to `.github/workflows/ci.yml`:
- **Migration safety check**: Run `alembic check` to detect pending migrations
- **Staging deploy**: On merge to `main`, deploy to staging
- **Production deploy**: Manual trigger or tag-based
- **Database backup**: Pre-migration backup trigger

### 4.10 Files to Create/Modify

| Action | File |
|---|---|
| CREATE | `docker-compose.prod.yml` |
| CREATE | `docker-compose.clerk.yml` |
| CREATE | `Caddyfile` |
| CREATE | `breakthevibe/web/health.py` (enhanced health check) |
| MODIFY | `breakthevibe/config/settings.py` (allowed_origins, environment, s3) |
| MODIFY | `breakthevibe/web/app.py` (dynamic CORS) |
| MODIFY | `breakthevibe/web/middleware.py` (security headers middleware) |
| MODIFY | `docker-compose.yml` (add profiles, resource limits) |
| MODIFY | `.github/workflows/ci.yml` (staging deploy, migration check) |
| MODIFY | `pyproject.toml` (sentry-sdk, prometheus deps) |

---

## Phase 5: Audit Logging & Compliance

> **Detailed Plan**: [phases/phase-5-audit-logging.md](phases/phase-5-audit-logging.md)

### Goal
Record all significant actions for SOC 2 compliance and GDPR accountability.

### 5.1 Audit Log Model

```python
class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str | None = Field(default=None, foreign_key="users.id")
    action: str = Field(index=True)        # e.g., "project.created", "pipeline.started"
    resource_type: str                      # "project", "test_run", "settings"
    resource_id: str | None = None
    details_json: str | None = None        # Additional context as JSON
    ip_address: str | None = None
    request_id: str | None = None          # Correlation with RequestIDMiddleware
    created_at: datetime = Field(default_factory=_utc_now)
```

**Index**: `(org_id, created_at DESC)` for efficient audit queries.

### 5.2 Audit Logger Service

**New file: `breakthevibe/audit/logger.py`**

```python
class AuditLogger:
    """Records audit events to the audit_logs table."""

    async def log(
        self,
        org_id: str,
        user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Insert an audit log entry."""
        ...
```

### 5.3 Events to Audit

| Action | Resource Type | Trigger Point |
|---|---|---|
| `auth.login` | session | Login route |
| `auth.logout` | session | Logout route |
| `auth.failed` | session | Login route (failed) |
| `project.created` | project | POST /api/projects |
| `project.deleted` | project | DELETE /api/projects/{id} |
| `project.updated` | project | PUT /api/projects/{id} |
| `pipeline.started` | pipeline | POST /api/projects/{id}/crawl |
| `pipeline.completed` | pipeline | run_pipeline() completion |
| `pipeline.failed` | pipeline | run_pipeline() error |
| `settings.llm_updated` | settings | PUT /api/settings/llm |
| `rules.updated` | rules | PUT /api/projects/{id}/rules |
| `member.invited` | membership | Clerk webhook |
| `member.removed` | membership | Clerk webhook |
| `member.role_changed` | membership | Clerk webhook |
| `org.plan_changed` | subscription | Billing webhook (future) |
| `data.export_requested` | gdpr | Export endpoint (future) |
| `data.deletion_requested` | gdpr | Erasure endpoint |

### 5.4 Audit Query API

```
GET /api/audit-logs?page=1&limit=50&action=pipeline.started&from=2026-01-01
```
- Requires admin role
- Filtered by org_id (tenant scoped)
- Paginated, sorted by `created_at DESC`

### 5.5 Files to Create/Modify

| Action | File |
|---|---|
| CREATE | `breakthevibe/audit/__init__.py` |
| CREATE | `breakthevibe/audit/logger.py` |
| CREATE | `breakthevibe/web/routes/audit.py` |
| CREATE | migration: `add_audit_logs_table.py` |
| MODIFY | `breakthevibe/models/database.py` (AuditLog model) |
| MODIFY | Route files (add audit logging calls) |
| MODIFY | `breakthevibe/web/auth/webhook.py` (audit membership events) |
| MODIFY | `breakthevibe/web/dependencies.py` (audit pipeline events) |

---

## Phase 6: Pipeline Isolation & Job Queue

> **Detailed Plan**: [phases/phase-6-pipeline-job-queue.md](phases/phase-6-pipeline-job-queue.md)

### Goal
Replace FastAPI `BackgroundTasks` with a persistent, tenant-aware job queue to prevent noisy neighbors and survive restarts.

### 6.1 Why Replace BackgroundTasks?

| Problem | Impact |
|---|---|
| No persistence | Jobs lost on restart |
| No concurrency control | One tenant's 10 crawls consume all resources |
| No retry on crash | Failed pipelines require manual re-trigger |
| In-process execution | Blocks the event loop under heavy load |
| No visibility | No way to list running/pending jobs |

### 6.2 PipelineJob Model

```python
class PipelineJob(SQLModel, table=True):
    __tablename__ = "pipeline_jobs"

    id: str = Field(default_factory=_new_uuid, primary_key=True,
                    sa_column=Column(String(36)))
    org_id: str = Field(foreign_key="organizations.id", index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending", index=True)
                         # pending | running | completed | failed | canceled
    url: str
    rules_yaml: str = ""
    priority: int = Field(default=0)       # Higher = more urgent
    max_retries: int = Field(default=3)
    attempt: int = Field(default=0)
    worker_id: str | None = None           # Claim token for distributed locking
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    result_json: str | None = None         # Pipeline result cached as JSON
    created_at: datetime = Field(default_factory=_utc_now)
```

### 6.3 Job Queue Architecture

**Simple PostgreSQL-based queue** using `SELECT ... FOR UPDATE SKIP LOCKED`:

```python
class JobQueue:
    """PostgreSQL-backed job queue with per-tenant concurrency limits."""

    async def enqueue(self, org_id: str, project_id: int, url: str,
                      rules_yaml: str = "") -> PipelineJob:
        """Create a new pipeline job."""
        ...

    async def claim_next(self, worker_id: str) -> PipelineJob | None:
        """Claim the next available job, respecting per-tenant limits."""
        # SELECT j.* FROM pipeline_jobs j
        # JOIN organizations o ON j.org_id = o.id
        # JOIN subscriptions s ON s.org_id = o.id
        # WHERE j.status = 'pending'
        # AND (SELECT COUNT(*) FROM pipeline_jobs
        #      WHERE org_id = j.org_id AND status = 'running')
        #     < PLAN_LIMITS[s.plan]['max_concurrent_pipelines']
        # ORDER BY j.priority DESC, j.created_at ASC
        # LIMIT 1
        # FOR UPDATE SKIP LOCKED
        ...

    async def complete(self, job_id: str, result: dict) -> None: ...
    async def fail(self, job_id: str, error: str) -> None: ...
    async def cancel(self, job_id: str) -> None: ...
```

### 6.4 Job Worker

**New file: `breakthevibe/worker/runner.py`**

```python
class JobWorker:
    """Polls the job queue and executes pipeline jobs."""

    def __init__(self, queue: JobQueue, poll_interval: float = 2.0):
        self._queue = queue
        self._poll_interval = poll_interval
        self._worker_id = str(uuid.uuid4())

    async def run_forever(self) -> None:
        """Main loop: claim and execute jobs."""
        while True:
            job = await self._queue.claim_next(self._worker_id)
            if job:
                await self._execute(job)
            else:
                await asyncio.sleep(self._poll_interval)

    async def _execute(self, job: PipelineJob) -> None:
        """Run a single pipeline job."""
        try:
            orchestrator = build_pipeline(
                project_id=str(job.project_id),
                url=job.url,
                rules_yaml=job.rules_yaml,
            )
            result = await orchestrator.run(
                project_id=str(job.project_id),
                url=job.url,
                rules_yaml=job.rules_yaml,
            )
            await self._queue.complete(job.id, result_to_dict(result))
        except Exception as e:
            await self._queue.fail(job.id, str(e))
```

### 6.5 Route Changes

```python
# crawl.py — BEFORE
background_tasks.add_task(run_pipeline, ...)

# crawl.py — AFTER
job = await job_queue.enqueue(
    org_id=tenant.org_id,
    project_id=project_id,
    url=url,
    rules_yaml=rules_yaml,
)
return {"status": "accepted", "job_id": job.id}
```

### 6.6 Job Status API

```
GET /api/jobs                          # List jobs for this tenant
GET /api/jobs/{job_id}                 # Job status + result
DELETE /api/jobs/{job_id}              # Cancel pending job
```

### 6.7 Files to Create/Modify

| Action | File |
|---|---|
| CREATE | `breakthevibe/worker/__init__.py` |
| CREATE | `breakthevibe/worker/queue.py` (JobQueue) |
| CREATE | `breakthevibe/worker/runner.py` (JobWorker) |
| CREATE | `breakthevibe/web/routes/jobs.py` (job status API) |
| CREATE | migration: `add_pipeline_jobs_table.py` |
| MODIFY | `breakthevibe/models/database.py` (PipelineJob model) |
| MODIFY | `breakthevibe/web/routes/crawl.py` (enqueue instead of BackgroundTask) |
| MODIFY | `breakthevibe/web/routes/tests.py` (same) |
| MODIFY | `docker-compose.yml` (add worker service) |

---

## Phase 7: Object Storage (S3/R2)

> **Detailed Plan**: [phases/phase-7-object-storage-s3-r2.md](phases/phase-7-object-storage-s3-r2.md)

### Goal
Replace local filesystem artifact storage with S3/R2-compatible object storage, with local filesystem as a fallback for development.

### 7.1 Storage Adapter Interface

**New file: `breakthevibe/storage/object_store.py`**

```python
from abc import ABC, abstractmethod

class ObjectStore(ABC):
    """Abstract interface for binary artifact storage."""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "") -> str:
        """Store an object, return its URL/path."""
        ...

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Retrieve an object by key."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def list_keys(self, prefix: str) -> list[str]: ...

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects with the given prefix. Returns count deleted."""
        ...

    @abstractmethod
    async def get_usage_bytes(self, prefix: str) -> int: ...
```

### 7.2 S3 Implementation

**New file: `breakthevibe/storage/s3_store.py`**

```python
class S3ObjectStore(ObjectStore):
    """S3/R2-compatible object storage using aiobotocore."""

    def __init__(self, bucket: str, endpoint_url: str | None = None,
                 access_key_id: str = "", secret_access_key: str = "",
                 region: str = "auto"):
        ...

    def _tenant_key(self, org_id: str, project_id: str,
                    run_id: str, filename: str) -> str:
        """Build tenant-scoped object key."""
        return f"tenants/{org_id}/projects/{project_id}/runs/{run_id}/{filename}"
```

Key prefix structure:
```
tenants/{org_id}/projects/{project_id}/runs/{run_id}/
  screenshots/step_name.png
  videos/video_name.webm
  diffs/diff_name.png
  tests/test_output.py
```

### 7.3 Local Filesystem Implementation

```python
class LocalObjectStore(ObjectStore):
    """Local filesystem adapter using the existing ArtifactStore paths."""
    ...
```

### 7.4 Factory

```python
def create_object_store() -> ObjectStore:
    settings = get_settings()
    if settings.use_s3:
        return S3ObjectStore(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
        )
    return LocalObjectStore(base_dir=Path(settings.artifacts_dir).expanduser())
```

### 7.5 ArtifactStore Refactor

The existing `ArtifactStore` is refactored to use `ObjectStore` as its backend:

```python
class ArtifactStore:
    def __init__(self, store: ObjectStore, org_id: str):
        self._store = store
        self._org_id = org_id

    async def save_screenshot(self, project_id: str, run_id: str,
                              step_name: str, data: bytes) -> str:
        key = f"tenants/{self._org_id}/projects/{project_id}/runs/{run_id}/screenshots/{step_name}.png"
        return await self._store.put(key, data, content_type="image/png")
```

### 7.6 Dependencies

Add `aiobotocore>=2.13.0` (async S3 client).

### 7.7 Files to Create/Modify

| Action | File |
|---|---|
| CREATE | `breakthevibe/storage/object_store.py` (abstract interface) |
| CREATE | `breakthevibe/storage/s3_store.py` (S3/R2 implementation) |
| CREATE | `breakthevibe/storage/local_store.py` (local filesystem adapter) |
| MODIFY | `breakthevibe/storage/artifacts.py` (use ObjectStore backend) |
| MODIFY | `breakthevibe/config/settings.py` (S3 settings) |
| MODIFY | `breakthevibe/web/pipeline.py` (pass org_id to ArtifactStore) |
| MODIFY | `pyproject.toml` (aiobotocore dep) |

---

## Edge Cases & Configuration Review

> **Detailed Plan**: [phases/edge-cases-and-configuration-review.md](phases/edge-cases-and-configuration-review.md)

A thorough review of all 7 phases identified **7 Critical, 8 High, 11 Medium, and 12 Low** findings. Key issues:

| # | Severity | Issue | Phase |
|---|---|---|---|
| C-1 | Critical | Cross-tenant data leak in `pipeline_results` cache | 1 |
| C-2 | Critical | `results.py` missing from route refactor | 1 |
| C-4 | Critical | Webhook concurrent retries cause `IntegrityError` | 2 |
| C-5 | Critical | Usage increment TOCTOU race condition | 3 |
| C-7 | Critical | `LocalObjectStore` path traversal vulnerability | 7 |
| H-2 | High | `_persist_test_run` missing `org_id` | 1 |
| H-3 | High | Orchestrator `CrawlRun` missing `org_id` | 1 |
| H-6 | High | Single-tenant users hit free-tier limits | 1+3 |

All findings have specific fixes documented in the review. Each phase's implementation should address relevant findings before merging.

---

## Migration Strategy

### Database Migration Order

All migrations are sequential, each depending on the previous:

```
2fbda022df84  (existing) initial_tables
       │
       ▼
a1b2c3d4e5f6  add_tenancy_tables (organizations, users, memberships)
       │
       ▼
b2c3d4e5f6a7  add_org_id_to_data_tables (org_id on all 7 tables + backfill)
       │
       ▼
c3d4e5f6a7b8  add_subscription_and_usage_tables
       │
       ▼
d4e5f6a7b8c9  add_audit_logs_table
       │
       ▼
e5f6a7b8c9d0  add_pipeline_jobs_table
```

### Zero-Downtime Migration Rules

1. **Never rename columns** — add new, migrate data, drop old
2. **Add nullable columns first** — then backfill, then add NOT NULL
3. **Never drop tables in the same deploy** — wait for code to stop referencing them
4. **Test migrations against production-size data** — backfill of org_id on large tables
5. **Add `statement_timeout` to long migrations** to prevent lock contention

### Rollback Strategy

Each migration has a `downgrade()` function. In case of issues:
```bash
alembic downgrade -1  # Rollback one migration
```

---

## Testing Strategy

### Unit Tests

| Area | Tests |
|---|---|
| TenantContext | Role checks (is_admin, is_at_least_member, is_viewer) |
| RBAC deps | require_viewer allows all, require_member rejects viewer, require_admin rejects member |
| TenantScopedSession | org_id is carried through |
| Usage enforcement | check() raises 429 at limit, passes under limit |
| Plan limits | Correct limits per tier |
| Audit logger | Correct event format and DB insertion |

### Integration Tests

| Test | Description |
|---|---|
| Tenant isolation | Tenant A creates project, Tenant B cannot read/list/delete it |
| Cross-tenant guard | Direct ID access to another tenant's resource returns 404 |
| Clerk JWT validation | Valid/expired/invalid tokens produce correct responses |
| Webhook processing | user.created/organization.created/membership events create correct DB rows |
| GDPR erasure | user.deleted anonymizes PII, org.deleted deactivates access |
| Usage limits | Creating projects beyond limit returns 429 |
| Job queue | Enqueue, claim, complete, fail lifecycle |
| Job concurrency | Tenant at concurrency limit cannot start new pipeline |
| S3 artifacts | Upload, download, list, delete, prefix deletion |

### End-to-End Tests

| Test | Description |
|---|---|
| Full pipeline multi-tenant | Two tenants run pipelines concurrently, results are isolated |
| Plan upgrade | Free tenant hits limit, upgrades to starter, can create more |
| Audit trail | Admin queries audit logs and sees all team activity |

---

## Implementation Sequence & Dependencies

### Dependency Graph

```
Phase 1 (Foundation)
  ├── Phase 2 (Clerk Auth)     ← depends on Phase 1
  │     └── Phase 5 (Audit)    ← depends on Phase 2 for user context
  ├── Phase 3 (Billing)        ← depends on Phase 1
  ├── Phase 4 (Infra)          ← independent, can start anytime
  ├── Phase 6 (Job Queue)      ← depends on Phase 1 + 3 (plan limits)
  └── Phase 7 (S3)             ← depends on Phase 1 (org_id in paths)
```

### Recommended Implementation Order

```
Week 1:  Phase 1 (Multi-tenancy foundation) + Phase 4 (Infra basics)
Week 2:  Phase 2 (Clerk integration)
Week 3:  Phase 3 (Billing/limits) + Phase 5 (Audit logging)
Week 4:  Phase 6 (Job queue) + Phase 7 (S3/R2)
Week 5:  Integration testing, end-to-end validation, staging deploy
```

### Phase Implementation Checklist

#### Phase 1: Multi-Tenancy Foundation
- [ ] Create TenantContext dataclass
- [ ] Create TenantScopedSession wrapper
- [ ] Create single-tenant auth shim
- [ ] Create RBAC dependency functions
- [ ] Update Settings with auth_mode and tenant fields
- [ ] Add Organization, User, OrganizationMembership models
- [ ] Add org_id to all 7 existing table models
- [ ] Write migration: tenancy tables
- [ ] Write migration: org_id backfill on data tables
- [ ] Update migrations/env.py with new model imports
- [ ] Refactor DatabaseProjectRepository for TenantScopedSession
- [ ] Refactor LlmSettingsRepository for TenantScopedSession
- [ ] Rewrite dependencies.py with Depends factories
- [ ] Create InMemoryProjectRepository (tenant-partitioned)
- [ ] Refactor all 7 route files to use Depends + RBAC
- [ ] Update app.py (remove global auth, add webhook router condition)
- [ ] Update pipeline_results cache key to include org_id
- [ ] Run all existing tests — verify backward compatibility
- [ ] Write tenant isolation integration test

#### Phase 2: Clerk Authentication
- [ ] Add PyJWT and cryptography to pyproject.toml
- [ ] Create clerk.py (JWKS fetch, JWT decode, resolve_tenant_context)
- [ ] Create webhook.py (Svix verification, 9 event handlers)
- [ ] Add Clerk env vars to settings.py with validation
- [ ] Mount webhook router in app.py (conditional on auth_mode)
- [ ] Test with Clerk dev credentials and ngrok
- [ ] Test GDPR: user.deleted anonymizes PII
- [ ] Test: organization.deleted blocks access immediately
- [ ] Write unit tests for JWT validation edge cases

#### Phase 3: Billing & Usage Limits
- [ ] Create PLAN_LIMITS configuration
- [ ] Add Subscription and UsageRecord models
- [ ] Write migration: subscription and usage tables
- [ ] Create UsageEnforcer service
- [ ] Add usage checks to project creation, crawl, test run routes
- [ ] Add usage increment after successful operations
- [ ] Write per-tenant rate limit middleware
- [ ] Seed free subscription for all existing orgs (migration)
- [ ] Write tests for limit enforcement at each tier boundary

#### Phase 4: Infrastructure & Operations
- [ ] Make CORS origins configurable from settings
- [ ] Create docker-compose.prod.yml with Caddy
- [ ] Add security headers middleware
- [ ] Create enhanced health check endpoint
- [ ] Add Sentry error tracking (optional)
- [ ] Add Prometheus metrics (optional)
- [ ] Update CI for migration safety checks
- [ ] Write .env.example with all new variables

#### Phase 5: Audit Logging & Compliance
- [ ] Add AuditLog model
- [ ] Write migration: audit_logs table
- [ ] Create AuditLogger service
- [ ] Add audit logging to all route handlers
- [ ] Add audit logging to webhook handlers
- [ ] Add audit logging to pipeline completion/failure
- [ ] Create GET /api/audit-logs endpoint (admin only)
- [ ] Write tests for audit event coverage

#### Phase 6: Pipeline Isolation & Job Queue
- [ ] Add PipelineJob model
- [ ] Write migration: pipeline_jobs table
- [ ] Create JobQueue with SKIP LOCKED claiming
- [ ] Create JobWorker poll loop
- [ ] Replace BackgroundTasks with queue.enqueue() in routes
- [ ] Create job status API routes
- [ ] Add worker service to docker-compose
- [ ] Test per-tenant concurrency limits
- [ ] Test job survival across worker restart

#### Phase 7: Object Storage (S3/R2)
- [ ] Create ObjectStore abstract interface
- [ ] Create S3ObjectStore implementation (aiobotocore)
- [ ] Create LocalObjectStore implementation
- [ ] Create factory function (use_s3 flag)
- [ ] Refactor ArtifactStore to use ObjectStore backend
- [ ] Add tenant prefix to all object keys
- [ ] Add S3 settings to config
- [ ] Add aiobotocore to pyproject.toml
- [ ] Test upload/download/delete/list with MinIO (local S3)
- [ ] Test with Cloudflare R2

---

## GDPR & SOC 2 Compliance Summary

### GDPR Requirements Met

| Requirement | Implementation |
|---|---|
| Right to erasure | `user.deleted` webhook anonymizes PII; tenant purge deletes all data |
| Data minimization | Only sync email, name, avatar from Clerk; no extra PII |
| Purpose limitation | org_id scoping ensures data used only for tenant's QA work |
| Data portability | Future: export API endpoint |
| Consent | Managed by Clerk during signup |
| Breach notification | Audit logs + Sentry alerts for anomalies |

### SOC 2 Controls

| Control | Implementation |
|---|---|
| Access control | RBAC (admin/member/viewer) enforced per route |
| Audit logging | All CRUD, auth, and pipeline events logged |
| Data isolation | org_id on all queries, TenantScopedSession enforces at ORM boundary |
| Encryption in transit | TLS via Caddy reverse proxy |
| Encryption at rest | PostgreSQL volume encryption (cloud provider), S3 server-side encryption |
| Session management | 24h expiry, HMAC-signed tokens (single-tenant) / RS256 JWT (Clerk) |
| Secret management | All secrets via env vars, never in code or DB (except LLM keys in DB, encrypted future) |

### Tenant Data Purge Workflow

For GDPR right to erasure at the organization level:

```python
async def purge_tenant(org_id: str) -> dict:
    """Delete ALL data for a tenant. Irreversible."""
    # 1. Delete test_results (FK to test_runs, test_cases)
    # 2. Delete test_runs (FK to projects)
    # 3. Delete test_cases (FK to projects)
    # 4. Delete routes (FK to crawl_runs)
    # 5. Delete crawl_runs (FK to projects)
    # 6. Delete pipeline_jobs
    # 7. Delete projects
    # 8. Delete llm_settings
    # 9. Delete usage_records
    # 10. Delete subscriptions
    # 11. Delete audit_logs (after retention period)
    # 12. Delete organization_memberships
    # 13. Anonymize users (if not in other orgs)
    # 14. Delete artifacts from S3 (prefix: tenants/{org_id}/)
    # 15. Soft-delete organization (set deleted_at, is_active=false)
    # 16. Log audit event: "data.purge_completed"
    return {"deleted_tables": 14, "artifacts_deleted": artifact_count}
```

---

## New Dependencies Summary

| Package | Version | Purpose | Phase |
|---|---|---|---|
| `PyJWT` | >=2.8.0 | Clerk JWT RS256 verification | 2 |
| `cryptography` | >=43.0.0 | RSA key parsing for PyJWT | 2 |
| `aiobotocore` | >=2.13.0 | Async S3/R2 client | 7 |
| `sentry-sdk[fastapi]` | >=2.0.0 | Error tracking (optional) | 4 |
| `prometheus-fastapi-instrumentator` | >=7.0.0 | Metrics (optional) | 4 |

---

## Configuration Reference

### All New Environment Variables

| Variable | Default | Phase | Required |
|---|---|---|---|
| `AUTH_MODE` | `single` | 1 | No (backward compat) |
| `SINGLE_TENANT_ORG_ID` | `00000000-...-0001` | 1 | No |
| `CLERK_SECRET_KEY` | None | 2 | When AUTH_MODE=clerk |
| `CLERK_PUBLISHABLE_KEY` | None | 2 | When AUTH_MODE=clerk |
| `CLERK_WEBHOOK_SECRET` | None | 2 | When AUTH_MODE=clerk |
| `CLERK_ISSUER` | None | 2 | When AUTH_MODE=clerk |
| `CLERK_AUDIENCE` | None | 2 | When AUTH_MODE=clerk |
| `CLERK_JWKS_URL` | None | 2 | When AUTH_MODE=clerk |
| `ENVIRONMENT` | `development` | 4 | No |
| `ALLOWED_ORIGINS` | `["http://localhost:8000"]` | 4 | No |
| `USE_S3` | `false` | 7 | No |
| `S3_BUCKET` | None | 7 | When USE_S3=true |
| `S3_ENDPOINT_URL` | None | 7 | For R2/MinIO |
| `S3_ACCESS_KEY_ID` | None | 7 | When USE_S3=true |
| `S3_SECRET_ACCESS_KEY` | None | 7 | When USE_S3=true |
| `S3_REGION` | `auto` | 7 | No |
| `STRIPE_SECRET_KEY` | None | 3 (future) | When billing enabled |
| `STRIPE_WEBHOOK_SECRET` | None | 3 (future) | When billing enabled |
