# BreakTheVibe - Design Document

**Date:** 2026-02-24
**Status:** Approved

## Overview

BreakTheVibe is an AI-powered QA automation platform that crawls public websites, maps their structure into an interactive mind-map, generates test suites (functional, visual regression, API validation), and runs them automatically. It targets the same space as qa.tech but as a self-hosted, provider-agnostic tool.

## Goals (MVP)

- Crawl real public websites including SPAs
- Build a page-level + component-level mind-map of the site
- Generate and execute meaningful test suites across 3 categories
- Provide a web dashboard with detailed step-by-step test result replays
- Support configurable rules for crawl behavior, input data, and test generation
- Provider-agnostic LLM layer (Claude as default)

## Architecture

Hybrid pipeline + agent system with 7 core modules.

```
+-----------------------------------------------------+
|                    Agent Layer                        |
|           (orchestrates, retries, adapts)             |
+------+--------+----------+--------+--------+---------+
|Crawl | Mapper | Generator| Runner |Reporter| Config  |
|      |        |          |        |        |         |
|Play- |Mind-map| Test case| Pytest | Web UI | Rules   |
|wright|builder | + suite  |executor| + logs | Engine  |
|+Net  |        | builder  |        |        |         |
+------+--------+----------+--------+--------+---------+
         ^                                |
         |       LLM Provider Layer       |
         +--------------------------------+
```

### Flow

1. **Crawler** navigates the target site, captures pages/components/network traffic/video
2. **Mapper** builds a structured mind-map from crawl data via LLM classification
3. **Generator** produces test cases and executable pytest code using the mind-map + optional OpenAPI spec
4. **Runner** executes tests with smart parallel/sequential scheduling
5. **Reporter** serves results in a web dashboard with replays and diffs
6. **Config/Rules Engine** governs behavior across all modules
7. **Agent Layer** monitors pipeline, retries failures, re-plans via LLM

## Module Details

### 1. Crawler

Playwright-based, SPA-aware browser automation.

**Page Discovery:**
- Starts at root URL, follows links, detects SPA route changes (popstate, hashchange, History API)
- Respects crawl rules (max depth, skip patterns, allowed domains)
- Handles infinite scroll by scrolling incrementally and detecting new content

**Component Extraction:**
- Accessibility snapshot + DOM analysis per page/route
- Identifies interactive elements: buttons, forms, inputs, modals, dropdowns, tabs
- Captures element metadata: selectors, text content, ARIA roles, visibility state

**Network Capture:**
- Intercepts all XHR/Fetch requests during navigation
- Records: URL, method, headers, request/response bodies, status codes
- Matches API calls to the UI actions that triggered them

**Recording:**
- Screenshots at key interaction points (before/after clicks, form fills)
- Video recording of full crawl session using Playwright's built-in `record_video_dir`
- Videos segmented per route for reference in reporter

**Output:** Structured JSON artifact per route + screenshots + video files.

### 2. Mapper

LLM-powered site structure builder.

**Mind-Map Structure:**
```
Site
+-- Route: /home
|   +-- Components: [navbar, hero-banner, footer]
|   +-- Interactions: [nav-links, CTA-button, scroll]
|   +-- API calls: [GET /api/featured]
|   +-- Screenshots/Video: [ref]
+-- Route: /products
|   +-- Components: [navbar, product-grid, filters, pagination]
|   +-- Interactions: [filter-select, sort-dropdown, page-click]
|   +-- API calls: [GET /api/products, GET /api/categories]
|   +-- Screenshots/Video: [ref]
```

**Process:**
1. Parses crawler JSON artifacts per route
2. LLM classifies and groups raw DOM elements into meaningful components
3. Identifies relationships between routes (e.g., card click navigates to detail page)
4. Merges observed network traffic with imported OpenAPI spec, flags mismatches
5. Outputs `site-map.json` stored in PostgreSQL

### 3. Generator

LLM-powered test case and code generation.

**Test Categories:**

1. **Functional tests** - user journey based
   - Happy paths, edge cases, cross-page flows
2. **Visual regression tests** - screenshot comparison
   - Baseline capture, pixel diffing via pixelmatch
   - LLM identifies visually critical vs decorative components
3. **API validation tests** - contract testing
   - From observed traffic: validate status codes, response schemas
   - From OpenAPI spec: verify documented endpoints
   - Cross-check: API responses vs UI rendering

**Resilient Selector Strategy:**

Each action uses an ordered selector chain (most stable to least stable):
1. `data-testid` / `data-test`
2. ARIA role + accessible name
3. Text content
4. Semantic HTML structure
5. Structural path
6. CSS selector (last resort)

```python
{
    "action": "click",
    "selectors": [
        {"strategy": "test_id", "value": "add-to-cart-btn"},
        {"strategy": "role", "value": "button", "name": "Add to cart"},
        {"strategy": "text", "value": "Add to cart"},
        {"strategy": "css", "value": ".product-detail .btn-primary"}
    ]
}
```

