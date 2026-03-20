---
name: prod-readiness
description: >
  Production readiness audit for Elixir/Phoenix/Ash applications. Performs static code analysis
  across 9 dimensions: database performance, query optimization, LiveView performance,
  dead code detection, Oban workers & background jobs, security, observability & monitoring,
  infrastructure & deployment, and resilience & error recovery. Generates a severity-prioritized
  report with file:line references and recommended diagnostic commands.
  Invoked as /prod-readiness with optional scope (directory, module path, or dimension name).
---

# Production Readiness Audit

You are a principal engineer performing a **production readiness audit** of an Elixir/Phoenix/Ash
application. Your goal is to identify performance bottlenecks, security gaps, dead code, and
reliability risks through **static code analysis only**.

Work like a site reliability engineer reviewing the codebase before a production deploy:
question every query, trace every data flow, probe every boundary.

## When to Use

- Pre-deployment readiness check to catch performance and security issues
- Periodic health check on database queries, LiveView memory, and security posture
- After adding new features, to verify they don't introduce N+1 queries, unbounded reads, or auth gaps
- Technical debt assessment focused on performance and reliability

**Not for:** Reviewing a specific PR diff (use `pr-llm-review`), or full feature-by-feature
analysis (use `feature-audit`).

## Process Overview

```
Phase 0: Scope & Preparation              -> Parse arguments, build file inventory
Phase 1: Database Performance              -> Indexes, connection pool, migration quality
Phase 2: Query Optimization                -> N+1, unbounded queries, missing select/limit
Phase 3: LiveView Performance              -> Socket memory, component rendering, assigns bloat
Phase 4: Dead Code Detection               -> Unused modules, functions, routes, config
Phase 5: Oban Workers & Background Jobs    -> Timeouts, uniqueness, error handling, scheduling
Phase 6: Security                          -> Auth gaps, CSRF, XSS, input validation, CSP
Phase 7: Observability & Monitoring        -> Logging, health checks, Telegram alerts, metrics
Phase 8: Infrastructure & Deployment       -> Dockerfile, releases, env vars, build config
Phase 9: Resilience & Error Recovery       -> Supervision trees, retries, graceful degradation
Phase 10: Report & Recommendations         -> Consolidated report with diagnostic commands
```

## Severity Framework

| Severity | Icon         | Criteria                                                     | Action                             |
| -------- | ------------ | ------------------------------------------------------------ | ---------------------------------- |
| Critical | `[CRITICAL]` | Data loss, security breach, or service outage risk           | Must fix before deploy             |
| High     | `[HIGH]`     | Degraded performance, intermittent errors, security weakness | Fix within current sprint          |
| Medium   | `[MEDIUM]`   | Issues under load, tech debt accumulation                    | Plan for next maintenance window   |
| Low      | `[LOW]`      | Code quality, optimization opportunity                       | Address when touching related code |

**Dimension tags:** `[DB]`, `[QUERY]`, `[LIVEVIEW]`, `[DEAD]`, `[OBAN]`, `[SECURITY]`, `[OBS]`, `[INFRA]`, `[RESILIENCE]`

**Positive findings** use the `[OK]` icon to highlight things done correctly.

---

## Phase 0: Scope & Preparation

### 0.1 Parse Scope

Parse `$ARGUMENTS` to determine audit scope:

- **No arguments**: Audit the full project
- **Directory** (e.g., `lib/management/instagram/`): Audit all files in that directory tree
- **Module path** (e.g., `lib/management/workers/profile_sync_worker.ex`): Deep audit of that module and its connections
- **Dimension name** (e.g., `security`): Run only that dimension across the full project

### 0.2 Build File Inventory

Use Glob to discover the files that will be audited:

```
# Ash domains and resources
Glob pattern="lib/management/**/*.ex"

# Workers (Oban)
Glob pattern="lib/management/workers/**/*.ex"

# Web layer — LiveView, controllers, components
Glob pattern="lib/management_web/live/**/*.ex"
Glob pattern="lib/management_web/components/**/*.ex"
Glob pattern="lib/management_web/plugs/**/*.ex"

# Router
Read file_path="lib/management_web/router.ex"

# Notifications
Glob pattern="lib/management/notifications/**/*.ex"

# External integrations
Glob pattern="lib/management/direct_api/**/*.ex"
Glob pattern="lib/management/llm/**/*.ex"
Glob pattern="lib/management/storage/**/*.ex"

# Configuration
Read file_path="config/config.exs"
Read file_path="config/runtime.exs"
Read file_path="config/prod.exs"
Read file_path="config/dev.exs"
Read file_path="mix.exs"

# Migrations
Glob pattern="priv/repo/migrations/**/*.exs"

# Infrastructure
Read file_path="Dockerfile"
Read file_path="docker-compose.yml"
Read file_path="rel/overlays/bin/entrypoint.sh"
```

Store this inventory for reference in all subsequent phases.

### 0.3 Read Core Config

Read these files to understand baseline configuration:

- `config/config.exs` — Oban crontab, Repo config, Ash domains
- `config/runtime.exs` — Environment variable loading, pool sizes, secrets
- `config/prod.exs` — Production-specific settings
- `lib/management/repo.ex` — Ecto Repo configuration
- `lib/management/application.ex` — Supervision tree, child processes

### 0.4 Understand Architecture

This project uses **Ash Framework 3.0** with domain-driven design:

- **Ash Domains** define context boundaries with declarative resources
- **Resources** declare attributes, relationships, actions, identities, and indexes
- **AshPostgres** provides the data layer with PostgreSQL
- **AshOban** integrates background jobs
- **AshAuthentication** handles magic link auth
- **LiveView** with Controller/View separation pattern

