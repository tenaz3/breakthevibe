# BreakTheVibe — Consolidated Audit Report

**Date:** 2026-03-20
**Scope:** Production Readiness (1.1) + Extended Audit (1.2) + Deep Feature Audit (1.3)
**Auditors:** 3 parallel AI agents performing static analysis

---

## Executive Summary

| Severity | Unique Findings |
|----------|----------------|
| Critical | 12 |
| High | 10 |
| Medium | 15 |
| Low | 10 |
| **Total** | **47** |

The codebase has **12 critical issues** that must be resolved before any production deployment. The top 5 are: SSRF enabled by default, auth bypass when credentials are unset, plaintext API key storage, in-memory sessions that don't survive restarts, and a missing tenant check on the SSE progress endpoint.

---

## CRITICAL FINDINGS (Fix Before Deploy)

### CRIT-1: SSRF Enabled by Default — `allow_private_urls = True`
**Files:** `config/settings.py:52`, `utils/sanitize.py:14-31`
**Effort:** Quick

The crawler's SSRF guard is disabled by default. Any authenticated user can crawl `http://169.254.169.254/` (AWS metadata), internal databases, and private network services. Additionally, `is_safe_url` only checks the parsed hostname string — a domain resolving to a private IP (DNS rebinding) bypasses the check entirely.

**Fix:** Flip default to `False`. Resolve hostnames via `socket.getaddrinfo` and check all returned IPs against private/link-local/loopback ranges.

---

### CRIT-2: Auth Bypass When `admin_username`/`admin_password` Are Unset
**File:** `web/routes/auth.py:83-88`
**Effort:** Quick

When `auth_mode == "single"` and credentials are not configured, the login check is entirely skipped — any username/password succeeds. This is the default for any deploy that forgets to set these env vars.

**Fix:** Reject login with 503 ("Not configured") when credentials are unset, rather than accepting everything.

---

### CRIT-3: Default `secret_key = "change-me-in-production"`
**File:** `config/settings.py:22`
**Effort:** Quick

Only a `warnings.warn` is emitted. Session HMAC signatures use this known-public key. Any attacker can forge session tokens.

**Fix:** `raise RuntimeError` if `SECRET_KEY` is the default and `environment != "development"`.

---

### CRIT-4: API Keys Stored in Plaintext in Database
**Files:** `web/routes/settings.py:112-119`, `models/database.py:261-268`
**Effort:** Medium

LLM API keys (Anthropic, OpenAI, Google) are written directly into `llm_settings.value_json` without encryption. A DB dump or misconfigured backup exposes all tenant API keys.

**Fix:** Encrypt with `cryptography.fernet` before insert, decrypt on read. Store encryption key in env var or secrets manager.

---

### CRIT-5: In-Memory Session Store — No Horizontal Scale
**File:** `web/auth/session.py:23`
**Effort:** Medium

`SessionAuth._sessions` is a plain Python `dict`. Multiple uvicorn workers, pod restarts, or deploys silently invalidate all sessions. No eviction beyond per-request expiry check — unbounded memory growth.

**Fix:** Replace with Redis or DB-backed session table. Add periodic sweep for expired entries.

---

### CRIT-6: SSE Progress Endpoint Missing Tenant Check
**File:** `web/routes/crawl.py` (progress endpoint)
**Effort:** Quick

`/api/projects/{project_id}/progress` has no `org_id` verification. Any logged-in user from any organization can watch any other organization's pipeline by guessing an integer project ID.

**Fix:** Add `org_id` filter to the progress query, same as other tenant-scoped endpoints.

---

### CRIT-7: Open Passkey Registration Race Condition
**File:** `web/routes/auth.py:136-141`
**Effort:** Medium

Two concurrent requests can both see `has_credentials = False` and both create admin accounts. No invite-token mechanism exists for subsequent users.

**Fix:** Use atomic `INSERT ... ON CONFLICT DO NOTHING` or DB-level unique constraint under a transaction. Add invite-token flow for additional users.

---

### CRIT-8: Test Dependencies Shipped in Production
**File:** `pyproject.toml:17-20`
**Effort:** Quick

`pytest`, `pytest-xdist`, `pytest-asyncio` are listed under `[project.dependencies]` (runtime), not `[dependency-groups].dev`. Bloats Docker image and increases attack surface.

**Fix:** Move test dependencies to `[dependency-groups].dev`.

---

### CRIT-9: `asyncio.get_event_loop()` Deprecated — Will Error in Future Python
**Files:** `crawler/crawler.py:104`, `runner/executor.py:199`
**Effort:** Quick

`asyncio.get_event_loop().create_task(...)` inside an already-running async context is deprecated since Python 3.10. Will become an error in future versions.

**Fix:** Replace with `asyncio.get_running_loop().create_task(...)`.

---

### CRIT-10: Project Delete Is Not Atomic — Partial Deletes on Crash
**File:** `storage/repositories/db_projects.py:82-120`
**Effort:** Medium

Multiple separate `DELETE` statements across `TestResult`, `TestRun`, `TestCase`, `CrawlRun`, `Route` without a single transaction. Process crash mid-cascade leaves inconsistent state.