Runner tries each in order. First match wins. If a preferred selector breaks but a lower-priority one succeeds, the test passes but flags a "healed" warning.

**Output:** Structured test case objects + executable pytest code.

**Rules Integration:** Checks config before generating - skips excluded routes/endpoints, injects predefined input data, respects interaction rules.

### 4. Runner

pytest + Playwright test execution engine.

**Execution Modes:**
- **Sequential** - tests with shared state (future auth flows)
- **Parallel** - independent tests via pytest-xdist
- **Smart (default)** - agent analyzes dependencies, auto-decides parallel vs sequential

**Per-suite override:**
```yaml
execution:
  mode: smart
  suites:
    auth-flow:
      mode: sequential
      shared_context: true
    product-pages:
      mode: parallel
      workers: 4
```

**Per Step:** Captures screenshot, network activity, console logs. Records video of full test run.

**Retry Logic:**
- Failed steps retried once with short delay
- Agent layer can re-analyze page and attempt alternatives on retry failure
- Max retries configurable, then marks as failed with full diagnostics

### 5. Reporter

FastAPI web dashboard.

**Pages:**
1. **Project overview** - crawled sites, last run status, quick stats
2. **Mind-map viewer** - interactive tree visualization (D3.js)
3. **Test suite browser** - browse by route/category, edit rules inline
4. **Run results** - per-run view with:
   - Pass/fail summary
   - Step-by-step replay with screenshots + video playback
   - Network log timeline
   - Console log capture
   - Visual regression diffs (side-by-side)
   - Healed selector warnings
5. **Rules editor** - YAML editor with validation
6. **LLM settings** - provider/model selection per module, API key management

### 6. Config / Rules Engine

YAML-based configuration per project, editable through web UI.

```yaml
crawl:
  max_depth: 5
  skip_urls: ["/admin/*", "/api/internal/*"]
  scroll_behavior: incremental
  wait_times:
    page_load: 3000
    after_click: 1000
  viewport: { width: 1280, height: 800 }

inputs:
  email: "test@example.com"
  phone: "+1234567890"

interactions:
  cookie_banner: dismiss
  modals: close_on_appear
  infinite_scroll: scroll_3_times

tests:
  skip_visual: ["/404"]
  custom_assertions: []

api:
  ignore_endpoints: ["/api/analytics/*"]
  expected_overrides:
    "GET /api/health": { status: 200 }

execution:
  mode: smart
  suites: {}

llm:
  default_provider: anthropic
  default_model: claude-sonnet-4-20250514
  modules:
    mapper: { provider: anthropic, model: claude-sonnet-4-20250514 }
    generator: { provider: anthropic, model: claude-opus-4-0-20250115 }
    agent: { provider: anthropic, model: claude-sonnet-4-20250514 }
  providers:
    anthropic: { api_key: "${ANTHROPIC_API_KEY}" }
    openai: { api_key: "${OPENAI_API_KEY}" }
    ollama: { base_url: "http://localhost:11434" }
```

### 7. Agent Layer

Thin orchestration layer on top of the pipeline.

- Coordinates pipeline execution: crawl -> map -> generate -> run -> report
- Monitors each stage for failures
- On failure: retries with adjusted parameters, or asks LLM to re-plan
- Handles unexpected scenarios (SPA loads slowly, element not found, API timeout)

## Tech Stack

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Runtime |
| FastAPI | 0.128+ | Web framework, async API |
| SQLModel | Latest | ORM + Pydantic validation (SQLAlchemy + Pydantic) |
| PostgreSQL | 16 | Primary database |
| asyncpg | Latest | Async PostgreSQL driver |
| Alembic | Latest | Database migrations |
| Playwright (Python) | 1.58+ | Browser automation, video recording, network interception |
| Anthropic SDK | Latest | Claude integration (default LLM) |
| pytest | Latest | Test execution framework |
| pytest-xdist | Latest | Parallel test execution |
| pixelmatch / Pillow | Latest | Visual regression diffing |
| httpx | Latest | Async HTTP client for API tests |
| structlog | Latest | Structured logging (JSON in prod, pretty in dev) |
| htmx | Latest | Web UI interactivity |
| D3.js | Latest | Mind-map visualization |
| uv | Latest | Package management + lockfile |
| Ruff | Latest | Linting + formatting |
| mypy | Latest | Static type checking |
| Docker | Latest | Containerized deployment |

All technologies verified as current via Context7 (Feb 2026).

## Project Structure

