"""SQLModel database table models."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    url: str
    config_yaml: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class CrawlRun(SQLModel, table=True):
    __tablename__ = "crawl_runs"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    site_map_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class Route(SQLModel, table=True):
    __tablename__ = "routes"

    id: int | None = Field(default=None, primary_key=True)
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


class LlmSetting(SQLModel, table=True):
    __tablename__ = "llm_settings"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value_json: str
    updated_at: datetime = Field(default_factory=_utc_now)