**Fix:** Wrap in `async with session.begin():` or add `ON DELETE CASCADE` foreign keys via Alembic migration.

---

### CRIT-11: Pipeline Triggers All Run Identical 5-Stage Pipeline
**File:** `web/dependencies.py` (run_pipeline)
**Effort:** Large

All three pipeline triggers (crawl/generate/run) execute the identical full 5-stage pipeline. The semantic split between "just crawl" vs "just run tests" is an illusion.

**Fix:** Accept a `stages` parameter to selectively execute pipeline stages.

---

### CRIT-12: JobQueue/JobWorker System Is Dead Code
**Files:** `worker/queue.py`, `worker/runner.py`
**Effort:** Medium

No HTTP route calls `queue.enqueue()`. The "Jobs" UI (`GET /api/jobs`) always returns an empty list. The entire system is unused.

**Fix:** Either wire it up to the pipeline or remove it entirely to reduce maintenance burden.

---

## HIGH FINDINGS (Fix Before Scale)

### HIGH-1: No Pagination on Core Queries
**Files:** `storage/repositories/test_runs.py:138-154`, `storage/repositories/db_projects.py:59-67`

`list_for_project` and `list_all` issue unbounded `SELECT *` queries. Hundreds of projects or thousands of test runs load entirely into memory.

**Fix:** Add `limit`/`offset` parameters, defaulting to `limit=50`.

---

### HIGH-2: Missing Composite Indexes for Tenant Queries
**File:** `models/database.py:78-105`

Every query filters on `org_id AND project_id` but only single-column indexes exist. Full table scans within org partitions as data grows.

**Fix:** Add composite indexes: `(org_id, project_id)`, `(org_id, created_at DESC)`.

---

### HIGH-3: Process-Local Rate Limiter
**File:** `web/middleware.py:34`

Each uvicorn worker has independent counters. Effective limit = `60 * num_workers` per window.

**Fix:** Back with Redis sliding window counter.

---

### HIGH-4: 3 Sequential DB Round-Trips Per Clerk Auth Request
**File:** `web/auth/rbac.py:93-127`

Every authenticated request in Clerk mode executes 3 separate SELECTs (user, org, membership).

**Fix:** Single JOIN query + short-lived cache (TTL ~30s).

---

### HIGH-5: `recover_stale_jobs` Runs Every 2s — No Throttle
**File:** `worker/runner.py:47`

Executes an UPDATE query on every poll iteration (every 2 seconds) regardless of whether recovery is needed.

**Fix:** Track `_last_recovery_at`, call only every 5 minutes.

---

### HIGH-6: `_pipeline_locks` Dict Leaks on Pipeline Crash
**File:** `web/dependencies.py:56-61, 207-208`

If pipeline is cancelled before cleanup, the lock entry remains forever, permanently blocking future runs for that project.

**Fix:** Move cleanup to `finally` block. Use `setdefault` for atomic dict access.

---

### HIGH-7: `AuditLogger` Created on Every `audit()` Call
**File:** `audit/logger.py:139-140`

Each call opens a dedicated DB connection from the pool. Under load, exhausts connection pool.

**Fix:** Module-level singleton pattern.

---

### HIGH-8: Unbounded JSON Blobs in DB Columns
**File:** `models/database.py:136, 157-161`

`suites_json`, `network_log_json`, `console_log_json`, `steps_log_json` stored as TEXT. Large crawls generate hundreds of KB per row.

**Fix:** Move large artifacts to object store, store only reference in DB. Use JSONB for queryable fields.

---

### HIGH-9: `LlmSetting.key` Global Unique Constraint Blocks Multi-Tenancy
**File:** `models/database.py:266`

`unique=True` on `key` is table-wide, not scoped to `org_id`. Two orgs cannot both have a `default_provider` setting.

**Fix:** Change to composite unique constraint `(org_id, key)`.

---

### HIGH-10: No Timeout on LLM Provider HTTP Calls
**Files:** `llm/anthropic.py`, `llm/openai_provider.py`, `llm/gemini_provider.py`, `llm/ollama_provider.py`

No explicit timeout. Hung upstream holds pipeline worker indefinitely.

**Fix:** Set `timeout=120.0` on all HTTP clients. Make configurable.

---

## MEDIUM FINDINGS (Fix Before GA)