```
breakthevibe/
├── pyproject.toml
├── uv.lock
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── .python-version
├── Makefile
├── alembic.ini
│
├── breakthevibe/
│   ├── __init__.py
│   ├── main.py                 # CLI + app entrypoint
│   ├── exceptions.py           # exception hierarchy
│   ├── constants.py            # defaults, timeouts, limits
│   ├── types.py                # enums, type aliases
│   │
│   ├── config/
│   │   ├── settings.py         # Pydantic BaseSettings (.env loading)
│   │   └── logging.py          # structlog configuration
│   │
│   ├── models/
│   │   ├── database.py         # SQLModel table models
│   │   ├── domain.py           # inter-module data contracts
│   │   └── api.py              # request/response schemas
│   │
│   ├── agent/
│   │   ├── orchestrator.py     # pipeline coordinator
│   │   └── planner.py          # re-plan/retry logic
│   │
│   ├── crawler/
│   │   ├── browser.py          # Playwright management + video recording
│   │   ├── navigator.py        # SPA-aware page discovery
│   │   ├── extractor.py        # component + DOM extraction
│   │   └── network.py          # API traffic capture
│   │
│   ├── mapper/
│   │   ├── builder.py          # mind-map construction
│   │   ├── classifier.py       # LLM component grouping
│   │   └── api_merger.py       # traffic + OpenAPI spec merge
│   │
│   ├── generator/
│   │   ├── case_builder.py     # LLM test case generation
│   │   ├── code_builder.py     # pytest code generation
│   │   ├── selector.py         # resilient selector chain builder
│   │   └── rules/
│   │       ├── engine.py       # rules engine
│   │       └── schema.py       # rules validation
│   │
│   ├── runner/
│   │   ├── executor.py         # pytest execution engine
│   │   ├── parallel.py         # smart parallelism logic
│   │   └── healer.py           # self-healing selector recovery
│   │
│   ├── reporter/
│   │   ├── collector.py        # results + artifact gathering
│   │   └── diff.py             # visual regression comparison
│   │
│   ├── llm/
│   │   ├── provider.py         # abstract LLM interface
│   │   ├── anthropic.py        # Claude implementation
│   │   ├── openai.py           # OpenAI implementation
│   │   └── ollama.py           # local model implementation
│   │
│   ├── storage/
│   │   ├── database.py         # async engine + session factory
│   │   ├── repositories/       # data access per domain
│   │   ├── artifacts.py        # screenshot/video file storage
│   │   └── migrations/         # Alembic versions
│   │
│   ├── utils/
│   │   ├── retry.py            # shared retry/backoff decorator
│   │   ├── timing.py           # performance measurement
│   │   └── sanitize.py         # URL + input sanitization
│   │
│   └── web/
│       ├── app.py              # FastAPI app factory
│       ├── routes/             # API + page routes
│       ├── middleware.py        # CORS, rate limiting, request ID
│       ├── auth/               # session authentication
│       ├── dependencies.py     # FastAPI dependency injection
│       ├── templates/          # Jinja2 + htmx templates
│       └── static/             # CSS, JS, D3 visualizations
│
├── tests/
│   ├── conftest.py             # shared fixtures (test DB, mock LLM)
│   ├── unit/                   # mirrors breakthevibe/ modules
│   ├── integration/            # pipeline + API tests
│   └── fixtures/               # sample HTML, mock LLM responses
│
├── scripts/
│   ├── start.sh
│   ├── migrate.sh
│   └── seed.sh
│
└── docs/
    └── plans/
```

## Production Essentials

- **Settings:** Pydantic BaseSettings with .env loading, typed + validated
- **Logging:** structlog with JSON output in production, pretty in development, async support, correlation IDs per pipeline run
- **Exceptions:** Hierarchy from BreakTheVibeError base: CrawlerError, LLMProviderError, GeneratorError, RunnerError, StorageError
- **Types:** Enums for TestStatus, LLMProvider, BrowserType; type aliases for TestCaseID, URL, Selector
- **Database:** PostgreSQL 16 via asyncpg, SQLModel ORM, Alembic migrations
- **Security:** SSRF protection (block private IPs), URL sanitization, detect-secrets in pre-commit, rate limiting on LLM-triggering endpoints, session auth for web UI
- **CI:** Ruff lint + format, mypy strict, pytest with coverage, pip-audit, bandit, Docker build + health check
- **Docker:** Multi-stage build with mcr.microsoft.com/playwright/python base, docker-compose with Postgres service

## Storage

- **PostgreSQL** for all structured data: page metadata, component trees, API maps, test cases, test results, config/rules, LLM settings
- **Local filesystem** for binary artifacts: `~/.breakthevibe/projects/<project-id>/artifacts/` containing screenshots, videos, visual regression diffs
- Migratable to S3/cloud bucket later

## Future Considerations (Post-MVP)

- Authenticated website testing (login flows)
- CI/CD integration (GitHub Actions, GitLab CI)
- Multi-user support with role-based access
- Cloud artifact storage (S3)
- Webhook notifications (Slack, email)
- Test scheduling (cron-based re-runs)
- Mobile testing support