**Important**: Always check `require Ash.Query` is present when Ash.Query macros are used.

---

## Phase 1: Database Performance

**Goal**: Identify missing indexes, inefficient schema design, and misconfigured database settings.

### 1.1 Search Patterns

| Check                         | Grep Pattern                                              | Glob                                   | Purpose                      |
| ----------------------------- | --------------------------------------------------------- | -------------------------------------- | ---------------------------- |
| Existing indexes              | `index\b` or `unique_index`                               | `lib/management/**/*.ex`               | Inventory existing indexes   |
| Custom indexes in migrations  | `create index\|create unique_index`                       | `priv/repo/migrations/**/*.exs`        | Indexes in migrations        |
| Identity definitions          | `identity\b`                                              | `lib/management/**/*.ex`               | Unique constraints           |
| Connection pool config        | `pool_size`                                               | `config/**/*.exs`                      | Connection pool sizing       |
| Queue target/interval         | `queue_target\|queue_interval`                            | `config/**/*.exs`                      | DB queue tuning              |
| Raw SQL usage                 | `Repo\.query\|Ecto\.Adapters\.SQL\.query\|fragment\(`     | `lib/**/*.ex`                          | Manual SQL bypassing Ash     |
| Timeout configuration         | `timeout:`                                                | `config/**/*.exs`, `lib/**/*.ex`       | Query/transaction timeouts   |
| Repo.transaction calls        | `Repo\.transaction`                                       | `lib/**/*.ex`                          | Transaction timeout coverage |

### 1.2 Analysis Steps

1. **Read every Ash resource file** in scope. For each resource:
   - List all attributes used in WHERE clauses (cross-reference with queries/actions)
   - Check if foreign key columns have index definitions
   - Verify identities exist for lookup fields (identities create unique indexes)
   - Note: Ash `identity` creates an implicit PostgreSQL unique index
   - Note: Primary keys automatically have indexes
2. **Read `config/runtime.exs`** for `pool_size`, `queue_target`, `queue_interval`
3. **Read migration files** to verify indexes were actually created
4. **Cross-reference**: For every `filter` call in queries, verify the filtered column has an index
5. **Check `Repo.transaction` calls** — every one must have an explicit `timeout:` option

### 1.3 Severity Definitions

- **[CRITICAL]**: Raw SQL with string interpolation, missing index on auth token lookup (hottest path), `Repo.transaction` without timeout
- **[HIGH]**: Missing index on columns used in high-frequency WHERE clauses, pool_size < 10 for production
- **[MEDIUM]**: Missing indexes on foreign key columns, missing composite indexes for common multi-field filters
- **[LOW]**: Index on rarely-queried field, pool sizing for expected scale

### 1.4 Recommended Diagnostic Commands

```bash
# Check current indexes
mix run -e "Management.Repo.query!(\"SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"

# Check table sizes
mix run -e "Management.Repo.query!(\"SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"

# Check migration status
mix ecto.migrations

# Check pending Ash migrations
mix ash.codegen --dry-run check_indexes

# Inspect pool status
mix run -e "IO.inspect(Management.Repo.config())"
```

---

## Phase 2: Query Optimization

**Goal**: Detect N+1 queries, unbounded reads, missing column selection, and inefficient Ash query patterns.

### 2.1 Search Patterns

| Check                        | Grep Pattern                                               | Glob                                   | Purpose                                 |
| ---------------------------- | ---------------------------------------------------------- | -------------------------------------- | --------------------------------------- |
| Unbounded reads              | `Ash\.read!\|Ash\.read\b` without `page:` or `limit:`     | `lib/**/*.ex`                          | Queries returning all rows              |
| N+1 in loops                 | `Enum\.each.*Ash\.\|Enum\.map.*Ash\.`                      | `lib/**/*.ex`                          | Sequential Ash calls in loops           |
| Full table loads             | `Ash\.read!` or `Ash\.stream!` without filters             | `lib/**/*.ex`                          | Loading entire tables                   |
| Missing load/side_load       | `Ash\.load` inside loops                                   | `lib/**/*.ex`                          | N+1 relationship loading                |
| Count via Enum               | `Enum\.count\|length\(` on Ash query results               | `lib/**/*.ex`                          | Loading all to count                    |
| Offset pagination            | `page: \[offset:`                                          | `lib/**/*.ex`                          | O(n) for deep pages                     |
| Fragment usage               | `fragment\(`                                               | `lib/**/*.ex`                          | Raw SQL in Ash queries                  |
| Bulk operations              | `Ash\.bulk_create\|Ash\.bulk_update\|Ash\.bulk_destroy`    | `lib/**/*.ex`                          | Verify bulk ops used where appropriate  |
| Stream usage                 | `Ash\.stream!`                                             | `lib/**/*.ex`                          | Verify streaming for large datasets     |

### 2.2 Analysis Steps

1. **Read every query module and action**. For each:
   - Does it use `limit:` for list queries?
   - Does it load relationships eagerly or in loops?
   - Is the WHERE clause indexed? (cross-reference Phase 1)
2. **Read every worker and service function**. For each:
   - Does it call Ash actions in a loop? (N+1 pattern)
   - Does it use `Ash.bulk_create/update` for batch operations?
   - Does it use `Ash.stream!` for processing large datasets?
3. **Check pagination**: Verify keyset pagination is used (default in this project) instead of offset.
4. **Check for full table loads**: Search for `Ash.read!` without filters or with overly broad filters.
5. **Check aggregates**: Verify `Ash.count`/`Ash.sum`/`Ash.aggregate` is used instead of loading-then-counting.

### 2.3 Severity Definitions

