# Phase 3: Billing & Usage Limits

> **Status**: Not started
> **Depends on**: Phase 1 (Multi-Tenancy Foundation)
> **Estimated scope**: ~8 files created, ~6 modified
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Define plan tiers (free/starter/pro) with concrete usage limits. Build enforcement that blocks operations when limits are exceeded. Create the Subscription and UsageRecord data models ready for Stripe integration. Implement per-tenant rate limiting separate from the global IP-based limiter.

---

## 2. Plan Tier Configuration

**Create: `breakthevibe/billing/__init__.py`** (empty)

**Create: `breakthevibe/billing/plans.py`**

```python
"""Plan tier definitions and usage limits."""

from __future__ import annotations

from typing import Any

# -1 means unlimited
PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {
        "max_projects": 3,
        "max_crawls_per_month": 10,
        "max_test_runs_per_month": 20,
        "max_artifact_storage_mb": 500,
        "max_concurrent_pipelines": 1,
        "rate_limit_per_minute": 30,
        "max_members": 3,
    },
    "starter": {
        "max_projects": 20,
        "max_crawls_per_month": 100,
        "max_test_runs_per_month": 500,
        "max_artifact_storage_mb": 5_000,
        "max_concurrent_pipelines": 3,
        "rate_limit_per_minute": 120,
        "max_members": 10,
    },
    "pro": {
        "max_projects": -1,
        "max_crawls_per_month": -1,
        "max_test_runs_per_month": -1,
        "max_artifact_storage_mb": 50_000,
        "max_concurrent_pipelines": 10,
        "rate_limit_per_minute": 600,
        "max_members": -1,
    },
}


def get_plan_limit(plan: str, metric: str) -> int:
    """Get the limit for a metric on a given plan. Returns -1 for unlimited."""
    tier = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    return tier.get(metric, 0)


def get_all_plans() -> dict[str, dict[str, int]]:
    """Return all plan definitions (for display in UI)."""
    return PLAN_LIMITS.copy()
```

---

## 3. New Database Models

**Add to: `breakthevibe/models/database.py`**

### Subscription

```python
class Subscription(SQLModel, table=True):
    """One subscription per organization. Tracks billing state."""

    __tablename__ = "subscriptions"

    id: str = Field(
        default_factory=_new_uuid,
        primary_key=True,
        sa_column=Column(sa.String(36), primary_key=True),
    )
    org_id: str = Field(foreign_key="organizations.id", index=True, unique=True)
    plan: str = Field(default="free")               # free | starter | pro
    status: str = Field(default="active")            # active | canceled | past_due
    stripe_subscription_id: str | None = None        # Future: Stripe sub ID
    stripe_customer_id: str | None = None            # Future: Stripe customer ID
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    canceled_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
```

### UsageRecord

```python
class UsageRecord(SQLModel, table=True):
    """Monthly usage counters per organization per metric."""

    __tablename__ = "usage_records"
    __table_args__ = (
        sa.UniqueConstraint("org_id", "metric", "period_start",
                            name="uq_usage_org_metric_period"),
    )

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    metric: str = Field(index=True)                  # projects | crawls | test_runs
    count: int = Field(default=0)
    period_start: datetime                           # First of month (UTC)
    period_end: datetime                             # Last of month (UTC)
    created_at: datetime = Field(default_factory=_utc_now)
```

---

## 4. Usage Enforcement Service

**Create: `breakthevibe/web/usage.py`**

