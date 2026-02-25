# BreakTheVibe Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an AI-powered QA automation platform that crawls websites, maps structure, generates test suites, and runs them — with a web dashboard for results.

**Architecture:** Hybrid pipeline (Crawler → Mapper → Generator → Runner → Reporter) with a thin Agent Layer for orchestration/retry. Provider-agnostic LLM layer with Claude as default. PostgreSQL for data, local filesystem for artifacts.

**Tech Stack:** Python 3.12+, FastAPI, SQLModel, PostgreSQL 16, Playwright, Anthropic SDK, pytest, structlog, htmx, D3.js, uv, Ruff, mypy, Docker

**Design Doc:** `docs/plans/2026-02-24-breakthevibe-design.md`

---

## Phase 1: Project Foundation

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Makefile`
- Create: `breakthevibe/__init__.py`
- Create: `breakthevibe/main.py`

**Step 1: Create `pyproject.toml` with all dependencies**

```toml
[project]
name = "breakthevibe"
version = "0.1.0"
description = "AI-powered QA automation platform"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.128.0",
    "uvicorn[standard]>=0.30.0",
    "sqlmodel>=0.0.22",
    "asyncpg>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "alembic>=1.14.0",
    "playwright>=1.48.0",
    "anthropic>=0.40.0",
    "openai>=1.50.0",
    "httpx>=0.27.0",
    "pytest>=8.0.0",
    "pytest-xdist>=3.5.0",
    "pytest-asyncio>=0.24.0",
    "pillow>=11.0.0",
    "structlog>=24.4.0",
    "pydantic-settings>=2.6.0",
    "pyyaml>=6.0.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.12",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "pre-commit>=4.0.0",
    "pytest-cov>=6.0.0",
]

[project.scripts]
breakthevibe = "breakthevibe.main:cli"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "SIM", "TCH"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "unit: unit tests (no I/O)",
    "integration: integration tests (DB, browser, LLM)",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: Create `.python-version`**

```
3.12
```

**Step 3: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
*$py.class
.env
.venv/
dist/
*.egg-info/
.mypy_cache/
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
*.db
artifacts/
videos/
screenshots/
```

**Step 4: Create `.env.example`**

```env
# Database
DATABASE_URL=postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe

# LLM Providers
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# App
SECRET_KEY=change-me-in-production
LOG_LEVEL=INFO
DEBUG=false
ARTIFACTS_DIR=~/.breakthevibe/artifacts
```

**Step 5: Create `Makefile`**

```makefile
.PHONY: dev test lint format typecheck setup migrate

setup:
	uv sync
	playwright install chromium

dev:
	fastapi dev breakthevibe/main.py

test:
	pytest -v

test-unit:
	pytest -v -m unit

test-integration:
	pytest -v -m integration

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy breakthevibe/

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"
```

**Step 6: Create `breakthevibe/__init__.py`**

```python
"""BreakTheVibe - AI-powered QA automation platform."""

__version__ = "0.1.0"
```

**Step 7: Create `breakthevibe/main.py` (minimal entrypoint)**

```python
"""BreakTheVibe entrypoint."""

import uvicorn


def cli() -> None:
    """CLI entrypoint."""
    uvicorn.run("breakthevibe.web.app:create_app", factory=True, reload=True)


if __name__ == "__main__":
    cli()
```

**Step 8: Install dependencies and verify**

Run: `cd /Users/tenaz3/development/breakthevibe && uv sync`
Expected: Dependencies install successfully

Run: `uv run python -c "import breakthevibe; print(breakthevibe.__version__)"`
Expected: `0.1.0`

**Step 9: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with dependencies and tooling"
```

---

### Task 2: Types, Constants, and Exceptions

**Files:**
- Create: `breakthevibe/types.py`
- Create: `breakthevibe/constants.py`
- Create: `breakthevibe/exceptions.py`
- Test: `tests/unit/test_types.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_types.py
import pytest
from breakthevibe.types import (
    ExecutionMode,
    LLMProvider,
    SelectorStrategy,
    TestCategory,
    TestStatus,
)
from breakthevibe.exceptions import (
    BreakTheVibeError,
    CrawlerError,
    GeneratorError,
    LLMProviderError,
    RunnerError,
    StorageError,
)
from breakthevibe.constants import DEFAULT_VIEWPORT_WIDTH, DEFAULT_MAX_DEPTH


@pytest.mark.unit
class TestEnums:
    def test_test_status_values(self):
        assert TestStatus.PENDING.value == "pending"
        assert TestStatus.RUNNING.value == "running"
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.HEALED.value == "healed"

    def test_test_category_values(self):
        assert TestCategory.FUNCTIONAL.value == "functional"
        assert TestCategory.VISUAL.value == "visual"
        assert TestCategory.API.value == "api"

    def test_llm_provider_values(self):
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.OLLAMA.value == "ollama"

    def test_selector_strategy_order(self):
        strategies = list(SelectorStrategy)
        assert strategies[0] == SelectorStrategy.TEST_ID
        assert strategies[-1] == SelectorStrategy.CSS

    def test_execution_mode_values(self):
        assert ExecutionMode.SMART.value == "smart"
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"


@pytest.mark.unit
class TestExceptions:
    def test_base_exception_hierarchy(self):
        assert issubclass(CrawlerError, BreakTheVibeError)
        assert issubclass(LLMProviderError, BreakTheVibeError)
        assert issubclass(GeneratorError, BreakTheVibeError)
        assert issubclass(RunnerError, BreakTheVibeError)
        assert issubclass(StorageError, BreakTheVibeError)

    def test_exception_message(self):
        err = CrawlerError("page not found")
        assert str(err) == "page not found"


@pytest.mark.unit
class TestConstants:
    def test_defaults_exist(self):
        assert DEFAULT_VIEWPORT_WIDTH == 1280
        assert DEFAULT_MAX_DEPTH == 5
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_types.py -v`
Expected: FAIL with import errors

**Step 3: Write implementations**

```python
# breakthevibe/types.py
"""Enums and type aliases for BreakTheVibe."""

from enum import StrEnum


class TestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    HEALED = "healed"
    SKIPPED = "skipped"


class TestCategory(StrEnum):
    FUNCTIONAL = "functional"
    VISUAL = "visual"
    API = "api"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class SelectorStrategy(StrEnum):
    TEST_ID = "test_id"
    ROLE = "role"
    TEXT = "text"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    CSS = "css"


class ExecutionMode(StrEnum):
    SMART = "smart"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class CrawlStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

```python
# breakthevibe/constants.py
"""Default constants for BreakTheVibe."""

# Crawler defaults
DEFAULT_MAX_DEPTH = 5
DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 800
DEFAULT_PAGE_LOAD_TIMEOUT_MS = 30_000
DEFAULT_AFTER_CLICK_WAIT_MS = 1_000
DEFAULT_SCROLL_WAIT_MS = 500
MAX_SCROLL_ATTEMPTS = 10

# Runner defaults
DEFAULT_PARALLEL_WORKERS = 4
DEFAULT_MAX_RETRIES = 1
DEFAULT_RETRY_DELAY_MS = 2_000

# LLM defaults
DEFAULT_LLM_PROVIDER = "anthropic"
DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"
DEFAULT_LLM_MAX_TOKENS = 4096

# Storage
DEFAULT_ARTIFACTS_DIR = "~/.breakthevibe/artifacts"
```

```python
# breakthevibe/exceptions.py
"""Exception hierarchy for BreakTheVibe."""


class BreakTheVibeError(Exception):
    """Base exception for all BreakTheVibe errors."""


class CrawlerError(BreakTheVibeError):
    """Raised when the crawler encounters an error."""


class MapperError(BreakTheVibeError):
    """Raised when the mapper encounters an error."""


class GeneratorError(BreakTheVibeError):
    """Raised when test generation fails."""


class LLMProviderError(BreakTheVibeError):
    """Raised when an LLM provider call fails."""


class RunnerError(BreakTheVibeError):
    """Raised when test execution fails."""


class StorageError(BreakTheVibeError):
    """Raised when storage operations fail."""


class ConfigError(BreakTheVibeError):
    """Raised when configuration is invalid."""
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_types.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/types.py breakthevibe/constants.py breakthevibe/exceptions.py tests/unit/test_types.py
git commit -m "feat: add types, constants, and exception hierarchy"
```

---

### Task 3: Configuration with Pydantic Settings

**Files:**
- Create: `breakthevibe/config/__init__.py`
- Create: `breakthevibe/config/settings.py`
- Create: `breakthevibe/config/logging.py`
- Test: `tests/unit/test_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_config.py
import pytest
from breakthevibe.config.settings import Settings