- **[CRITICAL]**: N+1 queries in loops processing potentially large batches (>50 items)
- **[HIGH]**: Unbounded reads on growing tables (profiles, posts), full table loads into memory, `Enum.count` on Ash results
- **[MEDIUM]**: Offset pagination on deep pages, missing eager loading, `Ash.load` in loops
- **[LOW]**: Minor over-fetching, redundant count queries

### 2.4 Recommended Diagnostic Commands

```bash
# Enable Ecto query logging (in config/dev.exs)
# config :management, Management.Repo, log: :debug

# Check slow queries (requires pg_stat_statements)
mix run -e "Management.Repo.query!(\"SELECT query, calls, mean_exec_time, total_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"

# Count rows in main tables
mix run -e "Management.Repo.query!(\"SELECT 'profiles' as tbl, count(*) FROM instagram_profiles UNION ALL SELECT 'posts', count(*) FROM instagram_posts UNION ALL SELECT 'followings', count(*) FROM instagram_followings;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"
```

---

## Phase 3: LiveView Performance

**Goal**: Identify LiveView socket memory issues, component rendering problems, and assigns bloat.

### 3.1 Search Patterns

| Check                        | Grep Pattern                                                  | Glob                                     | Purpose                    |
| ---------------------------- | ------------------------------------------------------------- | ---------------------------------------- | -------------------------- |
| Large assigns                | `assign\(socket\|assign_new`                                  | `lib/management_web/live/**/*.ex`        | Socket memory bloat        |
| Timer leaks                  | `Process\.send_after\|:timer\.send_interval`                  | `lib/management_web/live/**/*.ex`        | Leaking timers on navigate |
| Async operations             | `Task\.async\|assign_async\|start_async`                      | `lib/management_web/live/**/*.ex`        | Async data loading         |
| PubSub subscriptions         | `Phoenix\.PubSub\.subscribe\|subscribe\(`                     | `lib/management_web/live/**/*.ex`        | PubSub cleanup             |
| Connected? guard             | `connected?\(socket\)`                                        | `lib/management_web/live/**/*.ex`        | Double-load prevention     |
| Temporary assigns            | `temporary_assigns:`                                          | `lib/management_web/live/**/*.ex`        | Memory optimization        |
| Stream usage                 | `stream\(\|stream_insert\|stream_delete`                      | `lib/management_web/live/**/*.ex`        | Efficient list rendering   |
| Large component renders      | `def render\|def handle_event`                                | `lib/management_web/live/**/*.ex`        | Component complexity       |
| Colocated hooks              | `ColocatedHook\|:type.*Phoenix\.LiveView\.ColocatedHook`      | `lib/management_web/live/**/*.ex`        | JS hook patterns           |
| Flash timer cleanup          | `clear_flash\|flash`                                          | `lib/management_web/live/**/*.ex`        | Flash timer leaks          |

### 3.2 Analysis Steps

1. **Audit every LiveView controller** (`mount/3`, `handle_params/3`, `handle_event/3`, `handle_info/2`):
   - Does `mount` guard data loading with `connected?(socket)`?
   - Are timers stored in assigns and cancelled on unmount/navigation?
   - Are large lists using `stream` instead of regular assigns?
   - Does it subscribe to PubSub? If so, is there cleanup?
2. **Check for assigns bloat**: Look for assigning large data structures to the socket. Large lists of maps/structs should use `temporary_assigns` or `stream`.
3. **Timer leak audit**: For every `Process.send_after` or `:timer.send_interval`:
   - Is the timer reference stored in assigns?
   - Is it cancelled before scheduling a new one?
   - Is it cancelled on `terminate/2` or navigation?
4. **Component rendering**: Check for expensive computations in `render/1` that should be moved to `handle_event` or computed in assigns.
5. **Verify async patterns**: Data loading in `mount/3` should use `assign_async` or `Task.async` + `handle_info` to avoid blocking the socket.

### 3.3 Severity Definitions

- **[CRITICAL]**: Data loading blocks mount (user sees blank page), timer leak causing unbounded memory growth
- **[HIGH]**: Loading data before `connected?(socket)` (double data fetch), large lists in regular assigns (no stream/temporary), timer leaks in high-traffic pages
- **[MEDIUM]**: Missing `connected?` guard on non-critical pages, PubSub subscriptions without cleanup, expensive render computations
- **[LOW]**: Minor assigns optimization, component decomposition suggestions

### 3.4 Recommended Diagnostic Commands

```bash
# Check LiveView process memory (in iex)
# :observer.start()

# Check socket state
# In browser DevTools: liveSocket.getSocket().conn.transport

# Check for timer leaks (attach to running node)
# :recon.proc_count(:message_queue_len, 10)

# Profile LiveView render time
# Add to config: config :phoenix_live_view, debug_heex_annotations: true
```

---

## Phase 4: Dead Code Detection

**Goal**: Find unused modules, functions, routes, workers, config keys, and orphaned artifacts.

### 4.1 Search Patterns

| Check                         | How to Detect                                                    | Scope                         | Purpose                      |
| ----------------------------- | ---------------------------------------------------------------- | ----------------------------- | ---------------------------- |
| Unused modules                | Find `defmodule`, check for callers across project               | `lib/**/*.ex`                 | Dead modules                 |
| Unused public functions       | Find `def ` (not `defp`), Grep for usage across project          | `lib/**/*.ex`                 | Dead public functions        |
| Unused Ash actions            | Find `action :` definitions, check for code_interface/route use  | `lib/management/**/*.ex`      | Dead resource actions        |
| Orphaned routes               | Find routes in router, verify LiveView modules exist             | `lib/management_web/router.ex`| Routes to missing pages      |
| Dead config keys              | Find config keys in runtime.exs, check for usage                 | `config/runtime.exs`          | Configured but unused        |
| Unused workers                | Find worker modules, check Oban crontab/manual insertion         | `lib/management/workers/*.ex` | Unscheduled workers          |
| Dead schema attributes        | Find attributes in resources, check for read/write               | `lib/management/**/*.ex`      | Unused columns               |
| Orphaned migrations           | Migrations for removed features                                  | `priv/repo/migrations/*.exs`  | Historical cleanup           |
| Unused dependencies           | Cross-reference mix.exs deps with actual usage                   | `mix.exs`                     | Bloated dependencies         |
| Dead aliases/imports          | `alias` or `import` without usage in module                      | `lib/**/*.ex`                 | Unused imports               |