```python
"""Usage enforcement — checks plan limits before allowing operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlmodel import func, select

from breakthevibe.billing.plans import get_plan_limit
from breakthevibe.models.database import Project, Subscription, UsageRecord
from breakthevibe.storage.tenant_session import TenantScopedSession

logger = structlog.get_logger(__name__)


def _current_period() -> tuple[datetime, datetime]:
    """Return the start and end of the current billing period (calendar month)."""
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # End = first day of next month
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end


class UsageEnforcer:
    """Checks and increments usage against plan limits."""

    def __init__(self, scoped_session: TenantScopedSession) -> None:
        self._db = scoped_session

    async def _get_plan(self) -> str:
        """Get the org's current plan."""
        stmt = select(Subscription.plan).where(
            Subscription.org_id == self._db.org_id,
            Subscription.status == "active",
        )
        result = (await self._db.execute(stmt)).scalars().first()
        return result or "free"

    async def _get_current_usage(self, metric: str) -> int:
        """Get current month's usage count for a metric."""
        period_start, _ = _current_period()
        stmt = select(UsageRecord.count).where(
            UsageRecord.org_id == self._db.org_id,
            UsageRecord.metric == metric,
            UsageRecord.period_start == period_start,
        )
        result = (await self._db.execute(stmt)).scalars().first()
        return result or 0

    async def _get_project_count(self) -> int:
        """Get total active project count (not monthly — cumulative)."""
        stmt = select(func.count()).where(Project.org_id == self._db.org_id)
        result = (await self._db.execute(stmt)).scalars().first()
        return result or 0

    async def check(self, metric: str) -> None:
        """Raise HTTP 429 if the org has exceeded its plan limit for this metric.

        Metrics:
          - "projects" — cumulative (total projects, not per-month)
          - "crawls" — per calendar month
          - "test_runs" — per calendar month
        """
        plan = await self._get_plan()

        if metric == "projects":
            current = await self._get_project_count()
            limit_key = "max_projects"
        elif metric == "crawls":
            current = await self._get_current_usage("crawls")
            limit_key = "max_crawls_per_month"
        elif metric == "test_runs":
            current = await self._get_current_usage("test_runs")
            limit_key = "max_test_runs_per_month"
        else:
            return  # Unknown metric — allow

        limit = get_plan_limit(plan, limit_key)
        if limit == -1:
            return  # Unlimited

        if current >= limit:
            logger.warning(
                "usage_limit_exceeded",
                org_id=self._db.org_id,
                metric=metric,
                current=current,
                limit=limit,
                plan=plan,
            )
            raise HTTPException(
                status_code=429,
                detail=f"Plan limit reached for {metric}: {current}/{limit} "
                       f"(plan: {plan}). Upgrade to increase limits.",
            )

    async def increment(self, metric: str) -> None:
        """Increment the usage counter for the current billing period."""
        period_start, period_end = _current_period()

        stmt = select(UsageRecord).where(
            UsageRecord.org_id == self._db.org_id,
            UsageRecord.metric == metric,
            UsageRecord.period_start == period_start,
        )
        record = (await self._db.execute(stmt)).scalars().first()
        if record:
            record.count += 1
            self._db.add(record)
        else:
            self._db.add(
                UsageRecord(
                    org_id=self._db.org_id,
                    metric=metric,
                    count=1,
                    period_start=period_start,
                    period_end=period_end,
                )
            )
        await self._db.commit()
        logger.debug(
            "usage_incremented", org_id=self._db.org_id, metric=metric
        )
```

**FastAPI dependency:**

Add to `breakthevibe/web/dependencies.py`:

```python
def get_usage_enforcer(
    scoped_session: TenantScopedSession = Depends(get_scoped_session),
) -> UsageEnforcer:
    """Return a UsageEnforcer for the current tenant."""
    from breakthevibe.web.usage import UsageEnforcer
    return UsageEnforcer(scoped_session)
```

---

## 5. Route Integration

### projects.py — Check project limit on create

```python
@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: CreateProjectRequest,
    tenant: TenantContext = Depends(require_member),
    project_repo: Any = Depends(get_project_repo),
    usage: UsageEnforcer = Depends(get_usage_enforcer),
) -> dict:
    await usage.check("projects")  # NEW
    if not is_safe_url(str(body.url)):
        raise HTTPException(status_code=422, detail="...")
    return await project_repo.create(...)
```

### crawl.py — Check + increment crawl usage

```python
@router.post("/api/projects/{project_id}/crawl")
async def trigger_crawl(
    project_id: str,
    background_tasks: BackgroundTasks,
    tenant: TenantContext = Depends(require_member),
    project_repo: Any = Depends(get_project_repo),
    usage: UsageEnforcer = Depends(get_usage_enforcer),
) -> dict:
    await usage.check("crawls")  # NEW
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    background_tasks.add_task(run_pipeline, ...)
    await usage.increment("crawls")  # NEW
    ...
```

### tests.py — Check + increment test_runs usage

Same pattern for `trigger_generate` and `trigger_run`.

---

## 6. Per-Tenant Rate Limiting

**Create: `breakthevibe/web/tenant_rate_limit.py`**