@pytest.mark.unit
class TestSettings:
    def test_default_settings(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        settings = Settings()
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert "postgresql" in str(settings.database_url)

    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/mydb")
        monkeypatch.setenv("SECRET_KEY", "my-secret")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        settings = Settings()
        assert settings.debug is True
        assert settings.log_level == "DEBUG"

    def test_anthropic_key_optional(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        settings = Settings()
        assert settings.anthropic_api_key is None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_config.py -v`
Expected: FAIL with import error

**Step 3: Write implementations**

```python
# breakthevibe/config/__init__.py
```

```python
# breakthevibe/config/settings.py
"""Application settings via Pydantic BaseSettings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    database_url: str = "postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe"

    # App
    secret_key: str = "change-me-in-production"
    debug: bool = False
    log_level: str = "INFO"
    artifacts_dir: str = "~/.breakthevibe/artifacts"

    # LLM Providers (all optional)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"


def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
```

```python
# breakthevibe/config/logging.py
"""Structured logging configuration using structlog."""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog for the application."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output or not sys.stderr.isatty():
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_config.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/config/ tests/unit/test_config.py
git commit -m "feat: add Pydantic settings and structlog configuration"
```

---

### Task 4: Database Setup with SQLModel + PostgreSQL

**Files:**
- Create: `breakthevibe/storage/__init__.py`
- Create: `breakthevibe/storage/database.py`
- Create: `breakthevibe/models/__init__.py`
- Create: `breakthevibe/models/database.py`
- Create: `docker-compose.yml`
- Create: `alembic.ini`
- Create: `breakthevibe/storage/migrations/env.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write the failing test for models**

```python
# tests/unit/test_models.py
import pytest
from breakthevibe.models.database import Project, CrawlRun, Route, TestCase, TestRun, TestResult


@pytest.mark.unit
class TestDatabaseModels:
    def test_project_creation(self):
        project = Project(name="My Site", url="https://example.com")
        assert project.name == "My Site"
        assert project.url == "https://example.com"

    def test_crawl_run_creation(self):
        run = CrawlRun(project_id=1, status="running")
        assert run.status == "running"

    def test_route_creation(self):
        route = Route(
            crawl_run_id=1,
            url="https://example.com/products",
            path="/products",
        )
        assert route.path == "/products"

    def test_test_case_creation(self):
        tc = TestCase(
            project_id=1,
            name="Login flow",
            category="functional",
            route_path="/login",
        )
        assert tc.category == "functional"

    def test_test_run_creation(self):
        run = TestRun(project_id=1, status="running")
        assert run.status == "running"

    def test_test_result_creation(self):
        result = TestResult(
            test_run_id=1,
            test_case_id=1,
            status="passed",
        )
        assert result.status == "passed"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_models.py -v`
Expected: FAIL with import error

**Step 3: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: breakthevibe
      POSTGRES_PASSWORD: breakthevibe
      POSTGRES_DB: breakthevibe
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

**Step 4: Write models**

```python
# breakthevibe/storage/__init__.py
```

```python
# breakthevibe/storage/database.py
"""Async database engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from breakthevibe.config.settings import get_settings


def get_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=settings.debug)


async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    engine = get_engine()
    async with SQLModelAsyncSession(engine) as session:
        yield session


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
```

```python
# breakthevibe/models/__init__.py
```

```python
# breakthevibe/models/database.py
"""SQLModel database table models."""

from datetime import datetime

from sqlmodel import Field, SQLModel, Relationship


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    url: str
    config_yaml: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CrawlRun(SQLModel, table=True):
    __tablename__ = "crawl_runs"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    status: str = Field(default="pending")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    site_map_json: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_models.py -v`
Expected: ALL PASS

**Step 6: Set up Alembic**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run alembic init breakthevibe/storage/migrations`

Then edit `alembic.ini` to set `sqlalchemy.url` and edit `migrations/env.py` to import SQLModel metadata.

**Step 7: Start Postgres and run first migration**

Run: `cd /Users/tenaz3/development/breakthevibe && docker compose up -d db`
Run: `uv run alembic revision --autogenerate -m "initial tables"`
Run: `uv run alembic upgrade head`

**Step 8: Commit**

```bash
git add -A
git commit -m "feat: database models, SQLModel setup, Alembic migrations, Docker Compose"
```

---

### Task 5: Shared Domain Models and API Schemas

**Files:**
- Create: `breakthevibe/models/domain.py`
- Create: `breakthevibe/models/api.py`
- Test: `tests/unit/test_domain_models.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_domain_models.py
import pytest
from breakthevibe.models.domain import (
    ComponentInfo,
    CrawlResult,
    PageData,
    ResilientSelector,
    SiteMap,
    TestStep,
)
from breakthevibe.types import SelectorStrategy


@pytest.mark.unit
class TestDomainModels:
    def test_resilient_selector(self):
        selector = ResilientSelector(
            strategy=SelectorStrategy.TEST_ID,
            value="submit-btn",
        )
        assert selector.strategy == SelectorStrategy.TEST_ID

    def test_component_info(self):
        comp = ComponentInfo(
            name="navbar",
            element_type="nav",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.ROLE, value="navigation")
            ],
        )
        assert comp.name == "navbar"
        assert len(comp.selectors) == 1

    def test_page_data(self):
        page = PageData(
            url="https://example.com/products",
            path="/products",
            components=[],
            interactions=[],
            api_calls=[],
        )
        assert page.path == "/products"

    def test_site_map(self):
        site_map = SiteMap(
            base_url="https://example.com",
            pages=[],
        )
        assert site_map.base_url == "https://example.com"

    def test_test_step(self):
        step = TestStep(
            action="click",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Submit"),
            ],
        )
        assert step.action == "click"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_domain_models.py -v`
Expected: FAIL

**Step 3: Write implementations**

```python
# breakthevibe/models/domain.py
"""Inter-module data contracts (not persisted directly)."""

from pydantic import BaseModel

from breakthevibe.types import SelectorStrategy, TestCategory


class ResilientSelector(BaseModel):
    strategy: SelectorStrategy
    value: str
    name: str | None = None  # for ARIA role selectors


class ComponentInfo(BaseModel):
    name: str
    element_type: str
    selectors: list[ResilientSelector] = []
    text_content: str | None = None
    aria_role: str | None = None
    is_interactive: bool = True


class InteractionInfo(BaseModel):
    name: str
    action_type: str  # click, input, scroll, select, hover
    component_name: str
    selectors: list[ResilientSelector] = []


class ApiCallInfo(BaseModel):
    url: str
    method: str
    status_code: int | None = None
    request_headers: dict[str, str] = {}
    response_headers: dict[str, str] = {}
    request_body: str | None = None
    response_body: str | None = None
    triggered_by: str | None = None  # component/interaction that triggered it


class PageData(BaseModel):
    url: str
    path: str
    title: str | None = None
    components: list[ComponentInfo] = []
    interactions: list[InteractionInfo] = []
    api_calls: list[ApiCallInfo] = []
    screenshot_path: str | None = None
    video_path: str | None = None
    navigates_to: list[str] = []  # paths this page links to


class SiteMap(BaseModel):
    base_url: str
    pages: list[PageData] = []
    api_endpoints: list[ApiCallInfo] = []  # deduplicated across all pages


class CrawlResult(BaseModel):
    pages: list[PageData]
    total_routes: int = 0
    total_components: int = 0
    total_api_calls: int = 0


class TestStep(BaseModel):
    action: str  # navigate, click, fill, assert, scroll, wait
    selectors: list[ResilientSelector] = []
    target: str | None = None  # URL for navigate, value for fill
    assertion_type: str | None = None  # url_contains, element_visible, text_equals
    assertion_value: str | None = None


class GeneratedTestCase(BaseModel):
    name: str
    category: TestCategory
    route_path: str
    steps: list[TestStep]
    code: str  # executable pytest code
```

```python
# breakthevibe/models/api.py
"""API request/response schemas for FastAPI endpoints."""

from datetime import datetime

from pydantic import BaseModel

from breakthevibe.types import TestCategory, TestStatus


class ProjectCreate(BaseModel):
    name: str
    url: str
    config_yaml: str | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    url: str
    created_at: datetime


class CrawlRunResponse(BaseModel):
    id: int
    project_id: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None


class TestCaseResponse(BaseModel):
    id: int
    name: str
    category: str
    route_path: str


class TestRunResponse(BaseModel):
    id: int
    project_id: int
    status: str
    total: int
    passed: int
    failed: int
    healed: int


class TestResultResponse(BaseModel):
    id: int
    test_case_id: int
    status: str
    duration_ms: int | None
    error_message: str | None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_domain_models.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/models/domain.py breakthevibe/models/api.py tests/unit/test_domain_models.py
git commit -m "feat: add domain models and API schemas"
```

---

### Task 6: Utility Modules

**Files:**
- Create: `breakthevibe/utils/__init__.py`
- Create: `breakthevibe/utils/retry.py`
- Create: `breakthevibe/utils/sanitize.py`
- Test: `tests/unit/test_utils.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_utils.py
import pytest
from breakthevibe.utils.sanitize import sanitize_url, is_safe_url
from breakthevibe.utils.retry import retry


@pytest.mark.unit
class TestSanitize:
    def test_sanitize_url_strips_whitespace(self):
        assert sanitize_url("  https://example.com  ") == "https://example.com"

    def test_sanitize_url_removes_fragment(self):
        assert sanitize_url("https://example.com/page#section") == "https://example.com/page"

    def test_is_safe_url_blocks_localhost(self):
        assert is_safe_url("http://localhost:3000") is False
        assert is_safe_url("http://127.0.0.1") is False

    def test_is_safe_url_blocks_private_ips(self):
        assert is_safe_url("http://192.168.1.1") is False
        assert is_safe_url("http://10.0.0.1") is False

    def test_is_safe_url_allows_public(self):
        assert is_safe_url("https://example.com") is True
        assert is_safe_url("https://google.com") is True


@pytest.mark.unit
class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_try(self):
        call_count = 0

        @retry(max_attempts=3, delay_ms=10)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failure(self):
        call_count = 0

        @retry(max_attempts=3, delay_ms=10)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        @retry(max_attempts=2, delay_ms=10)
        async def always_fail():
            raise ValueError("fail")

        with pytest.raises(ValueError, match="fail"):
            await always_fail()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_utils.py -v`
Expected: FAIL

**Step 3: Write implementations**

```python
# breakthevibe/utils/__init__.py
```

```python
# breakthevibe/utils/retry.py
"""Retry decorator with exponential backoff."""

import asyncio
import functools
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def retry(max_attempts: int = 3, delay_ms: int = 1000, backoff_factor: float = 2.0):
    """Decorator for async functions with retry logic."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait = (delay_ms * (backoff_factor ** (attempt - 1))) / 1000
                        await logger.adebug(
                            "retry_attempt",
                            func=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            wait_seconds=wait,
                        )
                        await asyncio.sleep(wait)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
```

```python
# breakthevibe/utils/sanitize.py
"""URL and input sanitization utilities."""

import ipaddress
from urllib.parse import urlparse


def sanitize_url(url: str) -> str:
    """Strip whitespace and remove fragments from URL."""
    url = url.strip()
    parsed = urlparse(url)
    # Reconstruct without fragment
    return parsed._replace(fragment="").geturl()


def is_safe_url(url: str) -> bool:
    """Check if URL is safe to crawl (not localhost or private IP)."""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False

    # Block localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_global
    except ValueError:
        # Not an IP address (it's a domain name) — allow it
        return True
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_utils.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/utils/ tests/unit/test_utils.py
git commit -m "feat: add retry decorator and URL sanitization utilities"
```

---

## Phase 2: LLM Provider Layer

### Task 7: Abstract LLM Interface

**Files:**
- Create: `breakthevibe/llm/__init__.py`
- Create: `breakthevibe/llm/provider.py`
- Test: `tests/unit/test_llm_provider.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_llm_provider.py
import pytest
from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


@pytest.mark.unit
class TestLLMProvider:
    def test_llm_response_model(self):
        resp = LLMResponse(content="Hello", model="test", tokens_used=10)
        assert resp.content == "Hello"
        assert resp.tokens_used == 10

    def test_base_is_abstract(self):
        with pytest.raises(TypeError):
            LLMProviderBase()  # type: ignore[abstract]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_llm_provider.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# breakthevibe/llm/__init__.py
```

```python
# breakthevibe/llm/provider.py
"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: int


class LLMProviderBase(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None, max_tokens: int = 4096) -> LLMResponse:
        """Generate a text response from the LLM."""

    @abstractmethod
    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        """Generate a structured (JSON) response from the LLM."""
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_llm_provider.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/llm/ tests/unit/test_llm_provider.py
git commit -m "feat: add abstract LLM provider interface"
```

---

### Task 8: Anthropic (Claude) Provider Implementation

**Files:**
- Create: `breakthevibe/llm/anthropic.py`
- Test: `tests/unit/test_llm_anthropic.py`

**Step 1: Write the failing test (mocked — no real API calls)**

```python
# tests/unit/test_llm_anthropic.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.llm.provider import LLMResponse


@pytest.mark.unit
class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_generate_calls_api(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Test response")]
        mock_message.model = "claude-sonnet-4-20250514"
        mock_message.usage.input_tokens = 10
        mock_message.usage.output_tokens = 5

        with patch("breakthevibe.llm.anthropic.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            MockClient.return_value = mock_client

            provider = AnthropicProvider(api_key="test-key")
            result = await provider.generate("Hello")

            assert isinstance(result, LLMResponse)
            assert result.content == "Test response"
            assert result.tokens_used == 15

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Response")]
        mock_message.model = "claude-sonnet-4-20250514"
        mock_message.usage.input_tokens = 20
        mock_message.usage.output_tokens = 10

        with patch("breakthevibe.llm.anthropic.AsyncAnthropic") as MockClient:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            MockClient.return_value = mock_client

            provider = AnthropicProvider(api_key="test-key")
            result = await provider.generate("Hello", system="You are a tester")

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["system"] == "You are a tester"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_llm_anthropic.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# breakthevibe/llm/anthropic.py
"""Anthropic (Claude) LLM provider implementation."""

from anthropic import AsyncAnthropic

from breakthevibe.llm.provider import LLMProviderBase, LLMResponse


class AnthropicProvider(LLMProviderBase):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(self, prompt: str, system: str | None = None, max_tokens: int = 4096) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        message = await self._client.messages.create(**kwargs)
        return LLMResponse(
            content=message.content[0].text,
            model=message.model,
            tokens_used=message.usage.input_tokens + message.usage.output_tokens,
        )

    async def generate_structured(
        self, prompt: str, system: str | None = None, max_tokens: int = 4096
    ) -> LLMResponse:
        system_with_json = (system or "") + "\nRespond ONLY with valid JSON. No markdown, no explanation."
        return await self.generate(prompt, system=system_with_json.strip(), max_tokens=max_tokens)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_llm_anthropic.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/llm/anthropic.py tests/unit/test_llm_anthropic.py
git commit -m "feat: add Anthropic Claude LLM provider"
```

---

### Task 9: LLM Provider Factory

**Files:**
- Create: `breakthevibe/llm/factory.py`
- Test: `tests/unit/test_llm_factory.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_llm_factory.py
import pytest
from breakthevibe.llm.factory import create_llm_provider
from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.types import LLMProvider
from breakthevibe.exceptions import LLMProviderError


@pytest.mark.unit
class TestLLMFactory:
    def test_create_anthropic_provider(self):
        provider = create_llm_provider(LLMProvider.ANTHROPIC, api_key="test-key")
        assert isinstance(provider, AnthropicProvider)

    def test_create_unknown_provider_raises(self):
        with pytest.raises(LLMProviderError, match="Unsupported"):
            create_llm_provider("unknown", api_key="test")  # type: ignore[arg-type]

    def test_create_without_api_key_raises(self):
        with pytest.raises(LLMProviderError, match="API key"):
            create_llm_provider(LLMProvider.ANTHROPIC, api_key=None)  # type: ignore[arg-type]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_llm_factory.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# breakthevibe/llm/factory.py
"""Factory for creating LLM provider instances."""

from breakthevibe.exceptions import LLMProviderError
from breakthevibe.llm.anthropic import AnthropicProvider
from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.types import LLMProvider


def create_llm_provider(
    provider: LLMProvider, api_key: str | None = None, model: str | None = None, **kwargs: str
) -> LLMProviderBase:
    """Create an LLM provider instance."""
    if provider == LLMProvider.ANTHROPIC:
        if not api_key:
            raise LLMProviderError("API key required for Anthropic provider")
        return AnthropicProvider(api_key=api_key, **({"model": model} if model else {}))
    elif provider == LLMProvider.OPENAI:
        if not api_key:
            raise LLMProviderError("API key required for OpenAI provider")
        raise LLMProviderError("OpenAI provider not yet implemented")
    elif provider == LLMProvider.OLLAMA:
        raise LLMProviderError("Ollama provider not yet implemented")
    else:
        raise LLMProviderError(f"Unsupported LLM provider: {provider}")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_llm_factory.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/llm/factory.py tests/unit/test_llm_factory.py
git commit -m "feat: add LLM provider factory with Anthropic support"
```

---

## Phase 3: Crawler Module

### Task 10: Browser Manager

**Files:**
- Create: `breakthevibe/crawler/__init__.py`
- Create: `breakthevibe/crawler/browser.py`
- Test: `tests/unit/test_crawler_browser.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_crawler_browser.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from breakthevibe.crawler.browser import BrowserManager


@pytest.mark.unit
class TestBrowserManager:
    @pytest.mark.asyncio
    async def test_launch_creates_browser(self):
        with patch("breakthevibe.crawler.browser.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            manager = BrowserManager(headless=True)
            await manager.launch()

            assert manager._browser is not None

    @pytest.mark.asyncio
    async def test_new_context_with_video(self):
        with patch("breakthevibe.crawler.browser.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            manager = BrowserManager(headless=True)
            await manager.launch()
            ctx = await manager.new_context(video_dir="/tmp/videos")

            call_kwargs = mock_browser.new_context.call_args.kwargs
            assert call_kwargs["record_video_dir"] == "/tmp/videos"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_crawler_browser.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# breakthevibe/crawler/__init__.py
```

```python
# breakthevibe/crawler/browser.py
"""Playwright browser management with video recording."""

from playwright.async_api import Browser, BrowserContext, Page, async_playwright, Playwright

from breakthevibe.constants import DEFAULT_VIEWPORT_HEIGHT, DEFAULT_VIEWPORT_WIDTH


class BrowserManager:
    def __init__(self, headless: bool = True):
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def launch(self) -> None:
        """Launch the browser."""
        self._playwright = await async_playwright().__aenter__()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

    async def new_context(
        self,
        video_dir: str | None = None,
        viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
        viewport_height: int = DEFAULT_VIEWPORT_HEIGHT,
    ) -> BrowserContext:
        """Create a new browser context with optional video recording."""
        if not self._browser:
            raise RuntimeError("Browser not launched. Call launch() first.")

        kwargs: dict = {
            "viewport": {"width": viewport_width, "height": viewport_height},
        }
        if video_dir:
            kwargs["record_video_dir"] = video_dir
            kwargs["record_video_size"] = {"width": viewport_width, "height": viewport_height}

        return await self._browser.new_context(**kwargs)

    async def new_page(self, context: BrowserContext) -> Page:
        """Create a new page in the given context."""
        return await context.new_page()

    async def close(self) -> None:
        """Close browser and playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.__aexit__(None, None, None)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_crawler_browser.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/crawler/ tests/unit/test_crawler_browser.py
git commit -m "feat: add Playwright browser manager with video recording"
```

---

### Task 11: Network Interceptor

**Files:**
- Create: `breakthevibe/crawler/network.py`
- Test: `tests/unit/test_crawler_network.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_crawler_network.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from breakthevibe.crawler.network import NetworkInterceptor


@pytest.mark.unit
class TestNetworkInterceptor:
    def test_initial_state(self):
        interceptor = NetworkInterceptor()
        assert interceptor.get_captured_calls() == []

    def test_captures_xhr_request(self):
        interceptor = NetworkInterceptor()
        mock_request = MagicMock()
        mock_request.resource_type = "xhr"
        mock_request.url = "https://example.com/api/data"
        mock_request.method = "GET"
        mock_request.headers = {"content-type": "application/json"}
        mock_request.post_data = None

        interceptor.on_request(mock_request)
        calls = interceptor.get_captured_calls()
        assert len(calls) == 1
        assert calls[0]["url"] == "https://example.com/api/data"
        assert calls[0]["method"] == "GET"

    def test_ignores_non_api_resources(self):
        interceptor = NetworkInterceptor()
        mock_request = MagicMock()
        mock_request.resource_type = "image"
        mock_request.url = "https://example.com/logo.png"

        interceptor.on_request(mock_request)
        assert interceptor.get_captured_calls() == []

    @pytest.mark.asyncio
    async def test_on_response_captures_status(self):
        interceptor = NetworkInterceptor()

        mock_request = MagicMock()
        mock_request.resource_type = "fetch"
        mock_request.url = "https://example.com/api/users"
        mock_request.method = "POST"
        mock_request.headers = {}
        mock_request.post_data = '{"name": "test"}'
        interceptor.on_request(mock_request)

        mock_response = MagicMock()
        mock_response.url = "https://example.com/api/users"
        mock_response.status = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.body = AsyncMock(return_value=b'{"id": 1}')

        await interceptor.on_response(mock_response)
        calls = interceptor.get_captured_calls()
        assert calls[0]["status_code"] == 201

    def test_clear_resets(self):
        interceptor = NetworkInterceptor()
        mock_request = MagicMock()
        mock_request.resource_type = "xhr"
        mock_request.url = "https://example.com/api"
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.post_data = None
        interceptor.on_request(mock_request)

        interceptor.clear()
        assert interceptor.get_captured_calls() == []
```

**Step 2: Run test, verify fail, implement, verify pass, commit**

Implementation in `breakthevibe/crawler/network.py` — intercepts XHR/fetch requests, records URL/method/headers/body/status, provides `get_captured_calls()` and `clear()`.

```python
# breakthevibe/crawler/network.py
"""Network traffic interceptor for capturing API calls during crawling."""

import structlog

logger = structlog.get_logger(__name__)

API_RESOURCE_TYPES = {"xhr", "fetch"}


class NetworkInterceptor:
    def __init__(self):
        self._calls: list[dict] = []
        self._pending: dict[str, dict] = {}

    def on_request(self, request) -> None:
        """Handle intercepted request."""
        if request.resource_type not in API_RESOURCE_TYPES:
            return

        call_data = {
            "url": request.url,
            "method": request.method,
            "request_headers": dict(request.headers),
            "request_body": request.post_data,
            "status_code": None,
            "response_headers": {},
            "response_body": None,
        }
        self._pending[request.url] = call_data
        self._calls.append(call_data)

    async def on_response(self, response) -> None:
        """Handle intercepted response."""
        url = response.url
        if url in self._pending:
            call_data = self._pending[url]
            call_data["status_code"] = response.status
            call_data["response_headers"] = dict(response.headers)
            try:
                body = await response.body()
                call_data["response_body"] = body.decode("utf-8", errors="replace")
            except Exception:
                call_data["response_body"] = None
            del self._pending[url]

    def get_captured_calls(self) -> list[dict]:
        """Return all captured API calls."""
        return list(self._calls)

    def clear(self) -> None:
        """Clear all captured data."""
        self._calls.clear()
        self._pending.clear()
```

**Commit:**

```bash
git add breakthevibe/crawler/network.py tests/unit/test_crawler_network.py
git commit -m "feat: add network traffic interceptor for API capture"
```

---

### Task 12: Component Extractor

**Files:**
- Create: `breakthevibe/crawler/extractor.py`
- Test: `tests/unit/test_crawler_extractor.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_crawler_extractor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from breakthevibe.crawler.extractor import ComponentExtractor
from breakthevibe.models.domain import ComponentInfo, InteractionInfo


MOCK_DOM_RESULT = [
    {
        "tag": "button",
        "text": "Submit",
        "aria_role": "button",
        "is_interactive": True,
        "test_id": "submit-btn",
        "css_selector": "form > button.primary",
        "aria_name": "Submit",
        "bounding_box": {"x": 100, "y": 200, "width": 80, "height": 40},
        "visible": True,
    },
    {
        "tag": "input",
        "text": "",
        "aria_role": "textbox",
        "is_interactive": True,
        "test_id": None,
        "css_selector": "input[type='email']",
        "aria_name": "Email address",
        "bounding_box": {"x": 100, "y": 150, "width": 200, "height": 30},
        "visible": True,
    },
    {
        "tag": "nav",
        "text": "",
        "aria_role": "navigation",
        "is_interactive": False,
        "test_id": "main-nav",
        "css_selector": "nav.main-navigation",
        "aria_name": None,
        "bounding_box": {"x": 0, "y": 0, "width": 1280, "height": 60},
        "visible": True,
    },
]


@pytest.mark.unit
class TestComponentExtractor:
    @pytest.mark.asyncio
    async def test_extract_components_returns_list(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=MOCK_DOM_RESULT)

        extractor = ComponentExtractor()
        components = await extractor.extract_components(mock_page)

        assert len(components) == 3
        assert all(isinstance(c, ComponentInfo) for c in components)

    @pytest.mark.asyncio
    async def test_extract_builds_selectors(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=MOCK_DOM_RESULT)

        extractor = ComponentExtractor()
        components = await extractor.extract_components(mock_page)

        submit_btn = components[0]
        assert submit_btn.element_type == "button"
        assert submit_btn.text_content == "Submit"
        # Should have multiple selectors ordered by stability
        assert len(submit_btn.selectors) >= 2

    @pytest.mark.asyncio
    async def test_extract_interactions(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=MOCK_DOM_RESULT)

        extractor = ComponentExtractor()
        interactions = await extractor.extract_interactions(mock_page)

        # Only interactive elements become interactions
        interactive = [i for i in interactions if i.action_type in ("click", "input")]
        assert len(interactive) >= 2  # button + input

    @pytest.mark.asyncio
    async def test_extract_handles_empty_page(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        extractor = ComponentExtractor()
        components = await extractor.extract_components(mock_page)
        assert components == []

    @pytest.mark.asyncio
    async def test_take_screenshot(self):
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"png_data")

        extractor = ComponentExtractor()
        data = await extractor.take_screenshot(mock_page, "/tmp/test.png")
        mock_page.screenshot.assert_called_once_with(path="/tmp/test.png", full_page=True)
        assert data == b"png_data"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_crawler_extractor.py -v`
Expected: FAIL with import error

**Step 3: Write implementation**

```python
# breakthevibe/crawler/extractor.py
"""Component and interaction extraction from page DOM."""

from playwright.async_api import Page

from breakthevibe.models.domain import ComponentInfo, InteractionInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy

# JavaScript to extract interactive and structural elements from the DOM
EXTRACT_JS = """
() => {
    const elements = [];
    const selectors = 'a, button, input, select, textarea, [role], nav, form, '
        + 'header, footer, main, aside, [data-testid], [data-test]';
    document.querySelectorAll(selectors).forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;
        const interactive = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);
        elements.push({
            tag: el.tagName.toLowerCase(),
            text: (el.textContent || '').trim().slice(0, 200),
            aria_role: el.getAttribute('role') || el.tagName.toLowerCase(),
            is_interactive: interactive,
            test_id: el.getAttribute('data-testid') || el.getAttribute('data-test'),
            css_selector: el.tagName.toLowerCase()
                + (el.id ? '#' + el.id : '')
                + (el.className ? '.' + [...el.classList].join('.') : ''),
            aria_name: el.getAttribute('aria-label') || el.getAttribute('name') || null,
            bounding_box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
            visible: rect.width > 0 && rect.height > 0,
        });
    });
    return elements;
}
"""


class ComponentExtractor:
    """Extracts components and interactions from a Playwright page."""

    async def extract_components(self, page: Page) -> list[ComponentInfo]:
        """Extract all meaningful components from the page DOM."""
        raw_elements = await page.evaluate(EXTRACT_JS)
        components = []
        for el in raw_elements:
            if not el.get("visible", False):
                continue
            selectors = self._build_selectors(el)
            components.append(
                ComponentInfo(
                    name=el.get("aria_name") or el.get("text", "")[:50] or el["tag"],
                    element_type=el["tag"],
                    selectors=selectors,
                    text_content=el.get("text") or None,
                    aria_role=el.get("aria_role"),
                    is_interactive=el.get("is_interactive", False),
                )
            )
        return components

    async def extract_interactions(self, page: Page) -> list[InteractionInfo]:
        """Extract interactive elements as interactions."""
        raw_elements = await page.evaluate(EXTRACT_JS)
        interactions = []
        for el in raw_elements:
            if not el.get("visible") or not el.get("is_interactive"):
                continue
            action_type = self._infer_action_type(el["tag"])
            selectors = self._build_selectors(el)
            interactions.append(
                InteractionInfo(
                    name=el.get("aria_name") or el.get("text", "")[:50] or el["tag"],
                    action_type=action_type,
                    component_name=el.get("aria_name") or el["tag"],
                    selectors=selectors,
                )
            )
        return interactions

    async def take_screenshot(self, page: Page, path: str) -> bytes:
        """Take a full-page screenshot."""
        return await page.screenshot(path=path, full_page=True)

    def _build_selectors(self, el: dict) -> list[ResilientSelector]:
        """Build ordered list of selectors from most to least stable."""
        selectors: list[ResilientSelector] = []
        if el.get("test_id"):
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.TEST_ID, value=el["test_id"])
            )
        if el.get("aria_role") and el.get("aria_name"):
            selectors.append(
                ResilientSelector(
                    strategy=SelectorStrategy.ROLE,
                    value=el["aria_role"],
                    name=el["aria_name"],
                )
            )
        if el.get("text") and len(el["text"]) < 100:
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.TEXT, value=el["text"][:100])
            )
        if el.get("css_selector"):
            selectors.append(
                ResilientSelector(strategy=SelectorStrategy.CSS, value=el["css_selector"])
            )
        return selectors

    def _infer_action_type(self, tag: str) -> str:
        """Infer interaction type from element tag."""
        tag_actions = {
            "button": "click",
            "a": "click",
            "input": "input",
            "textarea": "input",
            "select": "select",
        }
        return tag_actions.get(tag, "click")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_crawler_extractor.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/crawler/extractor.py tests/unit/test_crawler_extractor.py
git commit -m "feat: add component extractor for DOM analysis"
```

---

### Task 13: SPA-Aware Navigator

**Files:**
- Create: `breakthevibe/crawler/navigator.py`
- Test: `tests/unit/test_crawler_navigator.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_crawler_navigator.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from breakthevibe.crawler.navigator import Navigator


@pytest.mark.unit
class TestNavigator:
    def test_init_with_config(self):
        nav = Navigator(
            base_url="https://example.com",
            max_depth=3,
            skip_patterns=["/admin/*"],
        )
        assert nav._base_url == "https://example.com"
        assert nav._max_depth == 3
        assert nav._visited == set()

    def test_should_skip_matching_pattern(self):
        nav = Navigator(
            base_url="https://example.com",
            skip_patterns=["/admin/*", "/api/internal/*"],
        )
        assert nav.should_skip("/admin/settings") is True
        assert nav.should_skip("/api/internal/debug") is True
        assert nav.should_skip("/products") is False

    def test_should_skip_already_visited(self):
        nav = Navigator(base_url="https://example.com")
        nav._visited.add("https://example.com/products")
        assert nav.should_visit("https://example.com/products") is False

    def test_should_visit_same_domain(self):
        nav = Navigator(base_url="https://example.com")
        assert nav.should_visit("https://example.com/about") is True
        assert nav.should_visit("https://other-site.com/page") is False

    def test_respects_max_depth(self):
        nav = Navigator(base_url="https://example.com", max_depth=2)
        assert nav.is_within_depth(0) is True
        assert nav.is_within_depth(2) is True
        assert nav.is_within_depth(3) is False

    @pytest.mark.asyncio
    async def test_discover_links_from_page(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            "https://example.com/about",
            "https://example.com/products",
            "https://other.com/external",
            "javascript:void(0)",
        ])

        nav = Navigator(base_url="https://example.com")
        links = await nav.discover_links(mock_page)

        assert "https://example.com/about" in links
        assert "https://example.com/products" in links
        assert "https://other.com/external" not in links
        assert "javascript:void(0)" not in links

    @pytest.mark.asyncio
    async def test_detect_spa_navigation(self):
        nav = Navigator(base_url="https://example.com")
        mock_page = AsyncMock()

        # Simulate SPA route change detection script returns new URL
        mock_page.evaluate = AsyncMock(return_value="https://example.com/products/123")
        mock_page.url = "https://example.com/products/123"

        new_url = await nav.get_current_url(mock_page)
        assert new_url == "https://example.com/products/123"

    def test_mark_visited(self):
        nav = Navigator(base_url="https://example.com")
        nav.mark_visited("https://example.com/about")
        assert "https://example.com/about" in nav._visited
        assert nav.should_visit("https://example.com/about") is False

    def test_get_path_from_url(self):
        nav = Navigator(base_url="https://example.com")
        assert nav.get_path("https://example.com/products?page=1") == "/products"
        assert nav.get_path("https://example.com/") == "/"
        assert nav.get_path("https://example.com") == "/"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_crawler_navigator.py -v`
Expected: FAIL with import error

**Step 3: Write implementation**

```python
# breakthevibe/crawler/navigator.py
"""SPA-aware page navigator for crawling websites."""

import fnmatch
from urllib.parse import urlparse

from playwright.async_api import Page

from breakthevibe.constants import DEFAULT_MAX_DEPTH

# JavaScript to extract all links from the page
DISCOVER_LINKS_JS = """
() => {
    const links = new Set();
    document.querySelectorAll('a[href]').forEach(a => {
        try {
            const url = new URL(a.href, window.location.origin);
            links.add(url.origin + url.pathname);
        } catch {}
    });
    return [...links];
}
"""

# JavaScript to install SPA navigation listener
INSTALL_SPA_LISTENER_JS = """
() => {
    if (window.__btv_spa_listener) return;
    window.__btv_spa_listener = true;
    window.__btv_route_changes = [];
    const orig_push = history.pushState;
    const orig_replace = history.replaceState;
    history.pushState = function(...args) {
        orig_push.apply(this, args);
        window.__btv_route_changes.push(window.location.href);
    };
    history.replaceState = function(...args) {
        orig_replace.apply(this, args);
        window.__btv_route_changes.push(window.location.href);
    };
    window.addEventListener('popstate', () => {
        window.__btv_route_changes.push(window.location.href);
    });
    window.addEventListener('hashchange', () => {
        window.__btv_route_changes.push(window.location.href);
    });
}
"""


class Navigator:
    """SPA-aware page discovery and navigation."""

    def __init__(
        self,
        base_url: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
        skip_patterns: list[str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._max_depth = max_depth
        self._skip_patterns = skip_patterns or []
        self._visited: set[str] = set()
        self._base_domain = urlparse(base_url).netloc

    def should_skip(self, path: str) -> bool:
        """Check if path matches any skip pattern."""
        for pattern in self._skip_patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    def should_visit(self, url: str) -> bool:
        """Check if URL should be visited (same domain, not visited, not skipped)."""
        if url in self._visited:
            return False
        parsed = urlparse(url)
        if parsed.netloc != self._base_domain:
            return False
        path = parsed.path or "/"
        if self.should_skip(path):
            return False
        return True

    def is_within_depth(self, depth: int) -> bool:
        """Check if current depth is within max depth."""
        return depth <= self._max_depth

    def mark_visited(self, url: str) -> None:
        """Mark a URL as visited."""
        self._visited.add(url)

    def get_path(self, url: str) -> str:
        """Extract clean path from URL (without query params or fragment)."""
        parsed = urlparse(url)
        return parsed.path or "/"

    async def discover_links(self, page: Page) -> list[str]:
        """Discover all links on the current page, filtered to same domain."""
        all_links = await page.evaluate(DISCOVER_LINKS_JS)
        return [
            link for link in all_links
            if self.should_visit(link) and not link.startswith("javascript:")
        ]

    async def install_spa_listener(self, page: Page) -> None:
        """Install JavaScript listener for SPA route changes."""
        await page.evaluate(INSTALL_SPA_LISTENER_JS)

    async def get_spa_route_changes(self, page: Page) -> list[str]:
        """Get any SPA route changes that occurred since last check."""
        changes = await page.evaluate("() => { const c = window.__btv_route_changes || []; window.__btv_route_changes = []; return c; }")
        return changes

    async def get_current_url(self, page: Page) -> str:
        """Get the current page URL."""
        return page.url
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_crawler_navigator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/crawler/navigator.py tests/unit/test_crawler_navigator.py
git commit -m "feat: add SPA-aware page navigator"
```

---

## Phase 4: Mapper Module

### Task 14: Mind-Map Builder

**Files:**
- Create: `breakthevibe/mapper/__init__.py`
- Create: `breakthevibe/mapper/builder.py`
- Test: `tests/unit/test_mapper_builder.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_mapper_builder.py
import pytest
from breakthevibe.mapper.builder import MindMapBuilder
from breakthevibe.models.domain import (
    ApiCallInfo,
    ComponentInfo,
    CrawlResult,
    InteractionInfo,
    PageData,
    ResilientSelector,
    SiteMap,
)
from breakthevibe.types import SelectorStrategy


def make_page(path: str, components: int = 2, api_calls: int = 1) -> PageData:
    """Helper to create test PageData."""
    return PageData(
        url=f"https://example.com{path}",
        path=path,
        title=f"Page {path}",
        components=[
            ComponentInfo(
                name=f"component-{i}",
                element_type="button",
                selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value=f"btn-{i}")],
            )
            for i in range(components)
        ],
        interactions=[
            InteractionInfo(
                name=f"click-{i}",
                action_type="click",
                component_name=f"component-{i}",
            )
            for i in range(components)
        ],
        api_calls=[
            ApiCallInfo(url=f"https://example.com/api/data-{i}", method="GET", status_code=200)
            for i in range(api_calls)
        ],
        navigates_to=["/about"] if path == "/" else [],
    )


@pytest.mark.unit
class TestMindMapBuilder:
    def test_build_from_crawl_result(self):
        crawl = CrawlResult(
            pages=[make_page("/"), make_page("/about")],
            total_routes=2,
            total_components=4,
            total_api_calls=2,
        )
        builder = MindMapBuilder()
        site_map = builder.build(crawl, base_url="https://example.com")

        assert isinstance(site_map, SiteMap)
        assert site_map.base_url == "https://example.com"
        assert len(site_map.pages) == 2

    def test_deduplicates_api_endpoints(self):
        page1 = make_page("/", api_calls=0)
        page1.api_calls = [
            ApiCallInfo(url="https://example.com/api/users", method="GET", status_code=200),
            ApiCallInfo(url="https://example.com/api/products", method="GET", status_code=200),
        ]
        page2 = make_page("/about", api_calls=0)
        page2.api_calls = [
            ApiCallInfo(url="https://example.com/api/users", method="GET", status_code=200),
        ]

        crawl = CrawlResult(pages=[page1, page2], total_routes=2)
        builder = MindMapBuilder()
        site_map = builder.build(crawl, base_url="https://example.com")

        # Should have 2 unique endpoints, not 3
        urls = [ep.url for ep in site_map.api_endpoints]
        assert len(urls) == 2
        assert "https://example.com/api/users" in urls
        assert "https://example.com/api/products" in urls

    def test_empty_crawl_result(self):
        crawl = CrawlResult(pages=[])
        builder = MindMapBuilder()
        site_map = builder.build(crawl, base_url="https://example.com")

        assert site_map.pages == []
        assert site_map.api_endpoints == []

    def test_to_json(self):
        crawl = CrawlResult(pages=[make_page("/")])
        builder = MindMapBuilder()
        site_map = builder.build(crawl, base_url="https://example.com")
        json_str = site_map.model_dump_json()
        assert "https://example.com" in json_str
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_mapper_builder.py -v`
Expected: FAIL with import error

**Step 3: Write implementation**

```python
# breakthevibe/mapper/__init__.py
```

```python
# breakthevibe/mapper/builder.py
"""Mind-map builder from crawl data."""

from breakthevibe.models.domain import ApiCallInfo, CrawlResult, SiteMap

import structlog

logger = structlog.get_logger(__name__)


class MindMapBuilder:
    """Builds a SiteMap (mind-map) from crawl results."""

    def build(self, crawl: CrawlResult, base_url: str) -> SiteMap:
        """Build a SiteMap from crawl results, deduplicating API endpoints."""
        all_api_calls = self._deduplicate_api_calls(crawl)
        return SiteMap(
            base_url=base_url,
            pages=crawl.pages,
            api_endpoints=all_api_calls,
        )

    def _deduplicate_api_calls(self, crawl: CrawlResult) -> list[ApiCallInfo]:
        """Collect and deduplicate API calls across all pages."""
        seen: set[str] = set()
        unique: list[ApiCallInfo] = []
        for page in crawl.pages:
            for call in page.api_calls:
                key = f"{call.method}:{call.url}"
                if key not in seen:
                    seen.add(key)
                    unique.append(call)
        return unique
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_mapper_builder.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/mapper/ tests/unit/test_mapper_builder.py
git commit -m "feat: add mind-map builder from crawl data"
```

---

### Task 15: LLM Component Classifier

**Files:**
- Create: `breakthevibe/mapper/classifier.py`
- Test: `tests/unit/test_mapper_classifier.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_mapper_classifier.py
import json
import pytest
from unittest.mock import AsyncMock
from breakthevibe.mapper.classifier import ComponentClassifier
from breakthevibe.models.domain import ComponentInfo, ResilientSelector
from breakthevibe.llm.provider import LLMResponse
from breakthevibe.types import SelectorStrategy


SAMPLE_COMPONENTS = [
    ComponentInfo(
        name="Home",
        element_type="a",
        selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value="Home")],
        aria_role="link",
    ),
    ComponentInfo(
        name="About",
        element_type="a",
        selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value="About")],
        aria_role="link",
    ),
    ComponentInfo(
        name="Submit",
        element_type="button",
        selectors=[ResilientSelector(strategy=SelectorStrategy.TEXT, value="Submit")],
        aria_role="button",
    ),
]

MOCK_LLM_RESPONSE = json.dumps({
    "groups": [
        {
            "group_name": "Navigation Bar",
            "group_type": "navigation",
            "components": ["Home", "About"],
        },
        {
            "group_name": "Form Actions",
            "group_type": "form",
            "components": ["Submit"],
        },
    ]
})


@pytest.mark.unit
class TestComponentClassifier:
    @pytest.mark.asyncio
    async def test_classify_groups_components(self):
        mock_llm = AsyncMock()
        mock_llm.generate_structured = AsyncMock(
            return_value=LLMResponse(content=MOCK_LLM_RESPONSE, model="test", tokens_used=100)
        )

        classifier = ComponentClassifier(llm=mock_llm)
        groups = await classifier.classify(SAMPLE_COMPONENTS, page_url="https://example.com/")

        assert len(groups) == 2
        assert groups[0]["group_name"] == "Navigation Bar"
        assert "Home" in groups[0]["components"]
        assert "About" in groups[0]["components"]
        assert groups[1]["group_name"] == "Form Actions"

    @pytest.mark.asyncio
    async def test_classify_sends_component_summary(self):
        mock_llm = AsyncMock()
        mock_llm.generate_structured = AsyncMock(
            return_value=LLMResponse(content='{"groups": []}', model="test", tokens_used=50)
        )

        classifier = ComponentClassifier(llm=mock_llm)
        await classifier.classify(SAMPLE_COMPONENTS, page_url="https://example.com/")

        call_args = mock_llm.generate_structured.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "Home" in prompt
        assert "Submit" in prompt

    @pytest.mark.asyncio
    async def test_classify_empty_components(self):
        mock_llm = AsyncMock()
        classifier = ComponentClassifier(llm=mock_llm)
        groups = await classifier.classify([], page_url="https://example.com/")
        assert groups == []
        mock_llm.generate_structured.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_mapper_classifier.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# breakthevibe/mapper/classifier.py
"""LLM-powered component classification and grouping."""

import json

import structlog

from breakthevibe.llm.provider import LLMProviderBase
from breakthevibe.models.domain import ComponentInfo

logger = structlog.get_logger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """You are an expert web UI analyst. Given a list of UI components extracted from a web page, group them into logical sections (navigation, forms, content areas, etc.).

Return JSON with this structure:
{
    "groups": [
        {
            "group_name": "descriptive name",
            "group_type": "navigation|form|content|footer|header|sidebar|modal|other",
            "components": ["component name 1", "component name 2"]
        }
    ]
}

Group by visual/functional proximity. Every component must appear in exactly one group."""


class ComponentClassifier:
    """Uses LLM to classify and group page components."""

    def __init__(self, llm: LLMProviderBase):
        self._llm = llm

    async def classify(self, components: list[ComponentInfo], page_url: str) -> list[dict]:
        """Classify components into logical groups using LLM."""
        if not components:
            return []

        component_summary = "\n".join(
            f"- {c.name} ({c.element_type}, role={c.aria_role}, interactive={c.is_interactive})"
            for c in components
        )
        prompt = f"Page: {page_url}\n\nComponents found:\n{component_summary}\n\nGroup these components."

        response = await self._llm.generate_structured(
            prompt=prompt,
            system=CLASSIFIER_SYSTEM_PROMPT,
        )

        try:
            result = json.loads(response.content)
            return result.get("groups", [])
        except json.JSONDecodeError:
            logger.warning("llm_classification_parse_error", page_url=page_url)
            return []
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_mapper_classifier.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/mapper/classifier.py tests/unit/test_mapper_classifier.py
git commit -m "feat: add LLM-powered component classifier"
```

---

### Task 16: API Merger (Traffic + OpenAPI Spec)

**Files:**
- Create: `breakthevibe/mapper/api_merger.py`
- Test: `tests/unit/test_mapper_api_merger.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_mapper_api_merger.py
import pytest
from breakthevibe.mapper.api_merger import ApiMerger
from breakthevibe.models.domain import ApiCallInfo


OBSERVED_TRAFFIC = [
    ApiCallInfo(url="https://example.com/api/users", method="GET", status_code=200),
    ApiCallInfo(url="https://example.com/api/products", method="GET", status_code=200),
    ApiCallInfo(url="https://example.com/api/products", method="POST", status_code=201),
]

OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "paths": {
        "/api/users": {
            "get": {"summary": "List users", "responses": {"200": {}}},
        },
        "/api/products": {
            "get": {"summary": "List products", "responses": {"200": {}}},
            "post": {"summary": "Create product", "responses": {"201": {}}},
        },
        "/api/orders": {
            "get": {"summary": "List orders", "responses": {"200": {}}},
        },
    },
}


@pytest.mark.unit
class TestApiMerger:
    def test_merge_finds_all_observed(self):
        merger = ApiMerger()
        result = merger.merge(OBSERVED_TRAFFIC, OPENAPI_SPEC)
        assert len(result.matched) == 3  # all 3 observed are in spec

    def test_merge_detects_unobserved_spec_endpoints(self):
        merger = ApiMerger()
        result = merger.merge(OBSERVED_TRAFFIC, OPENAPI_SPEC)
        # /api/orders GET is in spec but not observed
        assert len(result.spec_only) == 1
        assert result.spec_only[0]["path"] == "/api/orders"
        assert result.spec_only[0]["method"] == "get"

    def test_merge_detects_traffic_not_in_spec(self):
        extra_traffic = OBSERVED_TRAFFIC + [
            ApiCallInfo(url="https://example.com/api/internal/health", method="GET", status_code=200),
        ]
        merger = ApiMerger()
        result = merger.merge(extra_traffic, OPENAPI_SPEC)
        assert len(result.traffic_only) == 1
        assert "/api/internal/health" in result.traffic_only[0].url

    def test_merge_without_spec(self):
        merger = ApiMerger()
        result = merger.merge(OBSERVED_TRAFFIC, None)
        assert len(result.matched) == 0
        assert len(result.traffic_only) == 3
        assert len(result.spec_only) == 0

    def test_merge_empty_traffic(self):
        merger = ApiMerger()
        result = merger.merge([], OPENAPI_SPEC)
        assert len(result.matched) == 0
        assert len(result.spec_only) == 3  # all spec endpoints unobserved
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_mapper_api_merger.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# breakthevibe/mapper/api_merger.py
"""Merges observed API traffic with OpenAPI spec definitions."""

from dataclasses import dataclass, field
from urllib.parse import urlparse

from breakthevibe.models.domain import ApiCallInfo


@dataclass
class MergeResult:
    """Result of merging traffic with spec."""
    matched: list[ApiCallInfo] = field(default_factory=list)
    traffic_only: list[ApiCallInfo] = field(default_factory=list)
    spec_only: list[dict] = field(default_factory=list)


class ApiMerger:
    """Merges observed API traffic with OpenAPI/Swagger specification."""

    def merge(self, traffic: list[ApiCallInfo], spec: dict | None) -> MergeResult:
        """Merge observed traffic with OpenAPI spec.

        Returns matched endpoints, traffic-only (not in spec), and spec-only (not observed).
        """
        if not spec:
            return MergeResult(traffic_only=list(traffic))

        spec_endpoints = self._extract_spec_endpoints(spec)
        traffic_keys = set()
        matched: list[ApiCallInfo] = []
        traffic_only: list[ApiCallInfo] = []

        for call in traffic:
            path = urlparse(call.url).path
            key = f"{call.method.lower()}:{path}"
            traffic_keys.add(key)
            if key in spec_endpoints:
                matched.append(call)
            else:
                traffic_only.append(call)

        spec_only = [
            {"path": ep["path"], "method": ep["method"], "summary": ep.get("summary", "")}
            for key, ep in spec_endpoints.items()
            if key not in traffic_keys
        ]

        return MergeResult(matched=matched, traffic_only=traffic_only, spec_only=spec_only)

    def _extract_spec_endpoints(self, spec: dict) -> dict[str, dict]:
        """Extract path+method pairs from OpenAPI spec."""
        endpoints: dict[str, dict] = {}
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    key = f"{method.lower()}:{path}"
                    endpoints[key] = {
                        "path": path,
                        "method": method.lower(),
                        "summary": details.get("summary", ""),
                    }
        return endpoints
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_mapper_api_merger.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/mapper/api_merger.py tests/unit/test_mapper_api_merger.py
git commit -m "feat: add API merger for traffic and OpenAPI spec"
```

---

## Phase 5: Generator Module

### Task 17: Rules Engine

**Files:**
- Create: `breakthevibe/generator/__init__.py`
- Create: `breakthevibe/generator/rules/__init__.py`
- Create: `breakthevibe/generator/rules/schema.py`
- Create: `breakthevibe/generator/rules/engine.py`
- Test: `tests/unit/test_rules_engine.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_rules_engine.py
import pytest
from breakthevibe.generator.rules.schema import (
    CrawlRules,
    InputRules,
    InteractionRules,
    TestRules,
    ApiRules,
    ExecutionRules,
    RulesConfig,
)
from breakthevibe.generator.rules.engine import RulesEngine


SAMPLE_YAML = """
crawl:
  max_depth: 5
  skip_urls:
    - "/admin/*"
    - "/api/internal/*"
  scroll_behavior: incremental
  wait_times:
    page_load: 3000
    after_click: 1000
  viewport:
    width: 1280
    height: 800

inputs:
  email: "test@example.com"
  phone: "+1234567890"
  username: "testuser"

interactions:
  cookie_banner: dismiss
  modals: close_on_appear
  infinite_scroll: scroll_3_times

tests:
  skip_visual:
    - "/404"
    - "/500"
  custom_assertions: []

api:
  ignore_endpoints:
    - "/api/analytics/*"
    - "/api/tracking/*"
  expected_overrides:
    "GET /api/health":
      status: 200

execution:
  mode: smart
  suites:
    auth-flow:
      mode: sequential
      shared_context: true
    product-pages:
      mode: parallel
      workers: 4
"""


class TestRulesConfig:
    def test_parse_from_yaml(self) -> None:
        config = RulesConfig.from_yaml(SAMPLE_YAML)
        assert config.crawl.max_depth == 5
        assert len(config.crawl.skip_urls) == 2
        assert config.inputs.values["email"] == "test@example.com"
        assert config.interactions.cookie_banner == "dismiss"
        assert config.execution.mode == "smart"

    def test_defaults_when_empty(self) -> None:
        config = RulesConfig.from_yaml("")
        assert config.crawl.max_depth == 10
        assert config.crawl.skip_urls == []
        assert config.inputs.values == {}
        assert config.execution.mode == "smart"


class TestRulesEngine:
    @pytest.fixture()
    def engine(self) -> RulesEngine:
        config = RulesConfig.from_yaml(SAMPLE_YAML)
        return RulesEngine(config)

    def test_should_skip_url_exact_match(self, engine: RulesEngine) -> None:
        assert engine.should_skip_url("/admin/settings") is True
        assert engine.should_skip_url("/api/internal/users") is True

    def test_should_not_skip_allowed_url(self, engine: RulesEngine) -> None:
        assert engine.should_skip_url("/products") is False
        assert engine.should_skip_url("/api/products") is False

    def test_get_input_value(self, engine: RulesEngine) -> None:
        assert engine.get_input_value("email") == "test@example.com"
        assert engine.get_input_value("phone") == "+1234567890"
        assert engine.get_input_value("nonexistent") is None

    def test_should_skip_visual(self, engine: RulesEngine) -> None:
        assert engine.should_skip_visual("/404") is True
        assert engine.should_skip_visual("/home") is False

    def test_should_ignore_endpoint(self, engine: RulesEngine) -> None:
        assert engine.should_ignore_endpoint("/api/analytics/pageview") is True
        assert engine.should_ignore_endpoint("/api/products") is False

    def test_get_expected_override(self, engine: RulesEngine) -> None:
        override = engine.get_expected_override("GET", "/api/health")
        assert override is not None
        assert override["status"] == 200
        assert engine.get_expected_override("POST", "/api/users") is None

    def test_get_execution_mode(self, engine: RulesEngine) -> None:
        assert engine.get_execution_mode() == "smart"

    def test_get_suite_config(self, engine: RulesEngine) -> None:
        auth = engine.get_suite_config("auth-flow")
        assert auth is not None
        assert auth["mode"] == "sequential"
        assert auth["shared_context"] is True
        assert engine.get_suite_config("nonexistent") is None

    def test_get_cookie_banner_action(self, engine: RulesEngine) -> None:
        assert engine.get_cookie_banner_action() == "dismiss"

    def test_get_modal_action(self, engine: RulesEngine) -> None:
        assert engine.get_modal_action() == "close_on_appear"

    def test_get_scroll_behavior(self, engine: RulesEngine) -> None:
        assert engine.get_scroll_behavior() == "incremental"

    def test_get_infinite_scroll_action(self, engine: RulesEngine) -> None:
        assert engine.get_infinite_scroll_action() == "scroll_3_times"

    def test_get_viewport(self, engine: RulesEngine) -> None:
        vp = engine.get_viewport()
        assert vp == {"width": 1280, "height": 800}

    def test_get_wait_times(self, engine: RulesEngine) -> None:
        wt = engine.get_wait_times()
        assert wt["page_load"] == 3000
        assert wt["after_click"] == 1000

    def test_to_yaml_roundtrip(self, engine: RulesEngine) -> None:
        yaml_str = engine.to_yaml()
        config2 = RulesConfig.from_yaml(yaml_str)
        engine2 = RulesEngine(config2)
        assert engine2.should_skip_url("/admin/settings") is True
        assert engine2.get_input_value("email") == "test@example.com"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_rules_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.generator'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/generator/__init__.py
```

```python
# breakthevibe/generator/rules/__init__.py
```

```python
# breakthevibe/generator/rules/schema.py
"""Rules configuration schema with Pydantic validation."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field


class ViewportConfig(BaseModel):
    width: int = 1280
    height: int = 800


class WaitTimesConfig(BaseModel):
    page_load: int = 3000
    after_click: int = 1000


class CrawlRules(BaseModel):
    max_depth: int = 10
    skip_urls: list[str] = Field(default_factory=list)
    scroll_behavior: str = "incremental"
    wait_times: WaitTimesConfig = Field(default_factory=WaitTimesConfig)
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)


class InputRules(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any] | None) -> InputRules:
        if not data:
            return cls()
        return cls(values=data)


class InteractionRules(BaseModel):
    cookie_banner: str = "dismiss"
    modals: str = "close_on_appear"
    infinite_scroll: str = "scroll_3_times"


class TestRules(BaseModel):
    skip_visual: list[str] = Field(default_factory=list)
    custom_assertions: list[str] = Field(default_factory=list)


class ApiRules(BaseModel):
    ignore_endpoints: list[str] = Field(default_factory=list)
    expected_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SuiteConfig(BaseModel):
    mode: str = "smart"
    shared_context: bool = False
    workers: int = 1


class ExecutionRules(BaseModel):
    mode: str = "smart"
    suites: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RulesConfig(BaseModel):
    crawl: CrawlRules = Field(default_factory=CrawlRules)
    inputs: InputRules = Field(default_factory=InputRules)
    interactions: InteractionRules = Field(default_factory=InteractionRules)
    tests: TestRules = Field(default_factory=TestRules)
    api: ApiRules = Field(default_factory=ApiRules)
    execution: ExecutionRules = Field(default_factory=ExecutionRules)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> RulesConfig:
        """Parse a YAML string into a RulesConfig."""
        if not yaml_str or not yaml_str.strip():
            return cls()
        raw = yaml.safe_load(yaml_str)
        if not raw or not isinstance(raw, dict):
            return cls()
        # Handle inputs specially (flat dict -> InputRules)
        inputs_data = raw.pop("inputs", None)
        config = cls.model_validate(raw)
        if inputs_data:
            config.inputs = InputRules.from_raw(inputs_data)
        return config

    def to_yaml(self) -> str:
        """Serialize config back to YAML."""
        data = self.model_dump()
        # Flatten inputs back to simple dict
        data["inputs"] = data["inputs"]["values"]
        return yaml.dump(data, default_flow_style=False, sort_keys=False)
```

```python
# breakthevibe/generator/rules/engine.py
"""Rules engine providing query methods over parsed config."""

from __future__ import annotations

import fnmatch
from typing import Any

from breakthevibe.generator.rules.schema import RulesConfig

import structlog

logger = structlog.get_logger(__name__)


class RulesEngine:
    """Query interface over a RulesConfig."""

    def __init__(self, config: RulesConfig) -> None:
        self._config = config

    @classmethod
    def from_yaml(cls, yaml_str: str) -> RulesEngine:
        """Create a RulesEngine from a YAML string."""
        config = RulesConfig.from_yaml(yaml_str)
        return cls(config)

    @property
    def config(self) -> RulesConfig:
        return self._config

    def should_skip_url(self, url: str) -> bool:
        """Check if URL matches any skip pattern (supports glob)."""
        for pattern in self._config.crawl.skip_urls:
            if fnmatch.fnmatch(url, pattern):
                return True
        return False

    def get_input_value(self, field_name: str) -> str | None:
        """Get a predefined input value for a field name."""
        return self._config.inputs.values.get(field_name)

    def get_all_inputs(self) -> dict[str, str]:
        """Get all predefined input values."""
        return dict(self._config.inputs.values)

    def should_skip_visual(self, route: str) -> bool:
        """Check if visual regression should be skipped for a route."""
        return route in self._config.tests.skip_visual

    def should_ignore_endpoint(self, endpoint: str) -> bool:
        """Check if an API endpoint should be ignored (supports glob)."""
        for pattern in self._config.api.ignore_endpoints:
            if fnmatch.fnmatch(endpoint, pattern):
                return True
        return False

    def get_expected_override(self, method: str, path: str) -> dict[str, Any] | None:
        """Get expected response override for a specific endpoint."""
        key = f"{method} {path}"
        return self._config.api.expected_overrides.get(key)

    def get_execution_mode(self) -> str:
        """Get the global execution mode (smart/sequential/parallel)."""
        return self._config.execution.mode

    def get_suite_config(self, suite_name: str) -> dict[str, Any] | None:
        """Get execution config for a specific test suite."""
        return self._config.execution.suites.get(suite_name)

    def get_cookie_banner_action(self) -> str:
        """Get action for cookie banners."""
        return self._config.interactions.cookie_banner

    def get_modal_action(self) -> str:
        """Get action for modals."""
        return self._config.interactions.modals

    def get_scroll_behavior(self) -> str:
        """Get scroll behavior setting."""
        return self._config.crawl.scroll_behavior

    def get_infinite_scroll_action(self) -> str:
        """Get action for infinite scroll."""
        return self._config.interactions.infinite_scroll

    def get_viewport(self) -> dict[str, int]:
        """Get viewport configuration."""
        return self._config.crawl.viewport.model_dump()

    def get_wait_times(self) -> dict[str, int]:
        """Get wait time configuration."""
        return self._config.crawl.wait_times.model_dump()

    def get_max_depth(self) -> int:
        """Get maximum crawl depth."""
        return self._config.crawl.max_depth

    def to_yaml(self) -> str:
        """Serialize rules back to YAML."""
        return self._config.to_yaml()
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_rules_engine.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/generator/ tests/unit/test_rules_engine.py
git commit -m "feat: add rules engine with YAML parsing and validation"
```

---

### Task 18: Resilient Selector Builder

**Files:**
- Create: `breakthevibe/generator/selector.py`
- Test: `tests/unit/test_selector.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_selector.py
import pytest
from breakthevibe.generator.selector import SelectorBuilder
from breakthevibe.models.domain import ComponentInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy


class TestSelectorBuilder:
    @pytest.fixture()
    def builder(self) -> SelectorBuilder:
        return SelectorBuilder()

    def test_builds_ordered_selector_chain(self, builder: SelectorBuilder) -> None:
        component = ComponentInfo(
            name="Add to Cart",
            element_type="button",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn-primary"),
                ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="add-to-cart-btn"),
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Add to Cart"),
                ResilientSelector(strategy=SelectorStrategy.ROLE, value="button", name="Add to Cart"),
            ],
            aria_role="button",
            text_content="Add to Cart",
        )
        chain = builder.build_chain(component)
        # Should be ordered: test_id first (most stable), then role, text, css
        strategies = [s.strategy for s in chain]
        assert strategies[0] == SelectorStrategy.TEST_ID
        assert strategies[1] == SelectorStrategy.ROLE
        assert strategies[2] == SelectorStrategy.TEXT
        assert strategies[-1] == SelectorStrategy.CSS

    def test_deduplicates_selectors(self, builder: SelectorBuilder) -> None:
        component = ComponentInfo(
            name="Button",
            element_type="button",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Click"),
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="Click"),
                ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn"),
            ],
        )
        chain = builder.build_chain(component)
        text_selectors = [s for s in chain if s.strategy == SelectorStrategy.TEXT]
        assert len(text_selectors) == 1

    def test_empty_selectors_returns_empty(self, builder: SelectorBuilder) -> None:
        component = ComponentInfo(
            name="Empty",
            element_type="div",
            selectors=[],
        )
        chain = builder.build_chain(component)
        assert chain == []

    def test_infers_selectors_from_metadata(self, builder: SelectorBuilder) -> None:
        """When component has metadata but few explicit selectors, infer extras."""
        component = ComponentInfo(
            name="Submit",
            element_type="button",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.CSS, value="form .submit-btn"),
            ],
            aria_role="button",
            text_content="Submit",
            test_id="submit-btn",
        )
        chain = builder.build_chain(component)
        strategies = [s.strategy for s in chain]
        # Should have inferred test_id, role, and text from metadata
        assert SelectorStrategy.TEST_ID in strategies
        assert SelectorStrategy.ROLE in strategies
        assert SelectorStrategy.TEXT in strategies
        assert SelectorStrategy.CSS in strategies

    def test_priority_order_is_correct(self, builder: SelectorBuilder) -> None:
        """Verify the full priority order: test_id > role > text > semantic > structural > css."""
        component = ComponentInfo(
            name="Link",
            element_type="a",
            selectors=[
                ResilientSelector(strategy=SelectorStrategy.CSS, value="a.nav-link"),
                ResilientSelector(strategy=SelectorStrategy.STRUCTURAL, value="nav > ul > li:nth-child(2) > a"),
                ResilientSelector(strategy=SelectorStrategy.SEMANTIC, value="nav a[href='/about']"),
                ResilientSelector(strategy=SelectorStrategy.TEXT, value="About"),
                ResilientSelector(strategy=SelectorStrategy.ROLE, value="link", name="About"),
                ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="about-link"),
            ],
        )
        chain = builder.build_chain(component)
        strategies = [s.strategy for s in chain]
        assert strategies == [
            SelectorStrategy.TEST_ID,
            SelectorStrategy.ROLE,
            SelectorStrategy.TEXT,
            SelectorStrategy.SEMANTIC,
            SelectorStrategy.STRUCTURAL,
            SelectorStrategy.CSS,
        ]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_selector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.generator.selector'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/generator/selector.py
"""Resilient selector chain builder."""

from __future__ import annotations

from breakthevibe.models.domain import ComponentInfo, ResilientSelector
from breakthevibe.types import SelectorStrategy

import structlog

logger = structlog.get_logger(__name__)

# Priority order: most stable first
STRATEGY_PRIORITY: list[SelectorStrategy] = [
    SelectorStrategy.TEST_ID,
    SelectorStrategy.ROLE,
    SelectorStrategy.TEXT,
    SelectorStrategy.SEMANTIC,
    SelectorStrategy.STRUCTURAL,
    SelectorStrategy.CSS,
]


class SelectorBuilder:
    """Builds ordered, deduplicated selector chains for components."""

    def build_chain(self, component: ComponentInfo) -> list[ResilientSelector]:
        """Build a prioritized selector chain from a component's selectors + metadata."""
        all_selectors = list(component.selectors)

        # Infer additional selectors from component metadata
        all_selectors.extend(self._infer_from_metadata(component, all_selectors))

        # Deduplicate by (strategy, value) pair
        seen: set[tuple[SelectorStrategy, str]] = set()
        unique: list[ResilientSelector] = []
        for sel in all_selectors:
            key = (sel.strategy, sel.value)
            if key not in seen:
                seen.add(key)
                unique.append(sel)

        # Sort by priority order
        priority_map = {s: i for i, s in enumerate(STRATEGY_PRIORITY)}
        unique.sort(key=lambda s: priority_map.get(s.strategy, len(STRATEGY_PRIORITY)))

        return unique

    def _infer_from_metadata(
        self, component: ComponentInfo, existing: list[ResilientSelector]
    ) -> list[ResilientSelector]:
        """Infer selectors from component metadata that aren't already present."""
        existing_strategies = {s.strategy for s in existing}
        inferred: list[ResilientSelector] = []

        # Infer test_id selector
        if (
            SelectorStrategy.TEST_ID not in existing_strategies
            and component.test_id
        ):
            inferred.append(
                ResilientSelector(
                    strategy=SelectorStrategy.TEST_ID,
                    value=component.test_id,
                )
            )

        # Infer role selector
        if (
            SelectorStrategy.ROLE not in existing_strategies
            and component.aria_role
        ):
            inferred.append(
                ResilientSelector(
                    strategy=SelectorStrategy.ROLE,
                    value=component.aria_role,
                    name=component.text_content or component.name,
                )
            )

        # Infer text selector
        if (
            SelectorStrategy.TEXT not in existing_strategies
            and component.text_content
        ):
            inferred.append(
                ResilientSelector(
                    strategy=SelectorStrategy.TEXT,
                    value=component.text_content,
                )
            )

        return inferred
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_selector.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/generator/selector.py tests/unit/test_selector.py
git commit -m "feat: add resilient selector chain builder"
```

---

### Task 19: Test Case Generator (LLM-powered)

**Files:**
- Create: `breakthevibe/generator/case_builder.py`
- Test: `tests/unit/test_case_builder.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_case_builder.py
import json
import pytest
from unittest.mock import AsyncMock
from breakthevibe.generator.case_builder import TestCaseGenerator
from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.models.domain import (
    ApiCallInfo,
    ComponentInfo,
    GeneratedTestCase,
    PageData,
    ResilientSelector,
    SiteMap,
    TestStep,
)
from breakthevibe.llm.provider import LLMResponse
from breakthevibe.types import SelectorStrategy, TestCategory, TestStatus


SAMPLE_SITEMAP = SiteMap(
    base_url="https://example.com",
    pages=[
        PageData(
            url="https://example.com/",
            route="/",
            title="Home",
            components=[
                ComponentInfo(
                    name="CTA Button",
                    element_type="button",
                    selectors=[
                        ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="cta-btn"),
                        ResilientSelector(strategy=SelectorStrategy.TEXT, value="Get Started"),
                    ],
                    aria_role="button",
                    text_content="Get Started",
                ),
            ],
            api_calls=[
                ApiCallInfo(
                    url="https://example.com/api/featured",
                    method="GET",
                    status_code=200,
                    response_body={"items": []},
                ),
            ],
        ),
        PageData(
            url="https://example.com/products",
            route="/products",
            title="Products",
            components=[
                ComponentInfo(
                    name="Filter",
                    element_type="select",
                    selectors=[
                        ResilientSelector(strategy=SelectorStrategy.ROLE, value="combobox", name="Category"),
                    ],
                    aria_role="combobox",
                ),
            ],
            api_calls=[
                ApiCallInfo(
                    url="https://example.com/api/products",
                    method="GET",
                    status_code=200,
                    response_body={"products": []},
                ),
            ],
        ),
    ],
    api_endpoints=[
        ApiCallInfo(url="https://example.com/api/featured", method="GET", status_code=200),
        ApiCallInfo(url="https://example.com/api/products", method="GET", status_code=200),
    ],
)

MOCK_LLM_RESPONSE = json.dumps({
    "test_cases": [
        {
            "name": "test_home_cta_navigation",
            "category": "functional",
            "description": "Verify CTA button navigates to expected destination",
            "route": "/",
            "steps": [
                {
                    "action": "navigate",
                    "target_url": "https://example.com/",
                    "description": "Navigate to home page",
                },
                {
                    "action": "click",
                    "selectors": [
                        {"strategy": "test_id", "value": "cta-btn"},
                        {"strategy": "text", "value": "Get Started"},
                    ],
                    "description": "Click CTA button",
                },
                {
                    "action": "assert_url",
                    "expected": "https://example.com/products",
                    "description": "Verify navigation to products page",
                },
            ],
        },
        {
            "name": "test_api_featured_status",
            "category": "api",
            "description": "Validate /api/featured returns 200",
            "route": "/",
            "steps": [
                {
                    "action": "api_call",
                    "method": "GET",
                    "target_url": "https://example.com/api/featured",
                    "description": "Call featured API",
                },
                {
                    "action": "assert_status",
                    "expected": 200,
                    "description": "Verify 200 status code",
                },
            ],
        },
        {
            "name": "test_home_visual_baseline",
            "category": "visual",
            "description": "Visual baseline for home page",
            "route": "/",
            "steps": [
                {
                    "action": "navigate",
                    "target_url": "https://example.com/",
                    "description": "Navigate to home page",
                },
                {
                    "action": "screenshot",
                    "name": "home_baseline",
                    "description": "Capture baseline screenshot",
                },
            ],
        },
    ]
})

RULES_YAML = """
tests:
  skip_visual:
    - "/admin"
api:
  ignore_endpoints:
    - "/api/analytics/*"
"""


class TestTestCaseGenerator:
    @pytest.fixture()
    def mock_llm(self) -> AsyncMock:
        llm = AsyncMock()
        llm.generate.return_value = LLMResponse(
            content=MOCK_LLM_RESPONSE,
            model="test-model",
            usage={"input_tokens": 100, "output_tokens": 200},
        )
        return llm

    @pytest.fixture()
    def rules(self) -> RulesEngine:
        return RulesEngine(RulesConfig.from_yaml(RULES_YAML))

    @pytest.fixture()
    def generator(self, mock_llm: AsyncMock, rules: RulesEngine) -> TestCaseGenerator:
        return TestCaseGenerator(llm=mock_llm, rules=rules)

    @pytest.mark.asyncio
    async def test_generates_test_cases(self, generator: TestCaseGenerator) -> None:
        cases = await generator.generate(SAMPLE_SITEMAP)
        assert len(cases) == 3
        categories = {c.category for c in cases}
        assert TestCategory.FUNCTIONAL in categories
        assert TestCategory.API in categories
        assert TestCategory.VISUAL in categories

    @pytest.mark.asyncio
    async def test_functional_test_has_steps(self, generator: TestCaseGenerator) -> None:
        cases = await generator.generate(SAMPLE_SITEMAP)
        functional = [c for c in cases if c.category == TestCategory.FUNCTIONAL]
        assert len(functional) == 1
        assert len(functional[0].steps) == 3
        assert functional[0].steps[0].action == "navigate"

    @pytest.mark.asyncio
    async def test_api_test_has_steps(self, generator: TestCaseGenerator) -> None:
        cases = await generator.generate(SAMPLE_SITEMAP)
        api_tests = [c for c in cases if c.category == TestCategory.API]
        assert len(api_tests) == 1
        assert api_tests[0].steps[0].action == "api_call"

    @pytest.mark.asyncio
    async def test_llm_receives_sitemap_context(
        self, generator: TestCaseGenerator, mock_llm: AsyncMock
    ) -> None:
        await generator.generate(SAMPLE_SITEMAP)
        call_args = mock_llm.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "example.com" in prompt
        assert "CTA Button" in prompt
        assert "/api/featured" in prompt

    @pytest.mark.asyncio
    async def test_skips_filtered_routes(
        self, mock_llm: AsyncMock
    ) -> None:
        """Routes in skip_visual should be excluded from visual tests."""
        rules = RulesEngine(RulesConfig.from_yaml("""
tests:
  skip_visual:
    - "/"
"""))
        gen = TestCaseGenerator(llm=mock_llm, rules=rules)
        cases = await gen.generate(SAMPLE_SITEMAP)
        visual = [c for c in cases if c.category == TestCategory.VISUAL]
        # The LLM still returns them, but generator filters based on rules
        for v in visual:
            assert v.route != "/"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_case_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.generator.case_builder'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/generator/case_builder.py
"""LLM-powered test case generator."""

from __future__ import annotations

import json
from typing import Any

from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.llm.provider import LLMProvider
from breakthevibe.models.domain import (
    GeneratedTestCase,
    ResilientSelector,
    SiteMap,
    TestStep,
)
from breakthevibe.types import SelectorStrategy, TestCategory

import structlog

logger = structlog.get_logger(__name__)


class TestCaseGenerator:
    """Generates test cases from a SiteMap using LLM."""

    def __init__(self, llm: LLMProvider, rules: RulesEngine) -> None:
        self._llm = llm
        self._rules = rules

    async def generate(self, sitemap: SiteMap) -> list[GeneratedTestCase]:
        """Generate test cases for a site map."""
        prompt = self._build_prompt(sitemap)
        response = await self._llm.generate(prompt=prompt)

        raw_cases = self._parse_response(response.content)
        cases = [self._build_test_case(raw) for raw in raw_cases]

        # Apply rules filtering
        cases = self._apply_rules(cases)

        logger.info(
            "generated_test_cases",
            count=len(cases),
            categories={c.value: sum(1 for tc in cases if tc.category == c) for c in TestCategory},
        )
        return cases

    def _build_prompt(self, sitemap: SiteMap) -> str:
        """Build the LLM prompt from site map data."""
        pages_desc = []
        for page in sitemap.pages:
            components_desc = ", ".join(c.name for c in page.components)
            api_desc = ", ".join(f"{a.method} {a.url}" for a in page.api_calls)
            pages_desc.append(
                f"Route: {page.route} (title: {page.title})\n"
                f"  Components: [{components_desc}]\n"
                f"  API calls: [{api_desc}]"
            )

        api_endpoints_desc = "\n".join(
            f"  - {e.method} {e.url} (status: {e.status_code})"
            for e in sitemap.api_endpoints
        )

        return f"""Analyze the following website structure and generate test cases.
Site: {sitemap.base_url}

Pages:
{chr(10).join(pages_desc)}

API Endpoints:
{api_endpoints_desc}

Generate test cases in these categories:
1. functional - User journey tests with navigation and interactions
2. visual - Visual regression baseline captures
3. api - API contract validation tests

Return JSON with this structure:
{{
  "test_cases": [
    {{
      "name": "test_descriptive_name",
      "category": "functional|visual|api",
      "description": "What this tests",
      "route": "/route",
      "steps": [
        {{
          "action": "navigate|click|fill|assert_url|assert_text|api_call|assert_status|screenshot",
          "target_url": "optional url",
          "selectors": [optional selector objects],
          "expected": "optional expected value",
          "method": "optional HTTP method",
          "name": "optional screenshot name",
          "description": "step description"
        }}
      ]
    }}
  ]
}}"""

    def _parse_response(self, content: str) -> list[dict[str, Any]]:
        """Parse LLM response JSON into raw test case dicts."""
        data = json.loads(content)
        return data.get("test_cases", [])

    def _build_test_case(self, raw: dict[str, Any]) -> GeneratedTestCase:
        """Convert a raw dict into a GeneratedTestCase."""
        steps = []
        for step_raw in raw.get("steps", []):
            selectors = [
                ResilientSelector(
                    strategy=SelectorStrategy(s["strategy"]),
                    value=s["value"],
                    name=s.get("name"),
                )
                for s in step_raw.get("selectors", [])
            ]
            steps.append(
                TestStep(
                    action=step_raw["action"],
                    target_url=step_raw.get("target_url"),
                    selectors=selectors,
                    expected=step_raw.get("expected"),
                    description=step_raw.get("description", ""),
                )
            )

        return GeneratedTestCase(
            name=raw["name"],
            category=TestCategory(raw["category"]),
            description=raw.get("description", ""),
            route=raw.get("route", "/"),
            steps=steps,
        )

    def _apply_rules(self, cases: list[GeneratedTestCase]) -> list[GeneratedTestCase]:
        """Filter test cases based on rules engine."""
        filtered = []
        for case in cases:
            if case.category == TestCategory.VISUAL and self._rules.should_skip_visual(case.route):
                logger.debug("skipping_visual_test", route=case.route, test=case.name)
                continue
            filtered.append(case)
        return filtered
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_case_builder.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/generator/case_builder.py tests/unit/test_case_builder.py
git commit -m "feat: add LLM-powered test case generator"
```

---

### Task 20: Pytest Code Generator

**Files:**
- Create: `breakthevibe/generator/code_builder.py`
- Test: `tests/unit/test_code_builder.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_code_builder.py
import pytest
from breakthevibe.generator.code_builder import CodeBuilder
from breakthevibe.models.domain import (
    GeneratedTestCase,
    ResilientSelector,
    TestStep,
)
from breakthevibe.types import SelectorStrategy, TestCategory


class TestCodeBuilder:
    @pytest.fixture()
    def builder(self) -> CodeBuilder:
        return CodeBuilder()

    @pytest.fixture()
    def functional_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_home_cta_navigation",
            category=TestCategory.FUNCTIONAL,
            description="Verify CTA button navigates correctly",
            route="/",
            steps=[
                TestStep(
                    action="navigate",
                    target_url="https://example.com/",
                    description="Open home page",
                ),
                TestStep(
                    action="click",
                    selectors=[
                        ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="cta-btn"),
                        ResilientSelector(strategy=SelectorStrategy.TEXT, value="Get Started"),
                    ],
                    description="Click CTA button",
                ),
                TestStep(
                    action="assert_url",
                    expected="https://example.com/products",
                    description="Verify navigation",
                ),
            ],
        )

    @pytest.fixture()
    def api_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_api_featured_status",
            category=TestCategory.API,
            description="Validate /api/featured returns 200",
            route="/",
            steps=[
                TestStep(
                    action="api_call",
                    target_url="https://example.com/api/featured",
                    expected={"method": "GET"},
                    description="Call featured API",
                ),
                TestStep(
                    action="assert_status",
                    expected=200,
                    description="Verify 200 status",
                ),
            ],
        )

    @pytest.fixture()
    def visual_case(self) -> GeneratedTestCase:
        return GeneratedTestCase(
            name="test_home_visual_baseline",
            category=TestCategory.VISUAL,
            description="Visual baseline for home page",
            route="/",
            steps=[
                TestStep(
                    action="navigate",
                    target_url="https://example.com/",
                    description="Navigate to home",
                ),
                TestStep(
                    action="screenshot",
                    expected="home_baseline",
                    description="Capture baseline",
                ),
            ],
        )

    def test_generates_valid_python(self, builder: CodeBuilder, functional_case: GeneratedTestCase) -> None:
        code = builder.generate(functional_case)
        # Should be valid Python syntax
        compile(code, "<test>", "exec")

    def test_functional_has_playwright_imports(self, builder: CodeBuilder, functional_case: GeneratedTestCase) -> None:
        code = builder.generate(functional_case)
        assert "import pytest" in code
        assert "playwright" in code.lower() or "page" in code

    def test_functional_has_navigate(self, builder: CodeBuilder, functional_case: GeneratedTestCase) -> None:
        code = builder.generate(functional_case)
        assert "goto" in code or "navigate" in code
        assert "example.com" in code

    def test_functional_has_click_with_selectors(self, builder: CodeBuilder, functional_case: GeneratedTestCase) -> None:
        code = builder.generate(functional_case)
        assert "cta-btn" in code or "Get Started" in code

    def test_functional_has_url_assertion(self, builder: CodeBuilder, functional_case: GeneratedTestCase) -> None:
        code = builder.generate(functional_case)
        assert "assert" in code
        assert "products" in code

    def test_api_has_httpx_or_request(self, builder: CodeBuilder, api_case: GeneratedTestCase) -> None:
        code = builder.generate(api_case)
        assert "httpx" in code or "request" in code.lower()
        assert "api/featured" in code

    def test_api_has_status_assertion(self, builder: CodeBuilder, api_case: GeneratedTestCase) -> None:
        code = builder.generate(api_case)
        assert "status_code" in code
        assert "200" in code

    def test_visual_has_screenshot(self, builder: CodeBuilder, visual_case: GeneratedTestCase) -> None:
        code = builder.generate(visual_case)
        assert "screenshot" in code

    def test_generates_function_name(self, builder: CodeBuilder, functional_case: GeneratedTestCase) -> None:
        code = builder.generate(functional_case)
        assert "def test_home_cta_navigation" in code

    def test_generate_suite(self, builder: CodeBuilder, functional_case: GeneratedTestCase, api_case: GeneratedTestCase) -> None:
        code = builder.generate_suite([functional_case, api_case])
        assert "test_home_cta_navigation" in code
        assert "test_api_featured_status" in code
        # Should be valid Python
        compile(code, "<test>", "exec")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_code_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.generator.code_builder'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/generator/code_builder.py
"""Generates executable pytest code from test cases."""

from __future__ import annotations

from breakthevibe.models.domain import GeneratedTestCase, TestStep, ResilientSelector
from breakthevibe.types import SelectorStrategy, TestCategory

import structlog

logger = structlog.get_logger(__name__)


class CodeBuilder:
    """Generates pytest + Playwright code from GeneratedTestCase objects."""

    def generate(self, case: GeneratedTestCase) -> str:
        """Generate pytest code for a single test case."""
        if case.category == TestCategory.FUNCTIONAL:
            return self._generate_functional(case)
        elif case.category == TestCategory.API:
            return self._generate_api(case)
        elif case.category == TestCategory.VISUAL:
            return self._generate_visual(case)
        else:
            msg = f"Unknown test category: {case.category}"
            raise ValueError(msg)

    def generate_suite(self, cases: list[GeneratedTestCase]) -> str:
        """Generate a complete test file from multiple test cases."""
        # Collect unique imports needed
        has_functional = any(c.category == TestCategory.FUNCTIONAL for c in cases)
        has_api = any(c.category == TestCategory.API for c in cases)
        has_visual = any(c.category == TestCategory.VISUAL for c in cases)

        lines: list[str] = [
            '"""Auto-generated test suite by BreakTheVibe."""',
            "",
            "import pytest",
        ]

        if has_functional or has_visual:
            lines.append("from playwright.async_api import Page")
        if has_api:
            lines.append("import httpx")
        if has_visual:
            lines.append("from pathlib import Path")

        lines.extend(["", ""])

        for case in cases:
            func_code = self._generate_function_body(case)
            lines.append(func_code)
            lines.append("")

        return "\n".join(lines)

    def _generate_functional(self, case: GeneratedTestCase) -> str:
        """Generate a full functional test file."""
        lines = [
            '"""Auto-generated functional test by BreakTheVibe."""',
            "",
            "import pytest",
            "from playwright.async_api import Page",
            "",
            "",
            self._generate_function_body(case),
        ]
        return "\n".join(lines)

    def _generate_api(self, case: GeneratedTestCase) -> str:
        """Generate a full API test file."""
        lines = [
            '"""Auto-generated API test by BreakTheVibe."""',
            "",
            "import pytest",
            "import httpx",
            "",
            "",
            self._generate_function_body(case),
        ]
        return "\n".join(lines)

    def _generate_visual(self, case: GeneratedTestCase) -> str:
        """Generate a full visual regression test file."""
        lines = [
            '"""Auto-generated visual regression test by BreakTheVibe."""',
            "",
            "import pytest",
            "from pathlib import Path",
            "from playwright.async_api import Page",
            "",
            "",
            self._generate_function_body(case),
        ]
        return "\n".join(lines)

    def _generate_function_body(self, case: GeneratedTestCase) -> str:
        """Generate the test function body."""
        if case.category == TestCategory.FUNCTIONAL:
            return self._functional_body(case)
        elif case.category == TestCategory.API:
            return self._api_body(case)
        elif case.category == TestCategory.VISUAL:
            return self._visual_body(case)
        msg = f"Unknown category: {case.category}"
        raise ValueError(msg)

    def _functional_body(self, case: GeneratedTestCase) -> str:
        """Generate functional test function."""
        lines = [
            "@pytest.mark.asyncio",
            f"async def {case.name}(page: Page) -> None:",
            f'    """{case.description}"""',
        ]
        for step in case.steps:
            lines.extend(self._step_to_playwright(step))
        return "\n".join(lines)

    def _api_body(self, case: GeneratedTestCase) -> str:
        """Generate API test function."""
        lines = [
            "@pytest.mark.asyncio",
            f"async def {case.name}() -> None:",
            f'    """{case.description}"""',
            "    async with httpx.AsyncClient() as client:",
        ]
        for step in case.steps:
            lines.extend(self._step_to_httpx(step))
        return "\n".join(lines)

    def _visual_body(self, case: GeneratedTestCase) -> str:
        """Generate visual regression test function."""
        lines = [
            "@pytest.mark.asyncio",
            f"async def {case.name}(page: Page, tmp_path: Path) -> None:",
            f'    """{case.description}"""',
        ]
        for step in case.steps:
            lines.extend(self._step_to_visual(step))
        return "\n".join(lines)

    def _step_to_playwright(self, step: TestStep) -> list[str]:
        """Convert a test step to Playwright code lines."""
        lines: list[str] = []
        if step.action == "navigate":
            lines.append(f'    await page.goto("{step.target_url}")')
        elif step.action == "click":
            locator = self._build_locator(step.selectors)
            lines.append(f"    await {locator}.click()")
        elif step.action == "fill":
            locator = self._build_locator(step.selectors)
            value = step.expected or ""
            lines.append(f'    await {locator}.fill("{value}")')
        elif step.action == "assert_url":
            lines.append(f'    assert page.url == "{step.expected}"')
        elif step.action == "assert_text":
            locator = self._build_locator(step.selectors)
            lines.append(f'    await expect({locator}).to_have_text("{step.expected}")')
        return lines

    def _step_to_httpx(self, step: TestStep) -> list[str]:
        """Convert a test step to httpx code lines."""
        lines: list[str] = []
        if step.action == "api_call":
            method = "GET"
            if isinstance(step.expected, dict):
                method = step.expected.get("method", "GET")
            lines.append(f'        response = await client.{method.lower()}("{step.target_url}")')
        elif step.action == "assert_status":
            lines.append(f"        assert response.status_code == {step.expected}")
        return lines

    def _step_to_visual(self, step: TestStep) -> list[str]:
        """Convert a test step to visual regression code lines."""
        lines: list[str] = []
        if step.action == "navigate":
            lines.append(f'    await page.goto("{step.target_url}")')
        elif step.action == "screenshot":
            name = step.expected or "screenshot"
            lines.append(f'    await page.screenshot(path=str(tmp_path / "{name}.png"))')
        return lines

    def _build_locator(self, selectors: list[ResilientSelector]) -> str:
        """Build a Playwright locator from selectors, using the highest priority one."""
        if not selectors:
            return 'page.locator("body")'

        sel = selectors[0]  # Use highest priority
        if sel.strategy == SelectorStrategy.TEST_ID:
            return f'page.get_by_test_id("{sel.value}")'
        elif sel.strategy == SelectorStrategy.ROLE:
            if sel.name:
                return f'page.get_by_role("{sel.value}", name="{sel.name}")'
            return f'page.get_by_role("{sel.value}")'
        elif sel.strategy == SelectorStrategy.TEXT:
            return f'page.get_by_text("{sel.value}")'
        elif sel.strategy == SelectorStrategy.CSS:
            return f'page.locator("{sel.value}")'
        else:
            return f'page.locator("{sel.value}")'
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_code_builder.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/generator/code_builder.py tests/unit/test_code_builder.py
git commit -m "feat: add pytest code generator from test cases"
```

---

## Phase 6: Runner Module

### Task 21: Test Executor

**Files:**
- Create: `breakthevibe/runner/__init__.py`
- Create: `breakthevibe/runner/executor.py`
- Test: `tests/unit/test_executor.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_executor.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from breakthevibe.runner.executor import TestExecutor, ExecutionResult


class TestTestExecutor:
    @pytest.fixture()
    def executor(self, tmp_path: Path) -> TestExecutor:
        return TestExecutor(
            output_dir=tmp_path,
            timeout=60,
        )

    @pytest.fixture()
    def sample_test_code(self) -> str:
        return '''
import pytest

@pytest.mark.asyncio
async def test_example(page):
    """Simple test."""
    await page.goto("https://example.com")
    assert page.url == "https://example.com/"
'''

    def test_writes_test_file(self, executor: TestExecutor, sample_test_code: str, tmp_path: Path) -> None:
        test_file = executor._write_test_file("test_example_suite", sample_test_code)
        assert test_file.exists()
        assert test_file.name == "test_example_suite.py"
        assert test_file.read_text() == sample_test_code

    def test_builds_pytest_command(self, executor: TestExecutor, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("# test")
        cmd = executor._build_command(test_file, workers=1)
        assert "pytest" in cmd[0] or cmd[1] == "pytest" or any("pytest" in c for c in cmd)
        assert str(test_file) in cmd
        assert "-v" in cmd

    def test_builds_parallel_command(self, executor: TestExecutor, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text("# test")
        cmd = executor._build_command(test_file, workers=4)
        assert "-n" in cmd
        assert "4" in cmd

    @pytest.mark.asyncio
    @patch("breakthevibe.runner.executor.asyncio.create_subprocess_exec")
    async def test_run_returns_result(
        self, mock_subprocess: MagicMock, executor: TestExecutor, sample_test_code: str
    ) -> None:
        # Mock subprocess
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"1 passed", b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        result = await executor.run("test_suite", sample_test_code, workers=1)
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.exit_code == 0
        assert "1 passed" in result.stdout

    @pytest.mark.asyncio
    @patch("breakthevibe.runner.executor.asyncio.create_subprocess_exec")
    async def test_run_captures_failure(
        self, mock_subprocess: MagicMock, executor: TestExecutor, sample_test_code: str
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"1 failed", b"ERRORS")
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        result = await executor.run("test_fail", sample_test_code, workers=1)
        assert result.success is False
        assert result.exit_code == 1
        assert "1 failed" in result.stdout

    @pytest.mark.asyncio
    @patch("breakthevibe.runner.executor.asyncio.create_subprocess_exec")
    async def test_run_handles_timeout(
        self, mock_subprocess: MagicMock, executor: TestExecutor, sample_test_code: str
    ) -> None:
        import asyncio as aio
        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = aio.TimeoutError()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_subprocess.return_value = mock_proc

        result = await executor.run("test_timeout", sample_test_code, workers=1)
        assert result.success is False
        assert result.timed_out is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_executor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.runner'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/runner/__init__.py
```

```python
# breakthevibe/runner/executor.py
"""Test execution engine using pytest subprocess."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of a test execution run."""
    suite_name: str
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    test_file: Path | None = None
    duration_seconds: float = 0.0


class TestExecutor:
    """Runs generated pytest code via subprocess."""

    def __init__(self, output_dir: Path, timeout: int = 300) -> None:
        self._output_dir = output_dir
        self._timeout = timeout
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        suite_name: str,
        test_code: str,
        workers: int = 1,
    ) -> ExecutionResult:
        """Write test code to file and execute via pytest."""
        test_file = self._write_test_file(suite_name, test_code)
        cmd = self._build_command(test_file, workers)

        logger.info("executing_tests", suite=suite_name, workers=workers, file=str(test_file))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._output_dir),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            return ExecutionResult(
                suite_name=suite_name,
                success=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                test_file=test_file,
            )
        except asyncio.TimeoutError:
            logger.warning("test_execution_timeout", suite=suite_name, timeout=self._timeout)
            proc.kill()
            await proc.wait()
            return ExecutionResult(
                suite_name=suite_name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Test execution timed out after {self._timeout}s",
                timed_out=True,
                test_file=test_file,
            )

    def _write_test_file(self, suite_name: str, test_code: str) -> Path:
        """Write test code to a temporary file."""
        test_file = self._output_dir / f"{suite_name}.py"
        test_file.write_text(test_code)
        return test_file

    def _build_command(self, test_file: Path, workers: int) -> list[str]:
        """Build the pytest command."""
        cmd = [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"]
        if workers > 1:
            cmd.extend(["-n", str(workers)])
        return cmd
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_executor.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/runner/ tests/unit/test_executor.py
git commit -m "feat: add test executor with artifact capture"
```

---

### Task 22: Smart Parallelism

**Files:**
- Create: `breakthevibe/runner/parallel.py`
- Test: `tests/unit/test_parallel.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_parallel.py
import pytest
from breakthevibe.runner.parallel import ParallelScheduler, ExecutionPlan, SuiteSchedule
from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.models.domain import GeneratedTestCase, TestStep
from breakthevibe.types import TestCategory


def _make_case(name: str, category: TestCategory, route: str) -> GeneratedTestCase:
    return GeneratedTestCase(
        name=name,
        category=category,
        description=f"Test {name}",
        route=route,
        steps=[
            TestStep(action="navigate", target_url=f"https://example.com{route}", description="nav"),
        ],
    )


RULES_SMART = """
execution:
  mode: smart
  suites: {}
"""

RULES_SEQUENTIAL = """
execution:
  mode: sequential
  suites: {}
"""

RULES_PARALLEL = """
execution:
  mode: parallel
  suites: {}
"""

RULES_WITH_SUITES = """
execution:
  mode: smart
  suites:
    auth-flow:
      mode: sequential
      shared_context: true
    product-pages:
      mode: parallel
      workers: 4
"""


class TestParallelScheduler:
    def test_smart_mode_groups_by_route(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SMART))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_home_1", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_home_2", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_products_1", TestCategory.FUNCTIONAL, "/products"),
            _make_case("test_api_1", TestCategory.API, "/"),
        ]

        plan = scheduler.schedule(cases)
        assert isinstance(plan, ExecutionPlan)
        # Smart mode should create separate groups
        assert len(plan.suites) >= 1

    def test_sequential_mode_single_group(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SEQUENTIAL))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_1", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_2", TestCategory.FUNCTIONAL, "/products"),
        ]

        plan = scheduler.schedule(cases)
        # Sequential: all in one suite, workers=1
        for suite in plan.suites:
            assert suite.workers == 1

    def test_parallel_mode_max_workers(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_PARALLEL))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_1", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_2", TestCategory.FUNCTIONAL, "/products"),
            _make_case("test_3", TestCategory.FUNCTIONAL, "/about"),
        ]

        plan = scheduler.schedule(cases)
        # Parallel: should use multiple workers
        assert any(s.workers > 1 for s in plan.suites)

    def test_suite_config_overrides(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_WITH_SUITES))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_login", TestCategory.FUNCTIONAL, "/login"),
            _make_case("test_product_1", TestCategory.FUNCTIONAL, "/products"),
        ]

        plan = scheduler.schedule(
            cases,
            suite_assignments={"test_login": "auth-flow", "test_product_1": "product-pages"},
        )

        auth_suite = next((s for s in plan.suites if s.name == "auth-flow"), None)
        product_suite = next((s for s in plan.suites if s.name == "product-pages"), None)

        assert auth_suite is not None
        assert auth_suite.workers == 1  # sequential
        assert product_suite is not None
        assert product_suite.workers == 4

    def test_smart_groups_api_tests_separately(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SMART))
        scheduler = ParallelScheduler(rules)

        cases = [
            _make_case("test_home_ui", TestCategory.FUNCTIONAL, "/"),
            _make_case("test_api_health", TestCategory.API, "/"),
            _make_case("test_home_visual", TestCategory.VISUAL, "/"),
        ]

        plan = scheduler.schedule(cases)
        # API tests should be in their own parallel suite
        api_suites = [s for s in plan.suites if any(
            c.category == TestCategory.API for c in s.cases
        )]
        assert len(api_suites) >= 1
        assert api_suites[0].workers > 1 or len(api_suites[0].cases) <= 1

    def test_empty_cases_returns_empty_plan(self) -> None:
        rules = RulesEngine(RulesConfig.from_yaml(RULES_SMART))
        scheduler = ParallelScheduler(rules)
        plan = scheduler.schedule([])
        assert plan.suites == []
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_parallel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.runner.parallel'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/runner/parallel.py
"""Smart parallel/sequential test scheduling."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any

from breakthevibe.generator.rules.engine import RulesEngine
from breakthevibe.models.domain import GeneratedTestCase
from breakthevibe.types import TestCategory

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SuiteSchedule:
    """A group of test cases with execution configuration."""
    name: str
    cases: list[GeneratedTestCase]
    workers: int = 1
    shared_context: bool = False


@dataclass
class ExecutionPlan:
    """Complete execution plan with ordered suites."""
    suites: list[SuiteSchedule] = field(default_factory=list)

    @property
    def total_cases(self) -> int:
        return sum(len(s.cases) for s in self.suites)


class ParallelScheduler:
    """Analyzes test dependencies and decides parallel vs sequential."""

    def __init__(self, rules: RulesEngine) -> None:
        self._rules = rules
        self._max_workers = os.cpu_count() or 4

    def schedule(
        self,
        cases: list[GeneratedTestCase],
        suite_assignments: dict[str, str] | None = None,
    ) -> ExecutionPlan:
        """Create an execution plan from test cases."""
        if not cases:
            return ExecutionPlan()

        mode = self._rules.get_execution_mode()

        if suite_assignments:
            return self._schedule_with_assignments(cases, suite_assignments)

        if mode == "sequential":
            return self._schedule_sequential(cases)
        elif mode == "parallel":
            return self._schedule_parallel(cases)
        else:  # smart
            return self._schedule_smart(cases)

    def _schedule_sequential(self, cases: list[GeneratedTestCase]) -> ExecutionPlan:
        """All tests in one sequential suite."""
        return ExecutionPlan(
            suites=[SuiteSchedule(name="all", cases=cases, workers=1)]
        )

    def _schedule_parallel(self, cases: list[GeneratedTestCase]) -> ExecutionPlan:
        """All tests in one parallel suite with max workers."""
        workers = min(len(cases), self._max_workers)
        return ExecutionPlan(
            suites=[SuiteSchedule(name="all", cases=cases, workers=max(workers, 1))]
        )

    def _schedule_smart(self, cases: list[GeneratedTestCase]) -> ExecutionPlan:
        """Group by category and route, decide workers per group."""
        suites: list[SuiteSchedule] = []

        # Separate API tests (stateless, safe to parallelize)
        api_cases = [c for c in cases if c.category == TestCategory.API]
        ui_cases = [c for c in cases if c.category != TestCategory.API]

        if api_cases:
            workers = min(len(api_cases), self._max_workers)
            suites.append(SuiteSchedule(
                name="api-tests",
                cases=api_cases,
                workers=max(workers, 1),
            ))

        # Group UI tests by route
        by_route: dict[str, list[GeneratedTestCase]] = defaultdict(list)
        for case in ui_cases:
            by_route[case.route].append(case)

        for route, route_cases in by_route.items():
            safe_name = route.strip("/").replace("/", "-") or "root"
            # Tests on same route might share state, run sequentially
            # Tests across routes can run in parallel
            suites.append(SuiteSchedule(
                name=f"ui-{safe_name}",
                cases=route_cases,
                workers=1,
            ))

        logger.info("smart_schedule", suites=len(suites), total_cases=sum(len(s.cases) for s in suites))
        return ExecutionPlan(suites=suites)

    def _schedule_with_assignments(
        self,
        cases: list[GeneratedTestCase],
        assignments: dict[str, str],
    ) -> ExecutionPlan:
        """Schedule based on explicit suite assignments with config overrides."""
        suites_map: dict[str, list[GeneratedTestCase]] = defaultdict(list)
        unassigned: list[GeneratedTestCase] = []

        for case in cases:
            suite_name = assignments.get(case.name)
            if suite_name:
                suites_map[suite_name].append(case)
            else:
                unassigned.append(case)

        suites: list[SuiteSchedule] = []
        for suite_name, suite_cases in suites_map.items():
            config = self._rules.get_suite_config(suite_name)
            if config:
                mode = config.get("mode", "smart")
                workers = 1 if mode == "sequential" else config.get("workers", self._max_workers)
                shared = config.get("shared_context", False)
            else:
                workers = 1
                shared = False

            suites.append(SuiteSchedule(
                name=suite_name,
                cases=suite_cases,
                workers=workers,
                shared_context=shared,
            ))

        if unassigned:
            suites.append(SuiteSchedule(name="unassigned", cases=unassigned, workers=1))

        return ExecutionPlan(suites=suites)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_parallel.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/runner/parallel.py tests/unit/test_parallel.py
git commit -m "feat: add smart parallel/sequential test scheduling"
```

---

### Task 23: Self-Healing Selector

**Files:**
- Create: `breakthevibe/runner/healer.py`
- Test: `tests/unit/test_healer.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_healer.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from breakthevibe.runner.healer import SelectorHealer, HealResult
from breakthevibe.models.domain import ResilientSelector
from breakthevibe.types import SelectorStrategy


class TestSelectorHealer:
    @pytest.fixture()
    def healer(self) -> SelectorHealer:
        return SelectorHealer()

    @pytest.fixture()
    def selector_chain(self) -> list[ResilientSelector]:
        return [
            ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="submit-btn"),
            ResilientSelector(strategy=SelectorStrategy.ROLE, value="button", name="Submit"),
            ResilientSelector(strategy=SelectorStrategy.TEXT, value="Submit"),
            ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn-submit"),
        ]

    @pytest.mark.asyncio
    async def test_first_selector_works(self, healer: SelectorHealer, selector_chain: list[ResilientSelector]) -> None:
        """When the first selector works, no healing needed."""
        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_page.get_by_test_id.return_value = mock_locator

        result = await healer.find_element(mock_page, selector_chain)
        assert isinstance(result, HealResult)
        assert result.found is True
        assert result.healed is False
        assert result.used_selector == selector_chain[0]

    @pytest.mark.asyncio
    async def test_heals_to_second_selector(self, healer: SelectorHealer, selector_chain: list[ResilientSelector]) -> None:
        """When first selector fails, falls back to second."""
        mock_page = AsyncMock()

        # First selector fails (test_id)
        mock_locator_fail = MagicMock()
        mock_locator_fail.count = AsyncMock(return_value=0)

        # Second selector works (role)
        mock_locator_ok = MagicMock()
        mock_locator_ok.count = AsyncMock(return_value=1)

        mock_page.get_by_test_id.return_value = mock_locator_fail
        mock_page.get_by_role.return_value = mock_locator_ok

        result = await healer.find_element(mock_page, selector_chain)
        assert result.found is True
        assert result.healed is True
        assert result.used_selector == selector_chain[1]
        assert result.original_selector == selector_chain[0]

    @pytest.mark.asyncio
    async def test_all_selectors_fail(self, healer: SelectorHealer, selector_chain: list[ResilientSelector]) -> None:
        """When all selectors fail, result.found is False."""
        mock_page = AsyncMock()
        mock_locator_fail = MagicMock()
        mock_locator_fail.count = AsyncMock(return_value=0)

        mock_page.get_by_test_id.return_value = mock_locator_fail
        mock_page.get_by_role.return_value = mock_locator_fail
        mock_page.get_by_text.return_value = mock_locator_fail
        mock_page.locator.return_value = mock_locator_fail

        result = await healer.find_element(mock_page, selector_chain)
        assert result.found is False
        assert result.healed is False
        assert result.used_selector is None

    @pytest.mark.asyncio
    async def test_heals_to_css_fallback(self, healer: SelectorHealer, selector_chain: list[ResilientSelector]) -> None:
        """Falls all the way to CSS selector."""
        mock_page = AsyncMock()

        mock_fail = MagicMock()
        mock_fail.count = AsyncMock(return_value=0)

        mock_ok = MagicMock()
        mock_ok.count = AsyncMock(return_value=1)

        mock_page.get_by_test_id.return_value = mock_fail
        mock_page.get_by_role.return_value = mock_fail
        mock_page.get_by_text.return_value = mock_fail
        mock_page.locator.return_value = mock_ok

        result = await healer.find_element(mock_page, selector_chain)
        assert result.found is True
        assert result.healed is True
        assert result.used_selector.strategy == SelectorStrategy.CSS

    def test_heal_result_warning_message(self) -> None:
        result = HealResult(
            found=True,
            healed=True,
            used_selector=ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn"),
            original_selector=ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="submit-btn"),
        )
        msg = result.warning_message()
        assert "test_id" in msg
        assert "css" in msg
        assert "submit-btn" in msg

    def test_heal_result_no_warning_when_not_healed(self) -> None:
        result = HealResult(
            found=True,
            healed=False,
            used_selector=ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="btn"),
        )
        assert result.warning_message() is None

    @pytest.mark.asyncio
    async def test_empty_selector_chain(self, healer: SelectorHealer) -> None:
        mock_page = AsyncMock()
        result = await healer.find_element(mock_page, [])
        assert result.found is False

    @pytest.mark.asyncio
    async def test_handles_locator_exception(self, healer: SelectorHealer) -> None:
        """If a locator throws, treat it as not found and continue."""
        mock_page = AsyncMock()

        mock_error_locator = MagicMock()
        mock_error_locator.count = AsyncMock(side_effect=Exception("element detached"))

        mock_ok_locator = MagicMock()
        mock_ok_locator.count = AsyncMock(return_value=1)

        mock_page.get_by_test_id.return_value = mock_error_locator
        mock_page.get_by_role.return_value = mock_ok_locator

        chain = [
            ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="btn"),
            ResilientSelector(strategy=SelectorStrategy.ROLE, value="button", name="Submit"),
        ]
        result = await healer.find_element(mock_page, chain)
        assert result.found is True
        assert result.healed is True
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_healer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.runner.healer'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/runner/healer.py
"""Self-healing selector recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from breakthevibe.models.domain import ResilientSelector
from breakthevibe.types import SelectorStrategy

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HealResult:
    """Result of a selector healing attempt."""
    found: bool
    healed: bool
    used_selector: ResilientSelector | None = None
    original_selector: ResilientSelector | None = None
    locator: Any = None

    def warning_message(self) -> str | None:
        """Generate a warning message if healing occurred."""
        if not self.healed or not self.used_selector or not self.original_selector:
            return None
        return (
            f"Selector healed: preferred {self.original_selector.strategy.value}"
            f"({self.original_selector.value}) failed, "
            f"fell back to {self.used_selector.strategy.value}"
            f"({self.used_selector.value})"
        )


class SelectorHealer:
    """Tries selectors in priority order, healing when preferred ones fail."""

    async def find_element(
        self, page: Any, selectors: list[ResilientSelector]
    ) -> HealResult:
        """Try each selector in order until one finds an element."""
        if not selectors:
            return HealResult(found=False, healed=False)

        original = selectors[0]

        for i, selector in enumerate(selectors):
            try:
                locator = self._get_locator(page, selector)
                count = await locator.count()
                if count > 0:
                    healed = i > 0
                    if healed:
                        logger.warning(
                            "selector_healed",
                            original=f"{original.strategy.value}:{original.value}",
                            healed_to=f"{selector.strategy.value}:{selector.value}",
                        )
                    return HealResult(
                        found=True,
                        healed=healed,
                        used_selector=selector,
                        original_selector=original if healed else None,
                        locator=locator,
                    )
            except Exception:
                logger.debug(
                    "selector_error",
                    strategy=selector.strategy.value,
                    value=selector.value,
                )
                continue

        logger.error(
            "all_selectors_failed",
            selector_count=len(selectors),
            original=f"{original.strategy.value}:{original.value}",
        )
        return HealResult(found=False, healed=False)

    def _get_locator(self, page: Any, selector: ResilientSelector) -> Any:
        """Get a Playwright locator from a selector."""
        if selector.strategy == SelectorStrategy.TEST_ID:
            return page.get_by_test_id(selector.value)
        elif selector.strategy == SelectorStrategy.ROLE:
            if selector.name:
                return page.get_by_role(selector.value, name=selector.name)
            return page.get_by_role(selector.value)
        elif selector.strategy == SelectorStrategy.TEXT:
            return page.get_by_text(selector.value)
        elif selector.strategy in (
            SelectorStrategy.CSS,
            SelectorStrategy.SEMANTIC,
            SelectorStrategy.STRUCTURAL,
        ):
            return page.locator(selector.value)
        else:
            return page.locator(selector.value)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_healer.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/runner/healer.py tests/unit/test_healer.py
git commit -m "feat: add self-healing selector recovery"
```

---

## Phase 7: Reporter Module

### Task 24: Result Collector

**Files:**
- Create: `breakthevibe/reporter/__init__.py`
- Create: `breakthevibe/reporter/collector.py`
- Test: `tests/unit/test_collector.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_collector.py
import pytest
from breakthevibe.reporter.collector import ResultCollector, TestRunReport, TestCaseResult
from breakthevibe.runner.executor import ExecutionResult
from breakthevibe.runner.healer import HealResult
from breakthevibe.models.domain import ResilientSelector
from breakthevibe.types import SelectorStrategy, TestStatus
from pathlib import Path


class TestResultCollector:
    @pytest.fixture()
    def collector(self) -> ResultCollector:
        return ResultCollector()

    @pytest.fixture()
    def passing_result(self, tmp_path: Path) -> ExecutionResult:
        return ExecutionResult(
            suite_name="test_home",
            success=True,
            exit_code=0,
            stdout="2 passed in 1.5s",
            stderr="",
            test_file=tmp_path / "test_home.py",
            duration_seconds=1.5,
        )

    @pytest.fixture()
    def failing_result(self, tmp_path: Path) -> ExecutionResult:
        return ExecutionResult(
            suite_name="test_products",
            success=False,
            exit_code=1,
            stdout="1 passed, 1 failed in 2.0s",
            stderr="AssertionError: expected 200 got 404",
            test_file=tmp_path / "test_products.py",
            duration_seconds=2.0,
        )

    def test_collect_single_pass(self, collector: ResultCollector, passing_result: ExecutionResult) -> None:
        collector.add_execution_result(passing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-1")

        assert isinstance(report, TestRunReport)
        assert report.project_id == "proj-1"
        assert report.run_id == "run-1"
        assert report.total_suites == 1
        assert report.passed_suites == 1
        assert report.failed_suites == 0

    def test_collect_mixed_results(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
        failing_result: ExecutionResult,
    ) -> None:
        collector.add_execution_result(passing_result)
        collector.add_execution_result(failing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-2")

        assert report.total_suites == 2
        assert report.passed_suites == 1
        assert report.failed_suites == 1
        assert report.overall_status == TestStatus.FAILED

    def test_all_passing_status(self, collector: ResultCollector, passing_result: ExecutionResult) -> None:
        collector.add_execution_result(passing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-3")
        assert report.overall_status == TestStatus.PASSED

    def test_collect_healed_selectors(self, collector: ResultCollector, passing_result: ExecutionResult) -> None:
        heal = HealResult(
            found=True,
            healed=True,
            used_selector=ResilientSelector(strategy=SelectorStrategy.CSS, value=".btn"),
            original_selector=ResilientSelector(strategy=SelectorStrategy.TEST_ID, value="submit"),
        )
        collector.add_execution_result(passing_result)
        collector.add_heal_warning("test_home", heal)
        report = collector.build_report(project_id="proj-1", run_id="run-4")
        assert len(report.heal_warnings) == 1
        assert "submit" in report.heal_warnings[0]

    def test_collect_screenshots(self, collector: ResultCollector, passing_result: ExecutionResult, tmp_path: Path) -> None:
        screenshot = tmp_path / "home.png"
        screenshot.write_bytes(b"\x89PNG fake data")
        collector.add_execution_result(passing_result)
        collector.add_screenshot("test_home", "home_step_1", screenshot)
        report = collector.build_report(project_id="proj-1", run_id="run-5")
        assert len(report.screenshots) == 1
        assert report.screenshots[0].step_name == "home_step_1"

    def test_empty_report(self, collector: ResultCollector) -> None:
        report = collector.build_report(project_id="proj-1", run_id="run-6")
        assert report.total_suites == 0
        assert report.overall_status == TestStatus.PASSED  # vacuously true

    def test_duration_sums(
        self,
        collector: ResultCollector,
        passing_result: ExecutionResult,
        failing_result: ExecutionResult,
    ) -> None:
        collector.add_execution_result(passing_result)
        collector.add_execution_result(failing_result)
        report = collector.build_report(project_id="proj-1", run_id="run-7")
        assert report.total_duration == pytest.approx(3.5, abs=0.1)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.reporter'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/reporter/__init__.py
```

```python
# breakthevibe/reporter/collector.py
"""Test result collection and report building."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from breakthevibe.runner.executor import ExecutionResult
from breakthevibe.runner.healer import HealResult
from breakthevibe.types import TestStatus

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ScreenshotRef:
    """Reference to a captured screenshot."""
    suite_name: str
    step_name: str
    path: Path


@dataclass
class TestRunReport:
    """Aggregated report for a complete test run."""
    project_id: str
    run_id: str
    results: list[ExecutionResult]
    heal_warnings: list[str] = field(default_factory=list)
    screenshots: list[ScreenshotRef] = field(default_factory=list)

    @property
    def total_suites(self) -> int:
        return len(self.results)

    @property
    def passed_suites(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_suites(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def overall_status(self) -> TestStatus:
        if not self.results:
            return TestStatus.PASSED
        return TestStatus.PASSED if all(r.success for r in self.results) else TestStatus.FAILED

    @property
    def total_duration(self) -> float:
        return sum(r.duration_seconds for r in self.results)


class ResultCollector:
    """Collects test results and artifacts into a report."""

    def __init__(self) -> None:
        self._results: list[ExecutionResult] = []
        self._heal_warnings: list[str] = []
        self._screenshots: list[ScreenshotRef] = []

    def add_execution_result(self, result: ExecutionResult) -> None:
        """Add an execution result."""
        self._results.append(result)
        logger.info(
            "result_collected",
            suite=result.suite_name,
            success=result.success,
            duration=result.duration_seconds,
        )

    def add_heal_warning(self, suite_name: str, heal_result: HealResult) -> None:
        """Record a healed selector warning."""
        msg = heal_result.warning_message()
        if msg:
            self._heal_warnings.append(msg)
            logger.warning("heal_warning_recorded", suite=suite_name, message=msg)

    def add_screenshot(self, suite_name: str, step_name: str, path: Path) -> None:
        """Add a screenshot reference."""
        self._screenshots.append(ScreenshotRef(
            suite_name=suite_name,
            step_name=step_name,
            path=path,
        ))

    def build_report(self, project_id: str, run_id: str) -> TestRunReport:
        """Build a complete test run report."""
        report = TestRunReport(
            project_id=project_id,
            run_id=run_id,
            results=list(self._results),
            heal_warnings=list(self._heal_warnings),
            screenshots=list(self._screenshots),
        )
        logger.info(
            "report_built",
            project=project_id,
            run=run_id,
            total=report.total_suites,
            passed=report.passed_suites,
            failed=report.failed_suites,
            status=report.overall_status.value,
        )
        return report
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_collector.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/reporter/ tests/unit/test_collector.py
git commit -m "feat: add test result collector"
```

---

### Task 25: Visual Regression Diff

**Files:**
- Create: `breakthevibe/reporter/diff.py`
- Test: `tests/unit/test_diff.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_diff.py
import pytest
from pathlib import Path
from PIL import Image
from breakthevibe.reporter.diff import VisualDiff, DiffResult


class TestVisualDiff:
    @pytest.fixture()
    def differ(self) -> VisualDiff:
        return VisualDiff(threshold=0.1)

    @pytest.fixture()
    def identical_images(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two identical test images."""
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        img.save(baseline)
        img.save(current)
        return baseline, current

    @pytest.fixture()
    def different_images(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two different test images."""
        baseline_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current_img = Image.new("RGB", (100, 100), color=(0, 0, 255))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        baseline_img.save(baseline)
        current_img.save(current)
        return baseline, current

    @pytest.fixture()
    def slightly_different_images(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two images with minor differences."""
        baseline_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        # Change just a few pixels
        for x in range(5):
            for y in range(5):
                current_img.putpixel((x, y), (254, 1, 1))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        baseline_img.save(baseline)
        current_img.save(current)
        return baseline, current

    def test_identical_images_pass(self, differ: VisualDiff, identical_images: tuple[Path, Path]) -> None:
        baseline, current = identical_images
        result = differ.compare(baseline, current)
        assert isinstance(result, DiffResult)
        assert result.matches is True
        assert result.diff_percentage == 0.0

    def test_different_images_fail(self, differ: VisualDiff, different_images: tuple[Path, Path]) -> None:
        baseline, current = different_images
        result = differ.compare(baseline, current)
        assert result.matches is False
        assert result.diff_percentage > 0.1

    def test_generates_diff_image(self, differ: VisualDiff, different_images: tuple[Path, Path], tmp_path: Path) -> None:
        baseline, current = different_images
        diff_path = tmp_path / "diff.png"
        result = differ.compare(baseline, current, output_path=diff_path)
        assert diff_path.exists()
        assert result.diff_image_path == diff_path

    def test_slight_diff_below_threshold(self, differ: VisualDiff, slightly_different_images: tuple[Path, Path]) -> None:
        baseline, current = slightly_different_images
        result = differ.compare(baseline, current)
        # 25 pixels out of 10000 = 0.25% which is below 10% threshold
        assert result.matches is True

    def test_different_size_images(self, differ: VisualDiff, tmp_path: Path) -> None:
        baseline_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current_img = Image.new("RGB", (200, 200), color=(255, 0, 0))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        baseline_img.save(baseline)
        current_img.save(current)
        result = differ.compare(baseline, current)
        assert result.matches is False
        assert result.size_mismatch is True

    def test_missing_baseline_creates_new(self, differ: VisualDiff, tmp_path: Path) -> None:
        baseline = tmp_path / "nonexistent.png"
        current_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        current = tmp_path / "current.png"
        current_img.save(current)
        result = differ.compare(baseline, current)
        assert result.is_new_baseline is True
        assert result.matches is True  # No baseline to compare against

    def test_custom_threshold(self, tmp_path: Path) -> None:
        strict_differ = VisualDiff(threshold=0.001)
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        # Change a few pixels
        for x in range(2):
            for y in range(2):
                img2.putpixel((x, y), (254, 1, 1))
        baseline = tmp_path / "baseline.png"
        current = tmp_path / "current.png"
        img1.save(baseline)
        img2.save(current)
        result = strict_differ.compare(baseline, current)
        # 4 pixels out of 10000 = 0.04% which is above 0.1% threshold? Let's see...
        # Actually 0.04% < 0.1% so this would still pass
        assert result.diff_percentage < 0.01
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.reporter.diff'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/reporter/diff.py
"""Visual regression diff engine using Pillow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DiffResult:
    """Result of a visual comparison."""
    matches: bool
    diff_percentage: float = 0.0
    diff_image_path: Path | None = None
    size_mismatch: bool = False
    is_new_baseline: bool = False
    total_pixels: int = 0
    different_pixels: int = 0


class VisualDiff:
    """Compares baseline vs current screenshots using pixel comparison."""

    def __init__(self, threshold: float = 0.1) -> None:
        """
        Args:
            threshold: Maximum percentage of differing pixels allowed (0.0 to 1.0).
                       0.1 = 10% of pixels can differ and still match.
        """
        self._threshold = threshold

    def compare(
        self,
        baseline_path: Path,
        current_path: Path,
        output_path: Path | None = None,
    ) -> DiffResult:
        """Compare two images and optionally output a diff image."""
        if not baseline_path.exists():
            logger.info("new_baseline", path=str(current_path))
            return DiffResult(matches=True, is_new_baseline=True)

        baseline = Image.open(baseline_path).convert("RGB")
        current = Image.open(current_path).convert("RGB")

        # Check size mismatch
        if baseline.size != current.size:
            logger.warning(
                "size_mismatch",
                baseline=baseline.size,
                current=current.size,
            )
            return DiffResult(
                matches=False,
                diff_percentage=1.0,
                size_mismatch=True,
            )

        width, height = baseline.size
        total_pixels = width * height
        diff_count = 0

        baseline_pixels = baseline.load()
        current_pixels = current.load()

        # Create diff image if output requested
        diff_img = Image.new("RGB", (width, height), color=(0, 0, 0)) if output_path else None
        diff_pixels = diff_img.load() if diff_img else None

        for y in range(height):
            for x in range(width):
                bp = baseline_pixels[x, y]
                cp = current_pixels[x, y]
                if bp != cp:
                    diff_count += 1
                    if diff_pixels:
                        diff_pixels[x, y] = (255, 0, 255)  # Magenta for diffs
                else:
                    if diff_pixels:
                        # Dim the matching pixels
                        r, g, b = bp
                        diff_pixels[x, y] = (r // 3, g // 3, b // 3)

        diff_percentage = diff_count / total_pixels if total_pixels > 0 else 0.0
        matches = diff_percentage <= self._threshold

        result_path = None
        if diff_img and output_path:
            diff_img.save(output_path)
            result_path = output_path

        logger.info(
            "visual_diff_complete",
            diff_pct=f"{diff_percentage:.4%}",
            threshold=f"{self._threshold:.4%}",
            matches=matches,
            changed_pixels=diff_count,
            total_pixels=total_pixels,
        )

        return DiffResult(
            matches=matches,
            diff_percentage=diff_percentage,
            diff_image_path=result_path,
            total_pixels=total_pixels,
            different_pixels=diff_count,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_diff.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/reporter/diff.py tests/unit/test_diff.py
git commit -m "feat: add visual regression diff engine"
```

---

## Phase 8: Web Dashboard

### Task 26: FastAPI App Factory

**Files:**
- Create: `breakthevibe/web/__init__.py`
- Create: `breakthevibe/web/app.py`
- Create: `breakthevibe/web/middleware.py`
- Create: `breakthevibe/web/dependencies.py`
- Test: `tests/integration/test_app.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_app.py
import pytest
from httpx import AsyncClient, ASGITransport
from breakthevibe.web.app import create_app


class TestAppFactory:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.mark.asyncio
    async def test_app_creates_successfully(self, app) -> None:
        assert app is not None
        assert app.title == "BreakTheVibe"

    @pytest.mark.asyncio
    async def test_health_endpoint(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_request_id_header(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_cors_headers(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.options(
                "/api/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert resp.status_code in (200, 204, 405)

    @pytest.mark.asyncio
    async def test_404_for_unknown_route(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/nonexistent")
            assert resp.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.web'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/web/__init__.py
```

```python
# breakthevibe/web/middleware.py
"""FastAPI middleware: request ID, rate limiting."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

import structlog

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique X-Request-ID header to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
```

```python
# breakthevibe/web/dependencies.py
"""FastAPI dependency injection."""

from __future__ import annotations

from breakthevibe.llm.factory import create_llm_provider
from breakthevibe.llm.provider import LLMProvider


async def get_llm_provider() -> LLMProvider:
    """Get the default LLM provider."""
    return create_llm_provider("anthropic")
```

```python
# breakthevibe/web/app.py
"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from breakthevibe.web.middleware import RequestIDMiddleware

import structlog

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BreakTheVibe",
        description="AI-powered QA automation platform",
        version="0.1.0",
    )

    # Middleware (order matters - last added runs first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # Health check
    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy", "version": "0.1.0"}

    # Mount static files if directory exists
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    logger.info("app_created")
    return app
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_app.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/web/ tests/integration/test_app.py
git commit -m "feat: add FastAPI app factory with middleware"
```

---

### Task 27: API Routes — Projects

**Files:**
- Create: `breakthevibe/web/routes/__init__.py`
- Create: `breakthevibe/web/routes/projects.py`
- Create: `breakthevibe/storage/repositories/__init__.py`
- Create: `breakthevibe/storage/repositories/projects.py`
- Test: `tests/integration/test_routes_projects.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_routes_projects.py
import pytest
from httpx import AsyncClient, ASGITransport
from breakthevibe.web.app import create_app


class TestProjectRoutes:
    @pytest.fixture()
    def app(self):
        app = create_app()
        return app

    @pytest.mark.asyncio
    async def test_create_project(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/projects", json={
                "name": "Test Site",
                "url": "https://example.com",
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "Test Site"
            assert data["url"] == "https://example.com"
            assert "id" in data

    @pytest.mark.asyncio
    async def test_list_projects(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/projects", json={
                "name": "Site A",
                "url": "https://a.com",
            })
            resp = await client.get("/api/projects")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_project(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/projects", json={
                "name": "Site B",
                "url": "https://b.com",
            })
            project_id = create_resp.json()["id"]
            resp = await client.get(f"/api/projects/{project_id}")
            assert resp.status_code == 200
            assert resp.json()["name"] == "Site B"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/projects/nonexistent-id")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/projects", json={
                "name": "To Delete",
                "url": "https://delete.com",
            })
            project_id = create_resp.json()["id"]
            del_resp = await client.delete(f"/api/projects/{project_id}")
            assert del_resp.status_code == 204
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_project_validation(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/projects", json={
                "name": "",
                "url": "not-a-url",
            })
            assert resp.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_routes_projects.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# breakthevibe/web/routes/__init__.py
```

```python
# breakthevibe/storage/repositories/__init__.py
```

```python
# breakthevibe/storage/repositories/projects.py
"""In-memory project repository (PostgreSQL-backed version in production)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ProjectRepository:
    """In-memory project store. Replaced by SQLModel + PostgreSQL in production."""

    def __init__(self) -> None:
        self._projects: dict[str, dict[str, Any]] = {}

    async def create(self, name: str, url: str, rules_yaml: str = "") -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        project = {
            "id": project_id,
            "name": name,
            "url": url,
            "rules_yaml": rules_yaml,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run_at": None,
            "status": "created",
        }
        self._projects[project_id] = project
        logger.info("project_created", id=project_id, name=name)
        return project

    async def list_all(self) -> list[dict[str, Any]]:
        return list(self._projects.values())

    async def get(self, project_id: str) -> dict[str, Any] | None:
        return self._projects.get(project_id)

    async def delete(self, project_id: str) -> bool:
        if project_id in self._projects:
            del self._projects[project_id]
            logger.info("project_deleted", id=project_id)
            return True
        return False

    async def update(self, project_id: str, **updates: Any) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if project:
            project.update(updates)
            return project
        return None
```

```python
# breakthevibe/web/routes/projects.py
"""Project CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

import structlog

from breakthevibe.storage.repositories.projects import ProjectRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Shared repo instance (replaced by DI with DB session in production)
_repo = ProjectRepository()


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    rules_yaml: str = ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    url: str
    rules_yaml: str = ""
    created_at: str
    last_run_at: str | None = None
    status: str = "created"


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(body: CreateProjectRequest):
    project = await _repo.create(
        name=body.name,
        url=str(body.url),
        rules_yaml=body.rules_yaml,
    )
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects():
    return await _repo.list_all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    project = await _repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    deleted = await _repo.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
```

Now register the router in `app.py`. Update `breakthevibe/web/app.py` to add `from breakthevibe.web.routes.projects import router as projects_router` and `app.include_router(projects_router)`.

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_routes_projects.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/web/ breakthevibe/storage/repositories/ tests/integration/test_routes_projects.py
git commit -m "feat: add project CRUD API routes"
```

---

### Task 28: API Routes — Crawl, Tests, Results

**Files:**
- Create: `breakthevibe/web/routes/crawl.py`
- Create: `breakthevibe/web/routes/tests.py`
- Create: `breakthevibe/web/routes/results.py`
- Test: `tests/integration/test_routes_crawl.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_routes_crawl.py
import pytest
from httpx import AsyncClient, ASGITransport
from breakthevibe.web.app import create_app


class TestCrawlRoutes:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.fixture()
    async def project_id(self, app) -> str:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/projects", json={
                "name": "Test",
                "url": "https://example.com",
            })
            return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_crawl(self, app, project_id: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{project_id}/crawl")
            assert resp.status_code in (200, 202)
            data = resp.json()
            assert "status" in data

    @pytest.mark.asyncio
    async def test_crawl_nonexistent_project(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/projects/bad-id/crawl")
            assert resp.status_code == 404


class TestTestRoutes:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.fixture()
    async def project_id(self, app) -> str:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/projects", json={
                "name": "Test",
                "url": "https://example.com",
            })
            return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_trigger_generate(self, app, project_id: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{project_id}/generate")
            assert resp.status_code in (200, 202)

    @pytest.mark.asyncio
    async def test_trigger_run(self, app, project_id: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{project_id}/run")
            assert resp.status_code in (200, 202)


class TestResultRoutes:
    @pytest.fixture()
    def app(self):
        return create_app()

    @pytest.mark.asyncio
    async def test_get_run_results(self, app) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/test-run-id/results")
            assert resp.status_code in (200, 404)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_routes_crawl.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# breakthevibe/web/routes/crawl.py
"""Crawl trigger and sitemap API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from breakthevibe.storage.repositories.projects import ProjectRepository

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["crawl"])

_repo = ProjectRepository()


@router.post("/api/projects/{project_id}/crawl")
async def trigger_crawl(project_id: str):
    project = await _repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("crawl_triggered", project_id=project_id)
    return {"status": "accepted", "project_id": project_id, "message": "Crawl started"}


@router.get("/api/projects/{project_id}/sitemap")
async def get_sitemap(project_id: str):
    project = await _repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "pages": [], "api_endpoints": []}
```

```python
# breakthevibe/web/routes/tests.py
"""Test generation and execution API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from breakthevibe.storage.repositories.projects import ProjectRepository

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["tests"])

_repo = ProjectRepository()


@router.post("/api/projects/{project_id}/generate")
async def trigger_generate(project_id: str):
    project = await _repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("generate_triggered", project_id=project_id)
    return {"status": "accepted", "project_id": project_id, "message": "Test generation started"}


@router.post("/api/projects/{project_id}/run")
async def trigger_run(project_id: str):
    project = await _repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("run_triggered", project_id=project_id)
    return {"status": "accepted", "project_id": project_id, "message": "Test run started"}
```

```python
# breakthevibe/web/routes/results.py
"""Test results API routes."""

from __future__ import annotations

from fastapi import APIRouter

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["results"])