### 4.2 Analysis Steps

1. **Module audit**: For each module in `lib/management/`:
   - Grep for the module name across the project
   - Flag modules with zero references (except application entry points)
2. **Worker audit**: For each worker in `lib/management/workers/`:
   - Check if it's in the Oban crontab (`config/config.exs`)
   - Check if it's manually inserted anywhere (`Oban.insert`)
   - Flag workers that are never scheduled or invoked
3. **Route audit**: Read the router. For each LiveView route:
   - Verify the LiveView module exists
   - Verify the module has the expected `mount/3` function
4. **Config audit**: Read `config/runtime.exs`. For each env var:
   - Grep for usage across `lib/`
   - Flag configured features with no implementation
5. **Note**: Run `mix credo --strict` first — Credo catches many unused aliases/imports.

### 4.3 Severity Definitions

- **[HIGH]**: Config keys read at runtime that are never set (will crash), workers referenced in crontab that don't exist
- **[MEDIUM]**: Unused modules with >50 lines, orphaned routes, unused workers, configured-but-unimplemented integrations
- **[LOW]**: Unused public functions, dead aliases/imports, unused schema attributes, small unused helpers

### 4.4 Recommended Diagnostic Commands

```bash
# Credo catches unused aliases, imports, module attributes
mix credo --strict

# Compile with warnings as errors
mix compile --warnings-as-errors

# Check for unused dependencies
mix deps.unlock --check-unused

# List all public functions and their callers
mix xref graph --format stats

# Find unreachable modules
mix xref unreachable
```

---

## Phase 5: Oban Workers & Background Jobs

**Goal**: Find missing timeouts, uniqueness gaps, error handling issues, and scheduling problems in Oban workers.

### 5.1 Search Patterns

| Check                    | Grep Pattern                                           | Glob                                   | Purpose                             |
| ------------------------ | ------------------------------------------------------ | -------------------------------------- | ----------------------------------- |
| Worker definitions       | `use Oban\.Worker\|use AshOban`                        | `lib/management/workers/**/*.ex`       | Inventory all workers               |
| Unique constraints       | `unique:\s*\[`                                         | `lib/management/workers/**/*.ex`       | Missing uniqueness guards           |
| Max attempts             | `max_attempts:`                                        | `lib/management/workers/**/*.ex`       | Infinite retry risk                 |
| Timeout on workers       | `timeout:`                                             | `lib/management/workers/**/*.ex`       | Missing execution timeouts          |
| Oban crontab             | `crontab:`                                             | `config/config.exs`                    | Scheduled worker inventory          |
| Manual job insertion     | `Oban\.insert\|Oban\.insert!`                          | `lib/**/*.ex`                          | Manually triggered workers          |
| Error handling           | `{:error\|:discard\|:snooze\|:cancel`                  | `lib/management/workers/**/*.ex`       | Error return patterns               |
| External calls in workers| `Req\.get\|Req\.post\|Telegram\|DirectApi`             | `lib/management/workers/**/*.ex`       | External dependencies               |
| Queue configuration      | `queues:`                                              | `config/config.exs`                    | Queue concurrency limits            |
| Telemetry/logging        | `Logger\.\|telemetry`                                  | `lib/management/workers/**/*.ex`       | Observability in workers            |

### 5.2 Analysis Steps

1. **Audit every Oban worker**. For each:
   - Does it have `unique: [period: N]` to prevent duplicate execution?
   - Does it have a reasonable `max_attempts` (not unlimited)?
   - Does it handle errors with proper return values (`:ok`, `{:error, reason}`, `{:discard, reason}`, `{:snooze, seconds}`)?
   - Does it set a `timeout` to prevent indefinite execution?
   - Does it log entry/exit and errors with context?
2. **Cross-reference crontab**: Every entry in the Oban crontab must:
   - Point to an existing worker module
   - Have a reasonable schedule (not too frequent for expensive operations)
   - Not overlap with other workers doing the same work
3. **Check external calls**: Workers calling external services (Direct API, Telegram, R2):
   - Do they have timeouts on HTTP requests?
   - Do they handle service unavailability?
   - Are they idempotent (safe to retry)?
4. **Check queue configuration**: Verify queue concurrency limits are appropriate for the workload.
5. **Check for job storms**: Look for patterns where a single event triggers many job insertions without batching.

### 5.3 Severity Definitions

- **[CRITICAL]**: Worker with no error handling (crashes silently), external API call with no timeout in worker, missing `unique:` on expensive workers that run frequently
- **[HIGH]**: Missing `max_attempts` on workers calling external services, worker that blocks queue (no timeout), crontab entry pointing to nonexistent module
- **[MEDIUM]**: Missing uniqueness on less-critical workers, workers without structured logging, overly aggressive scheduling
- **[LOW]**: Minor error handling improvements, queue concurrency tuning, logging verbosity

### 5.4 Recommended Diagnostic Commands

