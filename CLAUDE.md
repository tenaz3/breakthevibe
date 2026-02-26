# BreakTheVibe - Claude Code Project Guide

## Project Overview

AI-powered QA automation platform built with Python 3.12, FastAPI, SQLModel, Playwright, and PostgreSQL (async via asyncpg). Transforms websites into automated visual regression and functional test suites.

**Active work**: Multi-tenant SaaS transformation on branch `feat/multi-tenant-saas`. See `docs/plans/2026-02-26-saas-multi-tenant-transformation.md` for the full plan (7 phases + edge cases review).

## Tech Stack

- **Language**: Python 3.12+ (strict typing, `from __future__ import annotations`)
- **Web**: FastAPI with Jinja2 SSR templates
- **ORM**: SQLModel + SQLAlchemy async (asyncpg driver)
- **Migrations**: Alembic
- **Browser**: Playwright (async)
- **LLM**: Anthropic, OpenAI, Ollama providers
- **Testing**: pytest + pytest-asyncio + pytest-xdist
- **Linting**: ruff (NOT pylint, NOT flake8)
- **Formatting**: ruff format (NOT black)
- **Type checking**: mypy --strict
- **Package manager**: uv (NOT pip, NOT poetry)

## Commands

```bash
# Run all tests
uv run pytest tests/

# Run unit tests only
uv run pytest tests/unit/

# Run integration tests only
uv run pytest tests/integration/

# Lint
uv run ruff check breakthevibe/

# Format
uv run ruff format breakthevibe/

# Type check
uv run mypy breakthevibe/ --strict

# Run migrations
uv run alembic upgrade head

# Check for pending migrations
uv run alembic check

# Start dev server
uv run uvicorn breakthevibe.web.app:create_app --factory --reload --port 8000
```

## Project Structure

```
breakthevibe/
  config/settings.py          # Pydantic BaseSettings, env vars
  models/database.py          # SQLModel tables
  web/
    app.py                    # FastAPI factory
    dependencies.py           # DI (module-level singletons, refactoring to Depends)
    auth/session.py           # HMAC cookie sessions
    middleware.py              # Rate limiter, request ID
    routes/                   # 7 route files
  storage/
    artifacts.py              # Local filesystem artifact store
    database.py               # AsyncEngine singleton
    repositories/             # In-memory + PostgreSQL repos
    migrations/               # Alembic migrations
  agent/orchestrator.py       # 5-stage pipeline
  crawler/                    # Playwright-based crawler
  generator/                  # Test code generation
  runner/                     # Test execution
tests/
  unit/                       # 333 unit tests
  integration/                # Integration tests (DB, browser)
  conftest.py                 # Shared fixtures
  fixtures/                   # Test data
```

## Code Quality

### Before committing any changes, always run:
1. `uv run ruff format breakthevibe/ tests/` - format code
2. `uv run ruff check breakthevibe/ tests/ --fix` - fix lint issues
3. `uv run pytest tests/` - run full test suite
4. Fix any failures before committing

### Conventions
- Follow existing patterns in the codebase
- Use `structlog` for logging (not stdlib `logging`)
- Async-first for all I/O operations
- Type hints on all function signatures
- ruff rules: E, F, I, N, W, UP, B, A, SIM, TCH (see pyproject.toml)
- Line length: 100 characters
- Exclude migrations from linting: `breakthevibe/storage/migrations/versions`

## Git & Commits

- Review staged files with `git diff --cached --name-only` before committing
- Never include unrelated files in commits
- Never commit `.env`, credentials, or API keys
- Use conventional commit messages (feat:, fix:, docs:, refactor:, test:)
- Current active branch: `feat/multi-tenant-saas`

## Database Operations

- When modifying upserts or bulk operations, verify which fields are written and that defaults don't overwrite existing data
- Use `INSERT ... ON CONFLICT DO UPDATE` for idempotent operations
- Always include `org_id` filtering in tenant-scoped queries (after Phase 1)
- Test data preservation cases specifically when touching DB write paths
- Migrations: add nullable columns first, backfill, then add NOT NULL

## Debugging

- Before attempting fixes, add diagnostic logging to confirm the actual code path being executed
- Don't change approach more than once without first gathering data (logs, reproduction tests)
- Use `structlog.get_logger(__name__)` for debug logging

## Testing

- Run the full test suite before committing, not just related tests
- Use `@pytest.mark.unit` and `@pytest.mark.integration` markers
- asyncio_mode is "auto" (no need for `@pytest.mark.asyncio`)
- Test files: `tests/unit/test_*.py`, `tests/integration/test_*.py`
- Use fixtures from `tests/conftest.py` and `tests/fixtures/`

## Security

- Never store secrets in code or database without encryption
- Validate all user-provided paths (prevent path traversal with `.resolve()` check)
- Use parameterized queries (SQLModel/SQLAlchemy handles this)
- Sanitize user input displayed in Jinja2 templates (auto-escaping is on)
- SSRF protection: block private IPs in crawler