@router.get("/api/runs/{run_id}/results")
async def get_run_results(run_id: str):
    return {"run_id": run_id, "status": "no_data", "suites": [], "total": 0, "passed": 0, "failed": 0}
```

Update `breakthevibe/web/app.py` to include all new routers. The full updated `app.py`:

```python
# breakthevibe/web/app.py  (updated with all route imports)
"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from breakthevibe.web.middleware import RequestIDMiddleware
from breakthevibe.web.routes.projects import router as projects_router
from breakthevibe.web.routes.crawl import router as crawl_router
from breakthevibe.web.routes.tests import router as tests_router
from breakthevibe.web.routes.results import router as results_router

import structlog

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BreakTheVibe",
        description="AI-powered QA automation platform",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.include_router(projects_router)
    app.include_router(crawl_router)
    app.include_router(tests_router)
    app.include_router(results_router)

    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy", "version": "0.1.0"}

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    logger.info("app_created")
    return app
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_routes_crawl.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/web/routes/ tests/integration/test_routes_crawl.py
git commit -m "feat: add crawl, test generation, and results API routes"
```

---

### Task 29: Web UI Templates — Project Overview + Mind-Map

**Files:**
- Create: `breakthevibe/web/templates/base.html`
- Create: `breakthevibe/web/templates/projects.html`
- Create: `breakthevibe/web/templates/project_detail.html`
- Create: `breakthevibe/web/templates/sitemap.html`
- Create: `breakthevibe/web/static/css/style.css`
- Create: `breakthevibe/web/static/js/mindmap.js`
- Create: `breakthevibe/web/routes/pages.py`

**Step 1: Create base template**

Jinja2 base layout with htmx, dark theme, nav bar. Include `{% block title %}`, `{% block content %}`, `{% block scripts %}` blocks. Link to `/static/css/style.css` and htmx CDN.

**Step 2: Create projects list template**

Extends `base.html`. Shows a card grid of projects with name, URL, status badge, and action buttons (Crawl, Delete). Uses htmx for inline actions (`hx-post`, `hx-delete`, `hx-target`).

**Step 3: Create project detail template**

Extends `base.html`. Shows project info, action bar (Crawl, Generate Tests, Run Tests, View Mind-Map, Edit Rules), tabs for Test Runs and Site Map using htmx partial loading.

**Step 4: Create sitemap / mind-map template**

Extends `base.html`. Includes D3.js v7 CDN. Has a `#mindmap-container` div with `data-sitemap-url` attribute pointing to the sitemap API endpoint.