```bash
# Check Oban job states
mix run -e "Management.Repo.query!(\"SELECT worker, state, count(*) FROM oban_jobs GROUP BY worker, state ORDER BY worker, state;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"

# Check stuck/retrying jobs
mix run -e "Management.Repo.query!(\"SELECT id, worker, state, attempt, errors FROM oban_jobs WHERE state IN ('retryable', 'executing') ORDER BY inserted_at DESC LIMIT 20;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"

# Check job execution times
mix run -e "Management.Repo.query!(\"SELECT worker, avg(extract(epoch from completed_at - attempted_at)) as avg_seconds FROM oban_jobs WHERE completed_at IS NOT NULL GROUP BY worker ORDER BY avg_seconds DESC;\") |> Map.get(:rows) |> Enum.each(&IO.inspect/1)"

# Verify crontab configuration
mix run -e "IO.inspect(Application.get_env(:management, Oban)[:plugins])"
```

---

## Phase 6: Security

**Goal**: Identify input validation gaps, injection vectors, authentication holes, and secrets management issues.

### 6.1 Search Patterns

| Check                               | Grep Pattern                                                   | Glob                               | Purpose                      |
| ----------------------------------- | -------------------------------------------------------------- | ---------------------------------- | ---------------------------- |
| SQL injection via fragment           | `fragment\(.*\#\{`                                             | `lib/**/*.ex`                      | String interpolation in SQL  |
| Raw SQL execution                    | `Repo\.query\|Ecto\.Adapters\.SQL`                             | `lib/**/*.ex`                      | Manual SQL bypassing Ash     |
| XSS via raw HTML                     | `raw\(\|Phoenix\.HTML\.raw\|{:safe`                            | `lib/**/*.ex`                      | Unescaped user content       |
| CSRF protection                      | `protect_from_forgery\|csrf`                                   | `lib/management_web/**/*.ex`       | CSRF coverage                |
| CSP configuration                    | `content-security-policy\|put_secure_browser_headers`          | `lib/management_web/**/*.ex`       | Content security policy      |
| Auth pipeline coverage               | `ash_authentication_live_session\|require_authenticated_user`  | `lib/management_web/router.ex`     | Auth middleware coverage     |
| Rate limiting                        | `rate_limit\|RateLimiter`                                      | `lib/management_web/**/*.ex`       | Rate limit coverage          |
| Hardcoded secrets                    | `"sk-\|"token_\|password.*=.*"`                                | `lib/**/*.ex`                      | Leaked credentials           |
| Sensitive data in logs               | `Logger\.\w+.*password\|Logger\.\w+.*secret\|Logger\.\w+.*token` | `lib/**/*.ex`                   | Secret leakage in logs       |
| Direct env reads                     | `System\.get_env\b`                                            | `lib/**/*.ex`                      | Bypassing config validation  |
| Input validation on actions          | `validate\|argument :.*allow_nil`                              | `lib/management/**/*.ex`           | Ash action input validation  |
| Cookie security                      | `put_resp_cookie\|cookie`                                      | `lib/management_web/**/*.ex`       | Cookie configuration         |

### 6.2 Analysis Steps

1. **SQL injection scan**: Search for `fragment()` calls. Verify every one uses parameterized `?` placeholders, not string interpolation with `#{}`.
2. **Auth coverage audit**: Read the router. For every route scope:
   - Is it inside an authenticated `live_session`?
   - Are API endpoints protected?
   - Are health/debug endpoints restricted?
3. **XSS scan**: Search for `raw()` or `{:safe, ...}` in templates. Verify user-provided content is never rendered raw.
4. **CSP audit**: Check `put_secure_browser_headers` in the pipeline. Verify:
   - No `'unsafe-eval'` in script-src
   - No `'unsafe-inline'` in script-src (or properly nonced)
   - Image sources cover R2 bucket domains
5. **Rate limiting**: Verify rate limiting exists on auth endpoints (login, magic link).
6. **Secrets audit**: Verify all secrets come from `Application.get_env` or `config/runtime.exs`, never hardcoded.
7. **Direct `System.get_env` reads**: Flag any `System.get_env` in `lib/` that bypasses the config system.

### 6.3 Severity Definitions

- **[CRITICAL]**: SQL injection via `fragment()` with interpolation, hardcoded secrets, unauthenticated state-mutating routes
- **[HIGH]**: Missing rate limiting on auth endpoints, XSS via `raw()` on user content, `'unsafe-eval'` in CSP
- **[MEDIUM]**: Missing CSP headers, direct `System.get_env` reads in lib, overly permissive CORS, sensitive data in logs
- **[LOW]**: Minor header hardening, verbose error messages in production, cookie attribute tuning

### 6.4 Recommended Diagnostic Commands

```bash
# Search for potential hardcoded secrets
grep -rn "sk-\|api_key\|secret_key\|password" lib/ --include="*.ex" | grep -v "config\.\|System\.get_env\|Application\.get_env\|@moduledoc\|#\|test"

# Check auth pipeline coverage
grep -n "live_session\|live\s*\"/" lib/management_web/router.ex

# Check CSP configuration
grep -rn "content-security-policy\|put_secure_browser_headers" lib/management_web/

# Verify rate limiting
grep -rn "RateLimiter\|rate_limit" lib/management_web/

# Check for raw HTML rendering
grep -rn "raw(\|{:safe" lib/management_web/ --include="*.ex" --include="*.heex"
```

---

## Phase 7: Observability & Monitoring

**Goal**: Verify logging coverage, health checks, alerting, and monitoring readiness.

### 7.1 Search Patterns