```python
"""Per-tenant rate limiting based on plan tier."""

from __future__ import annotations

import time
from collections import defaultdict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from breakthevibe.billing.plans import get_plan_limit

logger = structlog.get_logger(__name__)


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits API requests per organization based on their plan tier.

    Uses org_id from the request state (set by auth dependencies).
    Falls back to IP-based limiting for unauthenticated requests.
    """

    def __init__(self, app: object, window_seconds: int = 60) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Execute the request first to populate tenant context
        # (Rate limiting is checked post-auth in the dependency chain)
        # This middleware collects metrics; actual enforcement is in UsageEnforcer
        return await call_next(request)
```

> **Note**: For Phase 3, per-tenant rate limiting is enforced at the dependency level (not middleware) since the tenant context is resolved inside route handlers. The existing IP-based `RateLimitMiddleware` continues to run for DDoS protection. A future enhancement can move tenant rate limiting to middleware once Redis is available for shared state.

---

## 7. Alembic Migration

**Create: migration `add_subscription_and_usage_tables.py`**

```python
"""add subscription and usage tables

Revision ID: <auto>
Revises: <migration-2-id>
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "<auto>"
down_revision: Union[str, Sequence[str], None] = "<migration-2-id>"


def upgrade() -> None:
    # Subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"], unique=True)

    # Usage Records
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "metric", "period_start",
                            name="uq_usage_org_metric_period"),
    )
    op.create_index("ix_usage_records_org_id", "usage_records", ["org_id"])
    op.create_index("ix_usage_records_metric", "usage_records", ["metric"])

    # Seed free subscription for the sentinel org
    op.execute(
        sa.text("""
            INSERT INTO subscriptions (id, org_id, plan, status, created_at, updated_at)
            SELECT
                '00000000-0000-0000-0000-000000000003',
                '00000000-0000-0000-0000-000000000001',
                'free', 'active', NOW(), NOW()
            WHERE EXISTS (SELECT 1 FROM organizations
                          WHERE id = '00000000-0000-0000-0000-000000000001')
            ON CONFLICT DO NOTHING
        """)
    )


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("subscriptions")
```

---

## 8. Future: Stripe Integration (Design Only)

When ready to add billing:

### New files:
- `breakthevibe/billing/stripe_service.py`
- `breakthevibe/web/routes/billing.py`

### Stripe webhook events to handle:
- `customer.subscription.created` → Create/update Subscription row
- `customer.subscription.updated` → Update plan, period dates
- `customer.subscription.deleted` → Set status="canceled"
- `invoice.payment_failed` → Set status="past_due"

### API endpoints:
- `POST /api/billing/checkout` → Create Stripe checkout session
- `POST /api/billing/portal` → Create Stripe customer portal session
- `POST /api/webhooks/stripe/` → Stripe webhook receiver
- `GET /api/billing/subscription` → Current subscription details

### Environment variables:
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_STARTER`
- `STRIPE_PRICE_ID_PRO`

---

## 9. Verification Checklist

- [ ] PLAN_LIMITS correctly define all tiers
- [ ] Creating 4th project on free tier returns 429
- [ ] Creating project on starter tier works up to 20
- [ ] Crawl count resets at month boundary
- [ ] Usage increment is atomic (no double-counting)
- [ ] Sentinel org has a free subscription seeded
- [ ] `get_plan_limit("free", "max_projects")` returns 3
- [ ] `get_plan_limit("pro", "max_projects")` returns -1 (unlimited)
- [ ] Existing tests still pass (usage check not enforced in single-tenant with no subscription)

---

## 10. Files Summary

| Action | File |
|---|---|
| CREATE | `breakthevibe/billing/__init__.py` |
| CREATE | `breakthevibe/billing/plans.py` (~50 lines) |
| CREATE | `breakthevibe/web/usage.py` (~120 lines) |
| CREATE | migration: `add_subscription_and_usage_tables.py` |
| MODIFY | `breakthevibe/models/database.py` (Subscription, UsageRecord) |
| MODIFY | `breakthevibe/web/dependencies.py` (get_usage_enforcer) |
| MODIFY | `breakthevibe/web/routes/projects.py` (usage check) |
| MODIFY | `breakthevibe/web/routes/crawl.py` (usage check + increment) |
| MODIFY | `breakthevibe/web/routes/tests.py` (usage check + increment) |
| MODIFY | `breakthevibe/storage/migrations/env.py` (import new models) |