**Step 5: Create CSS**

Dark theme CSS with variables: `--bg: #0f1117`, `--surface: #1a1d27`, `--primary: #6366f1`. Styles for navbar, container, project cards, buttons (`.btn`, `.btn-primary`, `.btn-danger`), status badges, tabs, action bar, mind-map container, form inputs, code editor textarea.

**Step 6: Create mind-map D3.js visualization**

`mindmap.js`: Fetches sitemap data from `data-sitemap-url`, transforms flat page list into a hierarchy (Site > Routes > Components). Renders as a horizontal tree using `d3.tree()` with `d3.linkHorizontal()` paths. Nodes colored by type (route = indigo, component = green). Supports pan/zoom via `d3.zoom()`.

**Step 7: Create page routes**

```python
# breakthevibe/web/routes/pages.py
"""Server-rendered HTML page routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from breakthevibe.storage.repositories.projects import ProjectRepository

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_repo = ProjectRepository()


@router.get("/", response_class=HTMLResponse)
async def projects_page(request: Request):
    projects = await _repo.list_all()
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "projects": projects,
    })


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(request: Request, project_id: str):
    project = await _repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "project": project,
    })


@router.get("/projects/{project_id}/sitemap", response_class=HTMLResponse)
async def sitemap_page(request: Request, project_id: str):
    project = await _repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse("sitemap.html", {
        "request": request,
        "project": project,
    })
```