| Check                    | Grep Pattern                                               | Glob                                   | Purpose                   |
| ------------------------ | ---------------------------------------------------------- | -------------------------------------- | ------------------------- |
| Logger usage in workers  | `Logger\.\w+`                                              | `lib/management/workers/**/*.ex`       | Logging in workers        |
| Logger usage in services | `Logger\.\w+`                                              | `lib/management/**/*.ex`               | Logging in business logic |
| Health endpoint          | `/health`                                                  | `lib/management_web/router.ex`         | Health check routes       |
| Telegram notifications   | `Telegram\.\|send_alert\|send_message`                     | `lib/**/*.ex`                          | Alert coverage            |
| Telemetry events         | `telemetry\|:telemetry`                                    | `lib/**/*.ex`                          | Telemetry infrastructure  |
| Logger metadata          | `Logger\.metadata\|metadata:`                              | `lib/**/*.ex`                          | Structured log context    |
| Error tracking           | `Sentry\|sentry\|ErrorTracker`                             | `lib/**/*.ex`, `config/**/*.exs`       | Error tracking setup      |
| PubSub for monitoring    | `PubSub\.broadcast\|PubSub\.subscribe`                     | `lib/**/*.ex`                          | Real-time monitoring      |
| Metrics collection       | `ScrapingMetric\|DailyMetrics`                             | `lib/**/*.ex`                          | Metrics infrastructure    |

### 7.2 Analysis Steps

1. **Logging coverage**: For every worker and critical service:
   - Does it log on entry/exit with relevant context (IDs, counts)?
   - Does it log errors with full error details?
   - Are log levels appropriate (`:error` for failures, `:info` for operations, `:debug` for details)?
2. **Health checks**: Read health endpoint(s):
   - Do they check database connectivity?
   - Do they check external service availability (Direct API, R2)?
   - Are detailed checks protected from public access?
3. **Telegram alerting**: Verify critical failure paths send Telegram alerts:
   - Worker failures that affect user-facing features
   - External service outages
   - High error rates
4. **Metrics collection**: Verify `DailyMetricsWorker` and `ScrapingMetric` cover key operational metrics.
5. **Structured logging**: Check if Logger calls include metadata for filtering/searching.

### 7.3 Severity Definitions

- **[HIGH]**: No alerting on critical worker failures, health endpoint missing database check, no logging in critical paths
- **[MEDIUM]**: Missing structured logging metadata, health endpoint exposes internals without auth, incomplete metrics coverage
- **[LOW]**: Debug logs in production paths, missing telemetry events, uneven log levels

### 7.4 Recommended Diagnostic Commands

```bash
# Check health endpoint
curl -s http://localhost:4010/health | jq

# Check Telegram notification coverage
grep -rn "Telegram\.\|send_alert" lib/ --include="*.ex"

# Check logging coverage in workers
for worker in lib/management/workers/*.ex; do
  count=$(grep -c "Logger\." "$worker" 2>/dev/null || echo 0)
  echo "$count logs: $worker"
done

# Check telemetry events
grep -rn ":telemetry" lib/ --include="*.ex"
```

---

## Phase 8: Infrastructure & Deployment

**Goal**: Validate Dockerfile, release configuration, environment handling, and deployment readiness.

### 8.1 Search Patterns

| Check                     | What to Check                        | Files                                   | Purpose                           |
| ------------------------- | ------------------------------------ | --------------------------------------- | --------------------------------- |
| Docker multi-stage build  | Verify stages: deps, build, runner   | `Dockerfile`                            | Image size optimization           |
| Non-root user             | `USER` directive in runner stage     | `Dockerfile`                            | Security posture                  |
| Health check              | `HEALTHCHECK` directive              | `Dockerfile`                            | Container orchestration readiness |
| Entrypoint script         | Migration/seed logic                 | `rel/overlays/bin/entrypoint.sh`        | DB readiness handling             |
| Release config            | `mix release` settings               | `mix.exs`                               | Release configuration             |
| Environment variables     | All required env vars documented     | `config/runtime.exs`                    | Deployment documentation          |
| Elixir/OTP version        | Consistent across Dockerfile and mix | `Dockerfile`, `mix.exs`, `.tool-versions` | Version consistency             |
| Static assets             | Asset compilation in Dockerfile      | `Dockerfile`                            | Missing static files              |
| .dockerignore             | Sensitive files excluded             | `.dockerignore`                         | Secrets not in image              |
| Graceful shutdown         | Signal handling, drain config        | `config/runtime.exs`, `Dockerfile`      | Clean container stops             |

### 8.2 Analysis Steps

1. **Dockerfile audit**: Read the Dockerfile completely:
   - Are build stages properly separated (deps -> build -> run)?
   - Is the runner image minimal?
   - Is a non-root user configured?
   - Are OTP/Elixir versions pinned?
   - Is `MIX_ENV=prod` set?
   - Are assets compiled (`mix assets.deploy`)?
2. **Entrypoint audit**: Read `rel/overlays/bin/entrypoint.sh`:
   - Does it handle DB readiness (TCP check before migration)?
   - Does it run migrations before starting the app?
   - Does it have retry/backoff logic?
3. **Environment variable audit**: Compare `config/runtime.exs` env vars with:
   - `.env.example` or documentation — are all required vars documented?
   - Are secrets loaded from env vars (not hardcoded)?
   - Are there sensible defaults for non-secret vars?
4. **Release config**: Check `mix.exs` for proper release configuration (applications, cookie, etc.).
5. **.dockerignore audit**: Verify it excludes `_build`, `deps`, `.git`, test files, env files.

### 8.3 Severity Definitions

- **[CRITICAL]**: Secrets baked into Docker image, running as root in production, no DB migration in entrypoint
- **[HIGH]**: Missing `.dockerignore` (secrets in image layer), no health check for orchestration, missing env var documentation, no DB readiness check
- **[MEDIUM]**: Non-deterministic builds, missing graceful shutdown handling, dev deps in production image
- **[LOW]**: Image size optimization opportunities, missing build metadata labels

### 8.4 Recommended Diagnostic Commands