| ID | Issue | File | Effort |
|----|-------|------|--------|
| M-1 | No request body size limit on YAML endpoints | `routes/settings.py:63,82` | Quick |
| M-2 | No graceful shutdown of in-flight pipelines | `web/app.py:41-50` | Medium |
| M-3 | `pool_size=5` hardcoded — undersized for production | `storage/database.py:18-24` | Quick |
| M-4 | No `X-Request-ID` propagation to background tasks | `web/dependencies.py:64-208` | Quick |
| M-5 | `recover_stale_jobs` resets `started_at = NULL` — loses diagnostics | `worker/queue.py:201-211` | Quick |
| M-6 | `list_jobs` hardcoded `limit=50`, no pagination | `worker/queue.py:143` | Quick |
| M-7 | `is_safe_url` allows `http://` and doesn't block `ftp://`/`file://` | `utils/sanitize.py:14` | Quick |
| M-8 | Rate limiter doesn't cover auth endpoints specifically | `web/middleware.py:76` | Quick |
| M-9 | Health check leaks `auth_mode` to unauthenticated callers | `web/health.py:17` | Quick |
| M-10 | `AuditLogger` swallows exceptions — audit gaps invisible | `audit/logger.py:117-123` | Quick |
| M-11 | `last_run_id`/`last_run_at` not persisted — ephemeral dict fields | `repositories/db_projects.py:148-151` | Medium |
| M-12 | `suites_by_route` uses fragile string splitting for route paths | `routes/pages.py:125-136` | Medium |
| M-13 | `_resolve_clerk_tenant` bypasses FastAPI session DI | `web/auth/rbac.py:93` | Quick |
| M-14 | `UsageRecord` missing composite unique constraint | `models/database.py:186-195` | Quick |
| M-15 | Crawler uses `list.pop(0)` — O(n) BFS queue | `crawler/crawler.py:118` | Quick |

---

## LOW FINDINGS (Cleanup)

| ID | Issue | File |
|----|-------|------|
| L-1 | Hardcoded version `"0.1.0"` in health check | `web/health.py:17` |
| L-2 | Truncated HMAC signature (32 of 64 hex chars) | `web/auth/session.py:72` |
| L-3 | No composite index on `audit_logs (org_id, created_at)` | migrations |
| L-4 | Register page renders even when credentials exist | `routes/auth.py:50-60` |
| L-5 | `video_url` search breaks on first non-None, not best match | `routes/pages.py:181-188` |
| L-6 | `replay_steps_json` template injection risk in `<script>` | `routes/pages.py:208` |
| L-7 | No CSP nonce for inline scripts | templates |
| L-8 | Dependencies have no upper bounds in pyproject.toml | `pyproject.toml:6-30` |
| L-9 | Jinja2Templates instantiated once per route file | routes |
| L-10 | Worker has no circuit breaker / exponential backoff | `worker/runner.py` |

---

## Recommended Fix Order

### Phase 1: Security (1-2 days)
1. CRIT-1: SSRF default + DNS rebinding
2. CRIT-2: Auth bypass on unset credentials
3. CRIT-3: Secret key fail-fast
4. CRIT-4: Encrypt API keys at rest
5. CRIT-6: SSE tenant check
6. M-7: Scheme allowlist in `is_safe_url`

### Phase 2: Data Integrity (1 day)
7. CRIT-10: Atomic project delete
8. HIGH-9: `LlmSetting` composite unique constraint
9. M-14: `UsageRecord` composite unique constraint
10. HIGH-2: Composite indexes

### Phase 3: Scalability (2-3 days)
11. CRIT-5: External session store
12. HIGH-1: Pagination on all list queries
13. HIGH-3: Redis-backed rate limiter
14. HIGH-4: Single JOIN for Clerk tenant resolution
15. HIGH-7: AuditLogger singleton
16. M-3: Configurable pool size

### Phase 4: Reliability (1-2 days)
17. HIGH-10: LLM provider timeouts
18. HIGH-5: Throttle stale job recovery
19. HIGH-6: Pipeline lock cleanup in finally
20. CRIT-9: Fix deprecated asyncio calls
21. M-2: Graceful shutdown

### Phase 5: Cleanup (1 day)
22. CRIT-8: Move test deps to dev group
23. CRIT-11: Selective pipeline stages
24. CRIT-12: Remove or wire up dead JobQueue code
25. Remaining Medium and Low items

---

## Feature Coverage Matrix (from Audit 1.3)

| Feature | Routes | DB | Tests | Edge Cases | Status |
|---------|--------|----|-------|------------|--------|
| Project CRUD | Yes | Yes | Good | Partial | Working, needs pagination |
| Crawling | Yes | Yes | Good | Missing SSRF protection | Working, security gaps |
| Test Generation | Yes | Yes | Partial | Minimal | Working |
| Test Execution | Yes | Yes | Partial | No timeout handling | Working, reliability gaps |
| Test Results | Yes | Yes | Good | No pagination | Working |
| Auth (Single) | Yes | Memory | Good | Auth bypass on no config | Broken default |
| Auth (Passkey) | Yes | DB | Partial | Registration race | Working, edge cases |
| Auth (Clerk) | Yes | DB | Minimal | 3 round-trips per request | Working, perf issues |
| LLM Settings | Yes | Yes | Partial | Global unique key bug | Broken for multi-tenant |
| Rules Editor | Yes | Yes | Partial | No size limit | Working |
| Job Queue | Yes | Yes | None | Dead code | Not functional |
| Audit Logging | Backend | Yes | Minimal | Silent failures | Working, gaps invisible |
| SSE Progress | Yes | Memory | None | No tenant check | Security hole |
| Health Check | Yes | N/A | Good | Leaks config | Working |