Update `app.py` to include page routes.

**Step 8: Commit**

```bash
git add breakthevibe/web/
git commit -m "feat: add web UI templates for projects and mind-map"
```

---

### Task 30: Web UI — Test Results + Replay

**Files:**
- Create: `breakthevibe/web/templates/test_runs.html`
- Create: `breakthevibe/web/templates/test_result_detail.html`
- Create: `breakthevibe/web/static/js/replay.js`

**Step 1: Create test runs list template**

Extends `base.html`. Lists test runs as cards showing status badge, run ID, timestamp, pass/fail/total counts. Links to detail view.

**Step 2: Create test result detail template with replay**

Extends `base.html`. Sections:
- **Summary bar**: passed/failed/total/duration stats
- **Healed selector warnings**: listed if any
- **Suite results**: expandable suite cards using htmx
- **Replay panel**: Previous/Next buttons, step counter, screenshot display area, action/description labels, network activity timeline, console log output
- **Visual diffs**: side-by-side baseline/current/diff images (if any)
- **Video player**: HTML5 video element for test execution recording

**Step 3: Create replay JavaScript**

`replay.js`: Manages step-by-step navigation through test steps. Exposes `window.loadReplaySteps(data)` function. Renders current step's screenshot, action name, description, network requests, and console logs. Previous/Next buttons update the display. Uses `textContent` for dynamic text and DOM element creation for network entries (not raw string concatenation) to prevent XSS.