```bash
# Build and check image size
docker build -t management:audit . && docker images management:audit

# Check for secrets in image layers
docker history management:audit --no-trunc | grep -i "env\|arg\|secret\|key"

# Verify release configuration
mix release --overwrite && ls -la _build/prod/rel/management/

# Check .dockerignore coverage
cat .dockerignore

# Verify environment variables
grep "System.get_env" config/runtime.exs | grep -v "#"
```

---

## Phase 9: Resilience & Error Recovery

**Goal**: Verify supervision trees, retry strategies, graceful degradation, and failure recovery patterns.

### 9.1 Search Patterns

| Check                       | Grep Pattern                                           | Glob                              | Purpose                        |
| --------------------------- | ------------------------------------------------------ | --------------------------------- | ------------------------------ |
| Supervision tree            | `children\s*=\|Supervisor\.child_spec`                 | `lib/management/application.ex`   | Supervision structure          |
| GenServer processes         | `use GenServer\|GenServer\.start_link`                 | `lib/**/*.ex`                     | Long-running process catalog   |
| External service calls      | `Req\.get\|Req\.post\|Req\.request`                    | `lib/**/*.ex`                     | External dependency catalog    |
| Timeout on HTTP calls       | `receive_timeout:\|connect_options:`                   | `lib/**/*.ex`                     | Missing timeouts on Req calls  |
| Error handling on externals | `case.*:ok.*:error\|with.*<-`                          | `lib/**/*.ex`                     | Failure handling coverage      |
| Retry patterns              | `retry:\|max_retries\|backoff`                         | `lib/**/*.ex`                     | Retry infrastructure           |
| Circuit breaker patterns    | `circuit\|breaker\|Fuse`                               | `lib/**/*.ex`                     | Circuit breaker infrastructure |
| Process linking             | `Task\.async\|Task\.start\|spawn`                      | `lib/**/*.ex`                     | Unlinked process risks         |
| ETS tables                  | `:ets\.new\|:persistent_term`                          | `lib/**/*.ex`                     | In-memory state durability     |
| PubSub resilience           | `PubSub\.broadcast`                                    | `lib/**/*.ex`                     | Event propagation failures     |

### 9.2 Analysis Steps

1. **Catalog external dependencies**: List every external service the app calls:
   - Direct Scraper API (`direct_api/`)
   - Cloudflare R2 (`storage/`)
   - Telegram (`notifications/telegram.ex`)
   - Gemini LLM (`llm/providers/gemini.ex`)
   - PostgreSQL (via Repo)
2. **For each external dependency, check**:
   - **Timeout**: Is there an explicit `receive_timeout` on Req calls?
   - **Retry**: Is there retry logic for transient failures?
   - **Fallback**: What happens if the service is down? Does the app degrade or crash?
   - **Error propagation**: Do errors bubble up correctly with appropriate messages?
3. **Supervision tree audit**: Read `application.ex`:
   - Are all long-running processes supervised?
   - Is the restart strategy appropriate (`:one_for_one` vs `:rest_for_one`)?
   - Are GenServers using proper `init/1` patterns (not blocking)?
4. **ETS/persistent_term audit**: Check for in-memory state:
   - Is it recoverable if the process crashes?
   - Are there TTLs or cleanup mechanisms?
5. **Check for single points of failure**: Is there any path where a single external service failure takes down the entire app?

### 9.3 Severity Definitions

- **[CRITICAL]**: External service failure crashes the app (unhandled error), database connection failure with no recovery, unsupervised long-running process
- **[HIGH]**: Scraper API failure blocks all operations (no queue/fallback), Req call with no timeout, GenServer `init/1` that blocks on external service
- **[MEDIUM]**: Missing retry for transient failures, ETS state lost without recovery mechanism, no circuit breaker for frequently-failing externals
- **[LOW]**: Minor supervision tuning, cache TTL adjustments, logging on degradation paths

### 9.4 Recommended Diagnostic Commands

```bash
# Check supervision tree (in iex)
# :observer.start()

# Check process count and memory
mix run -e "IO.inspect(:erlang.system_info(:process_count)); IO.inspect(:erlang.memory())"

# Check ETS tables
mix run -e ":ets.all() |> Enum.map(fn t -> {t, :ets.info(t, :size)} end) |> Enum.sort_by(&elem(&1, 1), :desc) |> Enum.take(20) |> IO.inspect()"

# Test degradation by simulating service unavailability
# Stop external services and observe app behavior

# Check for process leaks
# :recon.proc_count(:memory, 10)
```

---

## Phase 10: Report & Recommendations

### 10.1 Report Structure

Compile all findings into this format:

```markdown
# Production Readiness Audit Report

**Project**: management
**Date**: [date]
**Scope**: [full project / specific scope]
**Dimensions Audited**: 9

---

## Summary

| Severity      | Count |
| ------------- | ----- |
| Critical      | X     |
| High          | X     |
| Medium        | X     |
| Low           | X     |
| OK (positive) | X     |

[2-3 sentence overall assessment: biggest risks, strongest areas, key recommendations]

---

## Critical Findings

For each:

- `[CRITICAL] [DIMENSION]` **Title** — `file:line`
  - **Issue**: What's wrong
  - **Impact**: What could happen in production
  - **Fix**: Concrete code change or action

## High Priority Findings

[Same format]

## Medium Priority Findings

[Same format]

## Low Priority Findings

[Same format]

---

## Positive Findings

[Things the codebase does well — at least 3 items]

- `[OK] [DIMENSION]` **What's good** — `file:line` evidence

---

## Recommended Diagnostic Commands

### Database Performance

[Commands from Phase 1.4]

### Query Analysis

[Commands from Phase 2.4]

### LiveView Profiling

[Commands from Phase 3.4]

### Dead Code Detection

[Commands from Phase 4.4]

### Oban Workers & Jobs

[Commands from Phase 5.4]

### Security Scanning

[Commands from Phase 6.4]

### Observability

[Commands from Phase 7.4]

### Infrastructure

[Commands from Phase 8.4]

### Resilience

[Commands from Phase 9.4]

---

## Per-Dimension Details

### 1. Database Performance

[Detailed findings for this dimension]

### 2. Query Optimization

[Detailed findings for this dimension]

### 3. LiveView Performance

[Detailed findings for this dimension]

### 4. Dead Code

[Detailed findings for this dimension]

### 5. Oban Workers & Background Jobs

[Detailed findings for this dimension]

### 6. Security

[Detailed findings for this dimension]

### 7. Observability & Monitoring

[Detailed findings for this dimension]

### 8. Infrastructure & Deployment

[Detailed findings for this dimension]

### 9. Resilience & Error Recovery

[Detailed findings for this dimension]

---

## Prioritized Action Items

### Immediate (before deploy)

[Critical findings]

### Short-term (this sprint)

[High findings]

### Medium-term (next 2-4 weeks)

[Medium findings]

### Backlog

[Low findings]
```

---

## Execution Guidelines

### Tool Usage

- **Read files actively** — never speculate about what code does; read it
- **Use Grep extensively** — run searches in parallel where possible
- **Use Glob** to discover files by pattern before reading them
- **Use Agent tool** (subagent_type=Explore) for deep exploration when auditing large domains
- **Do NOT execute** any diagnostic commands — only list them as recommendations

### Quality Standards

- Every finding must include **file:line evidence** — no vague claims
- Every finding must explain **what could go wrong in production**
- Every finding must include a **concrete fix** (code snippet or specific action)
- Distinguish between **facts** (verified by reading code) and **hypotheses** (need runtime testing)
- Include at least **3 positive findings** to calibrate severity and avoid alert fatigue

### Parallel Execution Strategy

Run these searches in parallel at the start of each phase:

- Phase 1: Grep for indexes, `Repo.transaction`, `pool_size`, `fragment(` simultaneously
- Phase 2: Grep for `Ash.read`, `Enum.each.*Ash`, `Ash.stream!`, `Ash.bulk_` simultaneously
- Phase 3: Grep for `assign(socket`, `Process.send_after`, `connected?`, `stream(` simultaneously
- Phase 4: Grep for `defmodule`, router routes, Oban crontab, cross-reference imports
- Phase 5: Grep for `use Oban.Worker`, `unique:`, `max_attempts`, `Oban.insert` simultaneously
- Phase 6: Grep for `fragment(`, `raw(`, `System.get_env`, rate limiting simultaneously
- Phase 7: Grep for `Logger.`, `Telegram.`, `/health`, telemetry simultaneously
- Phase 8: Read Dockerfile, .dockerignore, config/runtime.exs, entrypoint.sh in parallel
- Phase 9: Grep for `Req.`, `GenServer`, supervision, `:ets.new` simultaneously

### Common Mistakes to Avoid

| Mistake                                                        | Fix                                                                                                 |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Flagging Ash `identity` columns as missing indexes             | Ash `identity` creates an implicit PostgreSQL unique index                                           |
| Flagging primary keys as missing indexes                       | Primary keys automatically have indexes                                                              |
| Reporting Ash framework patterns as application issues         | Don't flag Ash-internal code; focus on application usage                                             |
| Flagging test files for missing auth                           | Test utilities don't need auth middleware                                                            |
| Confusing `Ash.Query.filter` with raw SQL                      | Ash queries are parameterized by default; only `fragment` with interpolation is risky                |
| Flagging dev-only code                                         | Skip code gated behind `Mix.env() == :dev` or config/dev.exs                                        |
| Reporting style nits as Critical                               | Reserve Critical for real production risk                                                            |
| Skipping positive findings                                     | Always acknowledge good patterns — builds trust and calibrates severity                              |
| Flagging `System.get_env` in `config/runtime.exs`             | `runtime.exs` is the designated place for env var reads; flag OTHER files reading `System.get_env`   |
| Not checking Ash resource `code_interface` for action coverage | Actions may be exposed through code_interface — verify before flagging as dead                        |
| Assuming Oban workers are dead because not in crontab          | Workers can be triggered via `Oban.insert` from other modules                                        |
| Flagging `Repo.transaction` in migration files                 | Migrations are run once; focus on runtime transaction calls                                          |

## Constraints

- Do NOT rush — thoroughness over speed
- Do NOT execute diagnostic commands — only recommend them
- Do NOT report issues without file:line evidence
- Do NOT flag framework-internal patterns as application issues
- Do NOT assume — verify with tools
- DO acknowledge well-implemented patterns
- DO consider the project's stage and context when assessing severity
- DO present findings in order of severity, not order of discovery


---

## Post-Completion: Follow-Up Suggestions

After completing the production readiness audit above, suggest the following follow-up prompts from
the `high-value-prompts` skill to the user. Present them as options and let the user choose:

1. **Security Surface Scan** — Deep scan for auth bypass, injection, sensitive data exposure, rate
   limiting gaps, CORS/CSP issues, and dependency vulnerabilities.
2. **Data Integrity & State Machine Audit** — Map every entity with a status field, verify transitions
   are enforced, find impossible states, race conditions, and missing cleanup on terminal states.
3. **Dependency & Configuration Health Check** — Find unused deps, known vulnerabilities, outdated
   pinned versions, undocumented env vars, hardcoded values, and cross-environment config surprises.

Say something like: "The production readiness audit is complete. Want me to dig deeper into any of
these areas?"

