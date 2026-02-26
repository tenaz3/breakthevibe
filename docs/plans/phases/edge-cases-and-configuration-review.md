# Edge Cases & Configuration Review

> **Date**: 2026-02-26
> **Scope**: Cross-cutting review of all 7 SaaS transformation phases
> **Purpose**: Identify edge cases, race conditions, configuration gaps, and security issues before implementation

---

## Summary

| Severity | Count | Status |
|---|---|---|
| Critical | 7 | Must fix during implementation |
| High | 8 | Must fix during implementation |
| Medium | 11 | Should fix, can be deferred short-term |
| Low | 12 | Nice-to-have improvements |

---

## CRITICAL Issues

### C-1. Cross-Tenant Data Leak: `pipeline_results` In-Memory Cache
**Phase**: 1 (partial), 6 (resolves fully)
**Files**: `web/dependencies.py`, `web/routes/results.py`, `web/routes/pages.py`

The global `pipeline_results: dict[str, dict]` is keyed only by `project_id`. In multi-tenant mode with integer PKs, two tenants can have projects with the same ID. The `/api/runs/{run_id}/results` endpoint iterates over **all** pipeline results without org_id filtering.

**Fix**: Phase 1 must namespace the cache key as `f"{org_id}:{project_id}"` (already noted in the plan). Phase 6 removes BackgroundTasks entirely, but during transition, **all reads from `pipeline_results`** in `results.py` and `pages.py` must also use the namespaced key. Add explicit cross-tenant guard: return 404 if the cache entry's org_id doesn't match the caller's.

---

### C-2. Cross-Tenant Data Leak: `results.py` Missing From Route Refactor
**Phase**: 1
**Files**: `web/routes/results.py`

Both `get_run_results()` and `get_project_results()` are protected routes but the Phase 1 detailed plan's route refactor section covers projects, crawl, tests, settings, and pages — but results.py only gets a brief mention for cache key changes. The `get_run_results` function needs the same Depends + RBAC treatment as all other routes, plus tenant-scoped DB queries when reading from the database (not just the cache).

**Fix**: Add `results.py` to the Phase 1 route refactor with full Depends injection, RBAC, and tenant-scoped queries.

---

### C-3. JWKS Fetch Failure Returns Raw 500 Error
**Phase**: 2
**Files**: `web/auth/clerk.py` (planned)

If Clerk's JWKS endpoint is temporarily unavailable, `resp.raise_for_status()` raises an `httpx.HTTPStatusError` that propagates as an unhandled 500 with internal details (URL, response body). With multiple workers doing concurrent refreshes, this creates a thundering-herd problem.

**Fix**: Wrap JWKS fetch in try/except, return cached JWKS on fetch failure (stale is better than broken), log the error. Add jitter to the TTL to prevent all workers refreshing simultaneously.

---

### C-4. Webhook Idempotency: Concurrent Retries Cause IntegrityError
**Phase**: 2
**Files**: `web/auth/webhook.py` (planned)

Clerk retries failed webhook deliveries. Two concurrent deliveries of `organizationMembership.created` could both SELECT nothing, then both INSERT, violating the unique constraint on `clerk_membership_id`. The code does not catch `IntegrityError`.

**Fix**: Wrap INSERT operations in try/except `IntegrityError` and treat it as a successful idempotent operation (the other request already handled it). Alternatively, use `INSERT ... ON CONFLICT DO UPDATE`.

---

### C-5. Usage Increment Race Condition (TOCTOU)
**Phase**: 3
**Files**: `web/usage.py` (planned)

Between `usage.check("crawls")` and `usage.increment("crawls")`, a concurrent request can also pass the check, exceeding the limit. The `increment()` method does SELECT-then-INSERT/UPDATE without `FOR UPDATE` or `ON CONFLICT`.

**Fix**: Use `INSERT ... ON CONFLICT (org_id, metric, period_start) DO UPDATE SET count = count + 1` for atomic increment. Move the check+increment into a single transaction with `SELECT ... FOR UPDATE` on the usage record.

---

### C-6. LLM API Keys Stored Unencrypted in Database
**Phase**: 1, 3 (design gap)
**Files**: `storage/repositories/llm_settings.py`, `web/routes/settings.py`

Each tenant's LLM API keys are stored as plain JSON in the `llm_settings` table. A database compromise exposes all tenants' keys. SOC 2 data-at-rest control is not met.