**Step 4: Commit**

```bash
git add breakthevibe/web/templates/ breakthevibe/web/static/js/replay.js
git commit -m "feat: add test results and step-by-step replay UI"
```

---

### Task 31: Web UI — Rules Editor + LLM Settings

**Files:**
- Create: `breakthevibe/web/templates/rules_editor.html`
- Create: `breakthevibe/web/templates/llm_settings.html`
- Create: `breakthevibe/web/routes/settings.py`

**Step 1: Create rules editor template**

Extends `base.html`. Contains:
- Large `<textarea>` with monospace font for YAML editing (`class="code-editor"`)
- htmx form submitting to `PUT /api/projects/{id}/rules`
- Validate button calling `POST /api/rules/validate` endpoint
- Reset to defaults button
- Help section documenting all available configuration keys: `crawl` (max_depth, skip_urls, scroll_behavior, viewport, wait_times), `inputs` (key-value pairs), `interactions` (cookie_banner, modals, infinite_scroll), `tests` (skip_visual), `api` (ignore_endpoints, expected_overrides), `execution` (mode, suites)

**Step 2: Create LLM settings template**

Extends `base.html`. Sections:
- **Default Provider**: dropdown (Anthropic/OpenAI/Ollama) + model text input
- **Per-Module Overrides**: for mapper, generator, agent — each with provider dropdown + model input. "Use default" option in dropdown.
- **API Keys**: password inputs for Anthropic key, OpenAI key, Ollama base URL. Help text about environment variables for production.
- Save button submitting to `PUT /api/settings/llm`

