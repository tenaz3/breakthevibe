"""SQLModel database table models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from breakthevibe.config.settings import SENTINEL_ORG_ID


def _utc_now() -> datetime:
    """Return current UTC time as naive datetime for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Multi-tenant models
# ---------------------------------------------------------------------------


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    clerk_org_id: str | None = Field(default=None, unique=True)
    name: str
    plan: str = Field(default="free")
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    clerk_user_id: str | None = Field(default=None, unique=True)
    email: str = Field(index=True)
    name: str = ""
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class OrganizationMembership(SQLModel, table=True):
    __tablename__ = "organization_memberships"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    role: str = Field(default="member")  # admin | member | viewer
    created_at: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Existing data models (now with org_id for multi-tenancy)
# ---------------------------------------------------------------------------


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
    name: str = Field(index=True)
    url: str
    config_yaml: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class CrawlRun(SQLModel, table=True):
    __tablename__ = "crawl_runs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    site_map_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class Route(SQLModel, table=True):
    __tablename__ = "routes"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
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
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    name: str
    category: str  # functional | visual | api
    route_path: str
    steps_json: str | None = None
    code: str | None = None
    selectors_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class TestRun(SQLModel, table=True):
    __tablename__ = "test_runs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
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
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
    test_run_id: int = Field(foreign_key="test_runs.id", index=True)
    test_case_id: int = Field(foreign_key="test_cases.id", index=True)
    status: str  # passed | failed | healed | skipped
    duration_ms: int | None = None
    error_message: str | None = None
    steps_log_json: str | None = None
    screenshot_paths_json: str | None = None
    video_path: str | None = None
    network_log_json: str | None = None
    console_log_json: str | None = None
    healed_selectors_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Billing models
# ---------------------------------------------------------------------------


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", unique=True, index=True)
    plan: str = Field(default="free")  # free | starter | pro
    status: str = Field(default="active")  # active | canceled | past_due
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class UsageRecord(SQLModel, table=True):
    __tablename__ = "usage_records"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(index=True)
    metric: str = Field(index=True)  # projects | crawls | test_runs | storage_bytes
    period: str  # YYYY-MM format
    count: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Pipeline job queue
# ---------------------------------------------------------------------------


class PipelineJob(SQLModel, table=True):
    __tablename__ = "pipeline_jobs"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    org_id: str = Field(index=True)
    project_id: str
    job_type: str = Field(default="full")  # full | crawl | generate | run
    status: str = Field(default="pending")  # pending | running | completed | failed | canceled
    url: str = ""
    rules_yaml: str = ""
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class LlmSetting(SQLModel, table=True):
    __tablename__ = "llm_settings"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(default=SENTINEL_ORG_ID, index=True)
    key: str = Field(index=True, unique=True)
    value_json: str
    updated_at: datetime = Field(default_factory=_utc_now)