**Fix**: Add application-level encryption for sensitive settings using Fernet (from `cryptography` package, already a Phase 2 dependency). Store encrypted values with a prefix like `enc:` to distinguish from plain values. Derive the encryption key from `SECRET_KEY`. Add to Phase 1 or Phase 2 implementation.

---

### C-7. LocalObjectStore Path Traversal Vulnerability
**Phase**: 7
**Files**: `storage/local_store.py` (planned)

`_path()` does `self._base / key` where `key` is influenced by user data. A crafted key with `../` sequences could read/write/delete arbitrary files on the server.

**Fix**: Validate that the resolved path is under `self._base`:
```python
def _path(self, key: str) -> Path:
    path = (self._base / key).resolve()
    if not str(path).startswith(str(self._base.resolve())):
        raise ValueError(f"Invalid object key: {key}")
    return path
```

---

## HIGH Issues

### H-1. `TenantScopedSession` Does Not Enforce org_id on Queries
**Phase**: 1
**Files**: `storage/tenant_session.py` (planned)

The wrapper just carries `org_id` — it doesn't validate that queries include `WHERE org_id = ...`. Every new query is a potential cross-tenant leak if a developer forgets the filter.

**Fix (pragmatic)**: Accept this as a convention-based approach (same as Django's `manager.filter(tenant=...)` pattern) but add integration tests that verify tenant isolation for every query path. Document the convention clearly. Consider a `SQLAlchemy event listener` that logs warnings when queries on tenant-scoped tables don't include `org_id` in WHERE clauses (development/test mode only).

---

### H-2. `_persist_test_run` Missing org_id
**Phase**: 1
**Files**: `web/dependencies.py` `_persist_test_run()` function

Creates `TestRun` without `org_id`. After Phase 1 migration adds NOT NULL `org_id`, all background pipeline runs will fail with constraint violations.

**Fix**: Update `_persist_test_run()` to accept and set `org_id`. The `run_pipeline()` function already receives `org_id` in the Phase 1 plan — pass it through to `_persist_test_run()`.

---

### H-3. Orchestrator's `_run_map()` Missing org_id on CrawlRun
**Phase**: 1
**Files**: `agent/orchestrator.py` `_run_map()` method

The orchestrator persists `CrawlRun` directly to the database without `org_id`. After Phase 1, this will raise a NOT NULL constraint violation.

**Fix**: Add `org_id` parameter to `build_pipeline()` and thread it through to the orchestrator (or to the Crawler which creates CrawlRun). This is already partially planned in Phase 7 (`build_pipeline` gains `org_id`) — move this to Phase 1.

---

### H-4. Job Queue `claim_next` Returns Detached ORM Object
**Phase**: 6
**Files**: `worker/queue.py` (planned)

After `session.commit()` and leaving the `async with AsyncSession` block, the returned `PipelineJob` is detached. Accessing lazy-loaded attributes in `_execute()` would raise `DetachedInstanceError`.

**Fix**: Instead of returning the ORM object, return a plain dict or dataclass with the needed fields. Or use `session.expunge(job)` before closing the session to keep the object in a usable detached state.

---

### H-5. In-Memory Rate Limiter Unbounded Growth + Per-Worker Split
**Phase**: 4
**Files**: `web/middleware.py` (existing)

The `_hits` dict never evicts stale IPs — memory leak. With multiple workers, rate limits are per-worker (client gets N× the limit).

**Fix**: For Phase 4: add periodic cleanup of stale keys (e.g., every 60s, remove keys with all timestamps older than the window). Document that the in-memory rate limiter is per-worker. For future: consider Redis-based rate limiting when Redis is added for session storage.

---

### H-6. Single-Tenant Users Hit Free-Tier Limits
**Phase**: 1 + 3
**Files**: `web/usage.py`, settings

When `AUTH_MODE=single` with `USE_DATABASE=true`, Phase 3's `UsageEnforcer` enforces free-tier limits on the sentinel org (3 projects, 10 crawls/month). Self-hosted users expect no limits.

**Fix**: Two options:
1. **Recommended**: In `AUTH_MODE=single`, skip usage enforcement entirely (check `auth_mode` in `UsageEnforcer.check()`).
2. Alternative: Seed the sentinel org with `plan="pro"` (unlimited) in the Phase 3 migration.

---

### H-7. Empty `CLERK_WEBHOOK_SECRET` Bypasses Signature Verification
**Phase**: 2
**Files**: `web/auth/webhook.py` (planned), `config/settings.py`

If `CLERK_WEBHOOK_SECRET=""`, `base64.b64decode("" + "==")` returns empty bytes, making HMAC deterministic and predictable. The settings validation uses `if not getattr(...)` which catches empty string, but a whitespace-only string like `" "` would pass.

**Fix**: Strip whitespace before checking: `if not getattr(settings, field_name, "").strip()`. Add a minimum length check for webhook secrets.

---

### H-8. `reclaim_stale` Uses Fragile Timestamp Arithmetic
**Phase**: 6
**Files**: `worker/queue.py` (planned)

The double conversion `datetime -> timestamp -> datetime` is fragile and may have timezone issues.

**Fix**: Use `cutoff = datetime.now(UTC) - timedelta(seconds=stale_seconds)` directly.

---

## MEDIUM Issues

### M-1. No `auth_mode` Validation Against Invalid Values
**Phase**: 1
**Fix**: Use `Literal["single", "clerk"]` type annotation. Add runtime validation in `get_settings()`.

### M-2. No Subscription Auto-Creation on Organization Webhook
**Phase**: 2 + 3
**Fix**: In `_upsert_org()` handler, also create a `Subscription(plan="free", status="active")` if one doesn't exist.

### M-3. Audit Log `details_json` May Contain PII or Secrets
**Phase**: 5
**Fix**: Add a sanitizer that strips known sensitive fields (api_key, password, token) before recording. Add a size limit (e.g., 10KB max for details_json).

### M-4. No Graceful Shutdown for Job Worker
**Phase**: 6
**Fix**: Register SIGTERM/SIGINT signal handlers in `cli.py` that call `worker.stop()`. Set `worker._running = False` and let the current job finish before exiting. Set Docker `stop_grace_period: 120s` to allow long-running pipelines to complete.

### M-5. ArtifactStore API Incompatibility (sync→async, Path→str)
**Phase**: 7
**Fix**: Phase 7 must also refactor `crawler.py` (and any other callers of ArtifactStore) to use the async API and string keys instead of Path objects. Add these files to Phase 7's files summary.

### M-6. GDPR Purge Missing: Logs, Job Results, Audit Trail IPs
**Phase**: 5 + 6
**Fix**: Define audit log retention period (e.g., 1 year post-deletion). Add `PipelineJob.result_json` cleanup to the purge workflow. Document that structured logs in external systems (CloudWatch/Loki) need a separate retention policy.

### M-7. No Compound Indexes for GDPR Purge Queries
**Phase**: 1
**Fix**: Add compound indexes `(org_id, project_id)` on child tables to speed up cascading deletes. Consider `ON DELETE CASCADE` on foreign keys (but this requires careful ordering).

### M-8. `create_object_store()` Creates New S3 Client Per Call
**Phase**: 7
**Fix**: Cache the ObjectStore instance using `@lru_cache` or a module-level singleton. The store is stateless (except connection pool) so safe to share.

### M-9. Webhook-Stored Org Names Not Sanitized (XSS Risk)
**Phase**: 2
**Fix**: Jinja2's auto-escaping handles this, but verify all templates use auto-escaping. Never use `|safe` filter on user-provided data. Add a test that verifies org names with `<script>` tags are properly escaped.

### M-10. CSP Header `unsafe-inline` Too Permissive for SaaS
**Phase**: 4
**Fix**: Move to nonce-based CSP for scripts when feasible. Short term, document the risk. Add `frame-ancestors 'none'` (redundant with X-Frame-Options but belt-and-suspenders).

### M-11. Job Queue Concurrency Limit Can Be Exceeded by 1
**Phase**: 6
**Fix**: Acceptable for MVP — the race window is within a single SQL statement. Document as a known limitation. For strict enforcement, use advisory locks per org.

---

## LOW Issues

### L-1. Health Check Exposes Internal State
**Fix**: Return minimal info to unauthenticated callers. Add `/api/health/detailed` for admins.

### L-2. Duplicate Security Headers (Caddy + Middleware)
**Fix**: Make SecurityHeadersMiddleware conditional on `environment != "production"`.

### L-3. No Pagination Index on Jobs Table
**Fix**: Add composite index `(org_id, created_at DESC)` on `pipeline_jobs`.

### L-4. Session Cookie Missing `Secure` Flag
**Fix**: Set `secure=True` when `environment != "development"`.

### L-5. No `environment` Value Validation
**Fix**: Use `Literal["development", "staging", "production"]`.

### L-6. Migration `ON CONFLICT DO NOTHING` Could Leave Stale Data
**Fix**: Use `ON CONFLICT DO UPDATE SET plan = 'free'`.

### L-7. No Connection Timeout on S3 Client
**Fix**: Pass `config=AioConfig(connect_timeout=5, read_timeout=30)`.

### L-8. `TenantRateLimitMiddleware` Is a No-Op (Dead Code)
**Fix**: Either implement it or remove it. Don't register dead middleware.

### L-9. `allowed_origins` Parsing From Env Var May Fail
**Fix**: Add a Pydantic validator for comma-separated or JSON list parsing. Document the expected format.

### L-10. `_soft_delete_user` Does Not Deactivate Memberships
**Fix**: Also deactivate all `OrganizationMembership` rows for the deleted user.

### L-11. No Audit Log Retention Policy
**Fix**: Define retention (e.g., 2 years) and schedule automated archival to cold storage.

### L-12. `Organization.plan` Duplicated With `Subscription.plan`
**Fix**: Remove `plan` from `Organization` model. Use `Subscription.plan` as single source of truth.

---

## Configuration Checklist

### Missing Validations to Add

| Setting | Validation Needed | Phase |
|---|---|---|
| `auth_mode` | Must be `"single"` or `"clerk"` | 1 |
| `environment` | Must be `"development"`, `"staging"`, or `"production"` | 4 |
| `clerk_webhook_secret` | Min length, strip whitespace before check | 2 |
| `allowed_origins` | Pydantic validator for list parsing from env | 4 |
| `s3_bucket` | Required when `use_s3=true` (already planned) | 7 |
| `auth_mode=clerk` + `use_database=false` | Invalid combination — fail fast | 1 |

### Dangerous Default Combinations

| Combination | Risk | Mitigation |
|---|---|---|
| `AUTH_MODE=single` + `USE_DATABASE=true` + Phase 3 deployed | Free-tier limits on self-hosted | Skip usage checks in single-tenant mode |
| `AUTH_MODE=clerk` + `USE_DATABASE=false` | Clerk needs DB for user/org lookup | Fail at startup with clear error |
| `ENVIRONMENT=production` + `SECRET_KEY=change-me...` | Insecure sessions | Existing warning is good; consider failing startup in production |
| `USE_S3=true` + no bucket configured | S3 operations fail at runtime | Already validated (Phase 7) |
| `DEBUG=true` + `ENVIRONMENT=production` | SQL query logging in production | Add validation: fail if both true |

### Cross-Phase Dependency Matrix (Config)

```
Phase 1 introduces:
  AUTH_MODE, SINGLE_TENANT_ORG_ID
  → Phase 2 adds: CLERK_* (6 vars)
  → Phase 3 adds: (no new env vars, limits in code)
  → Phase 4 adds: ENVIRONMENT, ALLOWED_ORIGINS
  → Phase 7 adds: USE_S3, S3_* (5 vars)

Critical rule: AUTH_MODE=clerk REQUIRES USE_DATABASE=true
               USE_S3=true REQUIRES S3_BUCKET
               ENVIRONMENT=production REQUIRES SECRET_KEY ≠ default
```

---

## Implementation Priority

When implementing each phase, address the findings in this order:

1. **Before Phase 1**: Fix H-2 (persist_test_run org_id), H-3 (orchestrator org_id), C-1/C-2 (pipeline_results + results.py)
2. **During Phase 2**: Fix C-3 (JWKS error handling), C-4 (webhook idempotency), H-7 (empty secret), L-10 (user deletion memberships)
3. **During Phase 3**: Fix C-5 (usage race condition), H-6 (single-tenant limits), L-12 (duplicate plan field)
4. **During Phase 4**: Fix M-1 (auth_mode validation), L-1 (health check), L-4 (secure cookie)
5. **During Phase 6**: Fix H-4 (detached ORM), H-8 (timestamp), M-4 (graceful shutdown)
6. **During Phase 7**: Fix C-7 (path traversal), M-5 (API compatibility), M-8 (S3 client caching)