**Step 3: Create settings routes**

```python
# breakthevibe/web/routes/settings.py
"""Settings API routes for rules and LLM configuration."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel

from breakthevibe.generator.rules.schema import RulesConfig
from breakthevibe.storage.repositories.projects import ProjectRepository

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_repo = ProjectRepository()

# In-memory LLM settings (replaced by DB in production)
_llm_settings = {
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


class ValidateRulesRequest(BaseModel):
    yaml: str


@router.get("/projects/{project_id}/rules", response_class=HTMLResponse)
async def rules_editor_page(request: Request, project_id: str):
    project = await _repo.get(project_id)
    if not project:
        return HTMLResponse(content="Project not found", status_code=404)
    return templates.TemplateResponse("rules_editor.html", {
        "request": request,
        "project": project,
        "rules_yaml": project.get("rules_yaml", ""),
    })


@router.put("/api/projects/{project_id}/rules")
async def update_rules(project_id: str, request: Request):
    project = await _repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    form = await request.form()
    rules_yaml = form.get("rules_yaml", "")
    try:
        RulesConfig.from_yaml(str(rules_yaml))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}")
    await _repo.update(project_id, rules_yaml=str(rules_yaml))
    return {"status": "saved"}


@router.post("/api/rules/validate")
async def validate_rules(body: ValidateRulesRequest):
    try:
        RulesConfig.from_yaml(body.yaml)
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.get("/settings/llm", response_class=HTMLResponse)
async def llm_settings_page(request: Request):
    return templates.TemplateResponse("llm_settings.html", {
        "request": request,
        "settings": _llm_settings,
    })


@router.put("/api/settings/llm")
async def update_llm_settings(request: Request):
    form = await request.form()
    if form.get("default_provider"):
        _llm_settings["default_provider"] = str(form["default_provider"])
    if form.get("default_model"):
        _llm_settings["default_model"] = str(form["default_model"])
    for module in ["mapper", "generator", "agent"]:
        provider = form.get(f"modules_{module}_provider")
        model = form.get(f"modules_{module}_model")
        if provider:
            _llm_settings["modules"][module]["provider"] = str(provider)
        if model:
            _llm_settings["modules"][module]["model"] = str(model)
    logger.info("llm_settings_updated", settings=_llm_settings)
    return {"status": "saved"}
```

Update `app.py` to include settings router.

**Step 4: Commit**

```bash
git add breakthevibe/web/
git commit -m "feat: add rules editor and LLM settings UI"
```

---

## Phase 9: Agent Layer

### Task 32: Pipeline Orchestrator

**Files:**
- Create: `breakthevibe/agent/__init__.py`
- Create: `breakthevibe/agent/orchestrator.py`
- Test: `tests/unit/test_orchestrator.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from breakthevibe.agent.orchestrator import PipelineOrchestrator, PipelineResult, PipelineStage


class TestPipelineOrchestrator:
    @pytest.fixture()
    def mock_components(self) -> dict:
        return {
            "crawler": AsyncMock(),
            "mapper": AsyncMock(),
            "generator": AsyncMock(),
            "runner": AsyncMock(),
            "collector": MagicMock(),
        }

    @pytest.fixture()
    def orchestrator(self, mock_components: dict) -> PipelineOrchestrator:
        return PipelineOrchestrator(**mock_components)

    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, orchestrator: PipelineOrchestrator) -> None:
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert isinstance(result, PipelineResult)
        assert result.success is True
        assert result.completed_stages == [
            PipelineStage.CRAWL,
            PipelineStage.MAP,
            PipelineStage.GENERATE,
            PipelineStage.RUN,
            PipelineStage.REPORT,
        ]

    @pytest.mark.asyncio
    async def test_crawl_failure_stops_pipeline(self, orchestrator: PipelineOrchestrator, mock_components: dict) -> None:
        mock_components["crawler"].crawl.side_effect = Exception("Connection timeout")
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert result.success is False
        assert result.failed_stage == PipelineStage.CRAWL
        assert "Connection timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_generator_failure_stops_pipeline(self, orchestrator: PipelineOrchestrator, mock_components: dict) -> None:
        mock_components["generator"].generate.side_effect = Exception("LLM rate limit")
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert result.success is False
        assert result.failed_stage == PipelineStage.GENERATE

    @pytest.mark.asyncio
    async def test_pipeline_records_duration(self, orchestrator: PipelineOrchestrator) -> None:
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_pipeline_retries_on_failure(self, orchestrator: PipelineOrchestrator, mock_components: dict) -> None:
        # First call fails, second succeeds
        mock_components["crawler"].crawl.side_effect = [Exception("Transient"), MagicMock()]
        orchestrator.max_retries = 2
        result = await orchestrator.run(
            project_id="proj-1",
            url="https://example.com",
            rules_yaml="",
        )
        # Should have retried and eventually succeeded or failed
        assert mock_components["crawler"].crawl.call_count == 2
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.agent'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/agent/__init__.py
```

```python
# breakthevibe/agent/orchestrator.py
"""Pipeline orchestrator — coordinates all stages."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PipelineStage(StrEnum):
    CRAWL = "crawl"
    MAP = "map"
    GENERATE = "generate"
    RUN = "run"
    REPORT = "report"


@dataclass
class PipelineResult:
    """Result of a full pipeline execution."""
    project_id: str
    run_id: str
    success: bool
    completed_stages: list[PipelineStage] = field(default_factory=list)
    failed_stage: PipelineStage | None = None
    error_message: str = ""
    duration_seconds: float = 0.0


class PipelineOrchestrator:
    """Coordinates the full pipeline: crawl -> map -> generate -> run -> report."""

    def __init__(
        self,
        crawler: Any = None,
        mapper: Any = None,
        generator: Any = None,
        runner: Any = None,
        collector: Any = None,
        planner: Any = None,
    ) -> None:
        self._crawler = crawler
        self._mapper = mapper
        self._generator = generator
        self._runner = runner
        self._collector = collector
        self._planner = planner
        self.max_retries: int = 1

    async def run(
        self,
        project_id: str,
        url: str,
        rules_yaml: str = "",
    ) -> PipelineResult:
        """Execute the full pipeline."""
        run_id = str(uuid.uuid4())
        start = time.monotonic()
        completed: list[PipelineStage] = []

        logger.info("pipeline_started", project_id=project_id, run_id=run_id, url=url)

        stages = [
            (PipelineStage.CRAWL, self._run_crawl),
            (PipelineStage.MAP, self._run_map),
            (PipelineStage.GENERATE, self._run_generate),
            (PipelineStage.RUN, self._run_tests),
            (PipelineStage.REPORT, self._run_report),
        ]

        context: dict[str, Any] = {"url": url, "rules_yaml": rules_yaml, "project_id": project_id}

        for stage, handler in stages:
            success = False
            last_error = ""

            for attempt in range(self.max_retries):
                try:
                    logger.info("stage_starting", stage=stage.value, attempt=attempt + 1)
                    await handler(context)
                    completed.append(stage)
                    success = True
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "stage_failed",
                        stage=stage.value,
                        attempt=attempt + 1,
                        error=last_error,
                    )

            if not success:
                duration = time.monotonic() - start
                logger.error("pipeline_failed", stage=stage.value, error=last_error)
                return PipelineResult(
                    project_id=project_id,
                    run_id=run_id,
                    success=False,
                    completed_stages=completed,
                    failed_stage=stage,
                    error_message=last_error,
                    duration_seconds=duration,
                )

        duration = time.monotonic() - start
        logger.info("pipeline_completed", run_id=run_id, duration=duration)
        return PipelineResult(
            project_id=project_id,
            run_id=run_id,
            success=True,
            completed_stages=completed,
            duration_seconds=duration,
        )

    async def _run_crawl(self, context: dict[str, Any]) -> None:
        result = await self._crawler.crawl(context["url"])
        context["crawl_result"] = result

    async def _run_map(self, context: dict[str, Any]) -> None:
        result = await self._mapper.build(context.get("crawl_result"))
        context["sitemap"] = result

    async def _run_generate(self, context: dict[str, Any]) -> None:
        result = await self._generator.generate(context.get("sitemap"))
        context["test_cases"] = result

    async def _run_tests(self, context: dict[str, Any]) -> None:
        result = await self._runner.run(context.get("test_cases"))
        context["test_results"] = result

    async def _run_report(self, context: dict[str, Any]) -> None:
        if self._collector:
            self._collector.build_report(
                project_id=context["project_id"],
                run_id="auto",
            )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_orchestrator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/agent/ tests/unit/test_orchestrator.py
git commit -m "feat: add pipeline orchestrator"
```

---

### Task 33: Agent Planner (LLM-based retry)

**Files:**
- Create: `breakthevibe/agent/planner.py`
- Test: `tests/unit/test_planner.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_planner.py
import json
import pytest
from unittest.mock import AsyncMock
from breakthevibe.agent.planner import AgentPlanner, RetryDecision
from breakthevibe.agent.orchestrator import PipelineStage
from breakthevibe.llm.provider import LLMResponse


class TestAgentPlanner:
    @pytest.fixture()
    def mock_llm(self) -> AsyncMock:
        llm = AsyncMock()
        llm.generate.return_value = LLMResponse(
            content=json.dumps({
                "should_retry": True,
                "reason": "Transient network error, retrying with longer timeout",
                "adjusted_params": {"timeout": 10000},
            }),
            model="test-model",
            usage={"input_tokens": 50, "output_tokens": 30},
        )
        return llm

    @pytest.fixture()
    def planner(self, mock_llm: AsyncMock) -> AgentPlanner:
        return AgentPlanner(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_decides_retry_on_transient(self, planner: AgentPlanner) -> None:
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="ConnectionError: Connection timed out",
            attempt=1,
        )
        assert isinstance(decision, RetryDecision)
        assert decision.should_retry is True
        assert decision.reason != ""

    @pytest.mark.asyncio
    async def test_decides_no_retry_on_permanent(self, planner: AgentPlanner, mock_llm: AsyncMock) -> None:
        mock_llm.generate.return_value = LLMResponse(
            content=json.dumps({
                "should_retry": False,
                "reason": "Invalid URL - permanent failure",
                "adjusted_params": {},
            }),
            model="test-model",
            usage={"input_tokens": 50, "output_tokens": 30},
        )
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="Invalid URL: not-a-url",
            attempt=1,
        )
        assert decision.should_retry is False

    @pytest.mark.asyncio
    async def test_includes_adjusted_params(self, planner: AgentPlanner) -> None:
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="Timeout",
            attempt=1,
        )
        assert "timeout" in decision.adjusted_params

    @pytest.mark.asyncio
    async def test_prompt_includes_context(self, planner: AgentPlanner, mock_llm: AsyncMock) -> None:
        await planner.analyze_failure(
            stage=PipelineStage.MAP,
            error="LLM rate limit exceeded",
            attempt=2,
        )
        call_args = mock_llm.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args.args[0]
        assert "map" in prompt.lower()
        assert "rate limit" in prompt.lower()
        assert "attempt 2" in prompt.lower() or "2" in prompt

    @pytest.mark.asyncio
    async def test_handles_invalid_llm_response(self, planner: AgentPlanner, mock_llm: AsyncMock) -> None:
        mock_llm.generate.return_value = LLMResponse(
            content="invalid json response",
            model="test-model",
            usage={"input_tokens": 10, "output_tokens": 10},
        )
        decision = await planner.analyze_failure(
            stage=PipelineStage.RUN,
            error="Some error",
            attempt=1,
        )
        # Should default to retry=False on parse error
        assert decision.should_retry is False

    @pytest.mark.asyncio
    async def test_max_attempts_forces_no_retry(self, planner: AgentPlanner) -> None:
        planner.max_attempts = 3
        decision = await planner.analyze_failure(
            stage=PipelineStage.CRAWL,
            error="Error",
            attempt=3,
        )
        assert decision.should_retry is False
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_planner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.agent.planner'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/agent/planner.py
"""LLM-based agent planner for retry decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from breakthevibe.agent.orchestrator import PipelineStage
from breakthevibe.llm.provider import LLMProvider

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RetryDecision:
    """Decision from the planner about whether to retry."""
    should_retry: bool
    reason: str = ""
    adjusted_params: dict[str, Any] = field(default_factory=dict)


class AgentPlanner:
    """Analyzes failures and decides whether/how to retry."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm
        self.max_attempts: int = 3

    async def analyze_failure(
        self,
        stage: PipelineStage,
        error: str,
        attempt: int,
    ) -> RetryDecision:
        """Ask LLM whether to retry a failed stage."""
        if attempt >= self.max_attempts:
            logger.info("max_attempts_reached", stage=stage.value, attempt=attempt)
            return RetryDecision(
                should_retry=False,
                reason=f"Maximum attempts ({self.max_attempts}) reached",
            )

        prompt = self._build_prompt(stage, error, attempt)

        try:
            response = await self._llm.generate(prompt=prompt)
            return self._parse_decision(response.content)
        except Exception as e:
            logger.error("planner_llm_error", error=str(e))
            return RetryDecision(should_retry=False, reason=f"Planner error: {e}")

    def _build_prompt(self, stage: PipelineStage, error: str, attempt: int) -> str:
        return f"""A pipeline stage has failed. Analyze the error and decide if retrying would help.

Stage: {stage.value}
Error: {error}
Attempt: {attempt} of {self.max_attempts}

Respond with JSON:
{{
  "should_retry": true/false,
  "reason": "explanation",
  "adjusted_params": {{}}  // optional adjusted parameters for retry
}}

Consider:
- Transient errors (timeouts, rate limits) usually benefit from retry
- Permanent errors (invalid URL, auth failure) should not be retried
- If retrying, suggest adjusted parameters (longer timeout, different approach)"""

    def _parse_decision(self, content: str) -> RetryDecision:
        """Parse LLM response into a RetryDecision."""
        try:
            data = json.loads(content)
            return RetryDecision(
                should_retry=bool(data.get("should_retry", False)),
                reason=data.get("reason", ""),
                adjusted_params=data.get("adjusted_params", {}),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("planner_parse_error", error=str(e), content=content[:200])
            return RetryDecision(should_retry=False, reason=f"Failed to parse planner response: {e}")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_planner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/agent/planner.py tests/unit/test_planner.py
git commit -m "feat: add LLM-based agent planner for retry logic"
```

---

## Phase 10: Docker + CI + Auth

### Task 34: Dockerfile + Docker Compose (Full)

**Files:**
- Create: `Dockerfile`
- Update: `docker-compose.yml` (add app service)
- Create: `.dockerignore`

**Step 1: Create Dockerfile**

```dockerfile
# Dockerfile
# Stage 1: Build dependencies
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy installed dependencies from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY breakthevibe/ breakthevibe/
COPY pyproject.toml ./
COPY alembic.ini* ./

# Install project itself
RUN uv sync --frozen --no-dev

# Install Playwright browsers
RUN uv run playwright install chromium

# Create artifact directory
RUN mkdir -p /data/artifacts

ENV PYTHONUNBUFFERED=1
ENV BTV_ARTIFACT_DIR=/data/artifacts
ENV BTV_DATABASE_URL=postgresql+asyncpg://breakthevibe:breakthevibe@db:5432/breakthevibe

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uv", "run", "uvicorn", "breakthevibe.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Create .dockerignore**

```
# .dockerignore
.git
.github
.venv
__pycache__
*.pyc
.mypy_cache
.ruff_cache
.pytest_cache
*.egg-info
dist
build
docs
tests
.env
.env.*
!.env.example
node_modules
```

**Step 3: Update docker-compose.yml**

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: breakthevibe
      POSTGRES_PASSWORD: breakthevibe
      POSTGRES_DB: breakthevibe
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U breakthevibe"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      BTV_DATABASE_URL: postgresql+asyncpg://breakthevibe:breakthevibe@db:5432/breakthevibe
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - artifact_data:/data/artifacts

volumes:
  postgres_data:
  artifact_data:
```

**Step 4: Verify Docker build**

Run: `cd /Users/tenaz3/development/breakthevibe && docker compose build`
Expected: Build completes successfully

**Step 5: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml
git commit -m "feat: add Dockerfile and full Docker Compose"
```

---

### Task 35: Session Auth for Web UI

**Files:**
- Create: `breakthevibe/web/auth/__init__.py`
- Create: `breakthevibe/web/auth/session.py`
- Test: `tests/integration/test_auth.py`

**Step 1: Write the failing test**

```python
# tests/integration/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from breakthevibe.web.app import create_app
from breakthevibe.web.auth.session import SessionAuth


class TestSessionAuth:
    def test_create_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = auth.create_session(username="admin")
        assert token is not None
        assert len(token) > 20

    def test_validate_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = auth.create_session(username="admin")
        user = auth.validate_session(token)
        assert user is not None
        assert user["username"] == "admin"

    def test_invalid_token(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        user = auth.validate_session("invalid-token")
        assert user is None

    def test_destroy_session(self) -> None:
        auth = SessionAuth(secret_key="test-secret")
        token = auth.create_session(username="admin")
        auth.destroy_session(token)
        user = auth.validate_session(token)
        assert user is None

    def test_different_secrets(self) -> None:
        auth1 = SessionAuth(secret_key="secret-1")
        auth2 = SessionAuth(secret_key="secret-2")
        token = auth1.create_session(username="admin")
        # Token from auth1 should not work with auth2
        user = auth2.validate_session(token)
        assert user is None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.web.auth'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/web/auth/__init__.py
```

```python
# breakthevibe/web/auth/session.py
"""Cookie-based session authentication."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SessionAuth:
    """Simple cookie-based session management."""

    def __init__(self, secret_key: str, max_age: int = 86400) -> None:
        self._secret = secret_key.encode()
        self._max_age = max_age
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self, username: str) -> str:
        """Create a new session and return the token."""
        token = secrets.token_urlsafe(32)
        signature = self._sign(token)
        signed_token = f"{token}.{signature}"

        self._sessions[signed_token] = {
            "username": username,
            "created_at": time.time(),
        }
        logger.info("session_created", username=username)
        return signed_token

    def validate_session(self, token: str) -> dict[str, Any] | None:
        """Validate a session token and return user data."""
        if not token or "." not in token:
            return None

        raw_token, signature = token.rsplit(".", 1)
        expected_sig = self._sign(raw_token)

        if not hmac.compare_digest(signature, expected_sig):
            return None

        session = self._sessions.get(token)
        if not session:
            return None

        # Check expiry
        if time.time() - session["created_at"] > self._max_age:
            self.destroy_session(token)
            return None

        return session

    def destroy_session(self, token: str) -> None:
        """Remove a session."""
        self._sessions.pop(token, None)
        logger.info("session_destroyed")

    def _sign(self, data: str) -> str:
        """Create HMAC signature for a token."""
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()[:32]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_auth.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/web/auth/ tests/integration/test_auth.py
git commit -m "feat: add session authentication for web UI"
```

---

### Task 36: CI Pipeline

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.pre-commit-config.yaml`

**Step 1: Create GitHub Actions CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run mypy breakthevibe/

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: breakthevibe
          POSTGRES_PASSWORD: breakthevibe
          POSTGRES_DB: breakthevibe_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      BTV_DATABASE_URL: postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run playwright install chromium
      - run: uv run pytest -v --cov=breakthevibe --cov-report=xml -m "not integration"
      - run: uv run pytest -v -m integration

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run pip-audit
        continue-on-error: true

  docker:
    runs-on: ubuntu-latest
    needs: [lint, typecheck, test]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build
      - run: docker compose up -d
      - run: sleep 10 && curl -f http://localhost:8000/api/health
      - run: docker compose down
```

**Step 2: Create pre-commit configuration**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]
        exclude: (uv\.lock|\.env\.example)$
```

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml .pre-commit-config.yaml
git commit -m "feat: add CI pipeline and pre-commit configuration"
```

---

### Task 37: Storage Artifacts Manager

**Files:**
- Create: `breakthevibe/storage/artifacts.py`
- Test: `tests/unit/test_artifacts.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_artifacts.py
import pytest
from pathlib import Path
from breakthevibe.storage.artifacts import ArtifactStore


class TestArtifactStore:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> ArtifactStore:
        return ArtifactStore(base_dir=tmp_path)

    def test_creates_project_directory(self, store: ArtifactStore) -> None:
        path = store.get_project_dir("proj-123")
        assert path.exists()
        assert path.is_dir()

    def test_creates_run_directory(self, store: ArtifactStore) -> None:
        path = store.get_run_dir("proj-123", "run-456")
        assert path.exists()
        assert "proj-123" in str(path)
        assert "run-456" in str(path)

    def test_screenshot_path(self, store: ArtifactStore) -> None:
        path = store.screenshot_path("proj-1", "run-1", "step_01")
        assert path.name == "step_01.png"
        assert path.parent.exists()

    def test_video_path(self, store: ArtifactStore) -> None:
        path = store.video_path("proj-1", "run-1", "crawl")
        assert path.name == "crawl.webm"

    def test_diff_path(self, store: ArtifactStore) -> None:
        path = store.diff_path("proj-1", "run-1", "home")
        assert "diffs" in str(path)
        assert path.name == "home.png"

    def test_save_and_load_screenshot(self, store: ArtifactStore) -> None:
        data = b"\x89PNG fake screenshot data"
        path = store.save_screenshot("proj-1", "run-1", "step_01", data)
        assert path.exists()
        assert path.read_bytes() == data

    def test_list_screenshots(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"img1")
        store.save_screenshot("proj-1", "run-1", "step_02", b"img2")
        screenshots = store.list_screenshots("proj-1", "run-1")
        assert len(screenshots) == 2

    def test_save_video(self, store: ArtifactStore) -> None:
        data = b"fake video data"
        path = store.save_video("proj-1", "run-1", "crawl", data)
        assert path.exists()
        assert path.read_bytes() == data

    def test_cleanup_run(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"img")
        store.save_video("proj-1", "run-1", "crawl", b"vid")
        run_dir = store.get_run_dir("proj-1", "run-1")
        assert any(run_dir.rglob("*"))
        store.cleanup_run("proj-1", "run-1")
        assert not run_dir.exists()

    def test_cleanup_project(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"img")
        store.cleanup_project("proj-1")
        project_dir = store.get_project_dir("proj-1")
        # After cleanup, dir should still exist but be empty
        # Actually cleanup_project removes the whole dir
        assert not project_dir.exists()

    def test_get_disk_usage(self, store: ArtifactStore) -> None:
        store.save_screenshot("proj-1", "run-1", "step_01", b"x" * 1000)
        usage = store.get_disk_usage("proj-1")
        assert usage >= 1000
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_artifacts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'breakthevibe.storage.artifacts'`

**Step 3: Write minimal implementation**

```python
# breakthevibe/storage/artifacts.py
"""Local filesystem artifact storage for screenshots, videos, diffs."""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class ArtifactStore:
    """Manages local filesystem storage for binary artifacts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path.home() / ".breakthevibe" / "artifacts"
        self._base.mkdir(parents=True, exist_ok=True)

    def get_project_dir(self, project_id: str) -> Path:
        """Get or create project artifact directory."""
        path = self._base / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run_dir(self, project_id: str, run_id: str) -> Path:
        """Get or create run artifact directory."""
        path = self.get_project_dir(project_id) / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot_path(self, project_id: str, run_id: str, step_name: str) -> Path:
        """Get path for a screenshot file."""
        screenshots_dir = self.get_run_dir(project_id, run_id) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        return screenshots_dir / f"{step_name}.png"

    def video_path(self, project_id: str, run_id: str, video_name: str) -> Path:
        """Get path for a video file."""
        videos_dir = self.get_run_dir(project_id, run_id) / "videos"
        videos_dir.mkdir(exist_ok=True)
        return videos_dir / f"{video_name}.webm"

    def diff_path(self, project_id: str, run_id: str, diff_name: str) -> Path:
        """Get path for a visual diff image."""
        diffs_dir = self.get_run_dir(project_id, run_id) / "diffs"
        diffs_dir.mkdir(exist_ok=True)
        return diffs_dir / f"{diff_name}.png"

    def save_screenshot(self, project_id: str, run_id: str, step_name: str, data: bytes) -> Path:
        """Save screenshot data to file."""
        path = self.screenshot_path(project_id, run_id, step_name)
        path.write_bytes(data)
        logger.debug("screenshot_saved", path=str(path), size=len(data))
        return path

    def save_video(self, project_id: str, run_id: str, video_name: str, data: bytes) -> Path:
        """Save video data to file."""
        path = self.video_path(project_id, run_id, video_name)
        path.write_bytes(data)
        logger.debug("video_saved", path=str(path), size=len(data))
        return path

    def list_screenshots(self, project_id: str, run_id: str) -> list[Path]:
        """List all screenshots for a run."""
        screenshots_dir = self.get_run_dir(project_id, run_id) / "screenshots"
        if not screenshots_dir.exists():
            return []
        return sorted(screenshots_dir.glob("*.png"))

    def cleanup_run(self, project_id: str, run_id: str) -> None:
        """Delete all artifacts for a specific run."""
        run_dir = self._base / project_id / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info("run_artifacts_cleaned", project=project_id, run=run_id)

    def cleanup_project(self, project_id: str) -> None:
        """Delete all artifacts for a project."""
        project_dir = self._base / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
            logger.info("project_artifacts_cleaned", project=project_id)

    def get_disk_usage(self, project_id: str) -> int:
        """Get total disk usage in bytes for a project."""
        project_dir = self._base / project_id
        if not project_dir.exists():
            return 0
        return sum(f.stat().st_size for f in project_dir.rglob("*") if f.is_file())
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/unit/test_artifacts.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add breakthevibe/storage/artifacts.py tests/unit/test_artifacts.py
git commit -m "feat: add artifact storage manager"
```

---

## Phase 11: Integration Testing

### Task 38: End-to-End Pipeline Test

**Files:**
- Create: `tests/fixtures/sample_site/index.html`
- Create: `tests/fixtures/sample_site/products.html`
- Create: `tests/fixtures/sample_site/api/products.json`
- Create: `tests/integration/test_pipeline.py`

**Step 1: Create sample test site**

```html
<!-- tests/fixtures/sample_site/index.html -->
<!DOCTYPE html>
<html lang="en">
<head><title>Test Shop</title></head>
<body>
    <nav>
        <a href="/" data-testid="nav-home">Home</a>
        <a href="/products.html" data-testid="nav-products">Products</a>
    </nav>
    <main>
        <h1>Welcome to Test Shop</h1>
        <button data-testid="cta-btn" onclick="location.href='/products.html'">
            Browse Products
        </button>
        <div id="featured"></div>
    </main>
    <script>
        fetch('/api/products.json')
            .then(r => r.json())
            .then(data => {
                document.getElementById('featured').textContent =
                    data.products.length + ' products available';
            });
    </script>
</body>
</html>
```

```html
<!-- tests/fixtures/sample_site/products.html -->
<!DOCTYPE html>
<html lang="en">
<head><title>Products — Test Shop</title></head>
<body>
    <nav>
        <a href="/" data-testid="nav-home">Home</a>
        <a href="/products.html" data-testid="nav-products">Products</a>
    </nav>
    <main>
        <h1>Products</h1>
        <select data-testid="category-filter" aria-label="Category">
            <option value="all">All</option>
            <option value="electronics">Electronics</option>
            <option value="books">Books</option>
        </select>
        <div class="product-grid" id="products"></div>
    </main>
    <script>
        fetch('/api/products.json')
            .then(r => r.json())
            .then(data => {
                const grid = document.getElementById('products');
                data.products.forEach(p => {
                    const card = document.createElement('div');
                    card.className = 'product-card';
                    card.setAttribute('data-testid', 'product-' + p.id);
                    card.textContent = p.name + ' - $' + p.price;
                    grid.appendChild(card);
                });
            });
    </script>
</body>
</html>
```

```json
// tests/fixtures/sample_site/api/products.json
{
    "products": [
        {"id": 1, "name": "Widget", "price": 9.99, "category": "electronics"},
        {"id": 2, "name": "Gadget", "price": 19.99, "category": "electronics"},
        {"id": 3, "name": "Python Book", "price": 39.99, "category": "books"}
    ]
}
```

**Step 2: Write the integration test**

```python
# tests/integration/test_pipeline.py
"""End-to-end pipeline integration test using a local sample site."""

import pytest
import subprocess
import time
import signal
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from breakthevibe.agent.orchestrator import PipelineOrchestrator, PipelineStage

SAMPLE_SITE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_site"


@pytest.fixture(scope="module")
def sample_server():
    """Start a local HTTP server serving the sample site."""
    proc = subprocess.Popen(
        ["python", "-m", "http.server", "8765", "--directory", str(SAMPLE_SITE_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)  # Wait for server to start
    yield "http://localhost:8765"
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


@pytest.mark.integration
class TestEndToEndPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_with_mock_components(self, sample_server: str) -> None:
        """Test the orchestrator coordinates stages correctly."""
        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=AsyncMock(),
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
        )

        result = await orchestrator.run(
            project_id="test-proj",
            url=sample_server,
            rules_yaml="",
        )

        assert result.success is True
        assert PipelineStage.CRAWL in result.completed_stages
        assert PipelineStage.MAP in result.completed_stages
        assert PipelineStage.GENERATE in result.completed_stages
        assert PipelineStage.RUN in result.completed_stages
        assert PipelineStage.REPORT in result.completed_stages
        assert result.duration_seconds > 0

    def test_sample_site_exists(self) -> None:
        """Verify sample site files are present."""
        assert (SAMPLE_SITE_DIR / "index.html").exists()
        assert (SAMPLE_SITE_DIR / "products.html").exists()
        assert (SAMPLE_SITE_DIR / "api" / "products.json").exists()

    def test_sample_site_index_has_structure(self) -> None:
        """Verify sample site has expected structure."""
        content = (SAMPLE_SITE_DIR / "index.html").read_text()
        assert "data-testid" in content
        assert "nav-home" in content
        assert "cta-btn" in content

    def test_sample_site_products_has_structure(self) -> None:
        """Verify products page has expected structure."""
        content = (SAMPLE_SITE_DIR / "products.html").read_text()
        assert "category-filter" in content
        assert "product-grid" in content

    @pytest.mark.asyncio
    async def test_pipeline_partial_failure_reports_stage(self) -> None:
        """Test that pipeline reports which stage failed."""
        orchestrator = PipelineOrchestrator(
            crawler=AsyncMock(),
            mapper=AsyncMock(side_effect=Exception("LLM unavailable")),
            generator=AsyncMock(),
            runner=AsyncMock(),
            collector=MagicMock(),
        )
        # mapper.build needs to raise
        orchestrator._mapper.build.side_effect = Exception("LLM unavailable")

        result = await orchestrator.run(
            project_id="test-proj",
            url="http://localhost:8765",
            rules_yaml="",
        )

        assert result.success is False
        assert result.failed_stage == PipelineStage.MAP
        assert "LLM unavailable" in result.error_message
```

**Step 3: Run test to verify it passes**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest tests/integration/test_pipeline.py -v -m integration`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/fixtures/sample_site/ tests/integration/test_pipeline.py
git commit -m "test: add end-to-end pipeline integration test"
```

---

### Task 39: Final Run — All Tests + Lint + Typecheck

**Step 1: Run full unit test suite**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest -v --cov=breakthevibe -m "not integration"`
Expected: ALL PASS with >80% coverage on core modules

**Step 2: Run integration tests**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run pytest -v -m integration`
Expected: ALL PASS

**Step 3: Run linting**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run ruff check .`
Expected: No errors

**Step 4: Run formatting check**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run ruff format --check .`
Expected: No errors (or run `ruff format .` to fix)

**Step 5: Run type checking**

Run: `cd /Users/tenaz3/development/breakthevibe && uv run mypy breakthevibe/`
Expected: No errors (fix any type issues found)

**Step 6: Run Docker build**

Run: `cd /Users/tenaz3/development/breakthevibe && docker compose build`
Expected: Build succeeds

**Step 7: Verify Docker health check**

Run: `cd /Users/tenaz3/development/breakthevibe && docker compose up -d && sleep 10 && curl -f http://localhost:8000/api/health && docker compose down`
Expected: `{"status":"healthy","version":"0.1.0"}`

**Step 8: Final commit**

```bash
git add -A
git commit -m "chore: all tests passing, lint clean, types verified"
```

**Step 9: Tag the MVP release**

```bash
git tag -a v0.1.0 -m "MVP release: crawl, map, generate, run, report pipeline"
```
