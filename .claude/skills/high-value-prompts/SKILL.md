---
name: high-value-prompts
description: >
  A curated library of 27 battle-tested, generic prompts for deep codebase analysis, auditing,
  debugging, refactoring, and quality assurance. Use this skill whenever the user asks to
  "audit", "review", "analyze", "stress-test", "assess", or "explain" their codebase — or when
  they want a structured approach to debugging, refactoring, security scanning, production
  readiness, test coverage gaps, or onboarding to a new project. Also trigger when the user says
  things like "find issues", "check for problems", "what's wrong with this code", "help me
  understand this codebase", "check consistency", or "run a health check". Each prompt is
  generic (not tied to any stack) and produces deep, actionable output with file:line evidence.
---

# High-Value Generic Prompts

This skill provides a library of reusable, high-value prompts organized by category. Each prompt
is stack-agnostic and designed to produce deep, actionable analysis on any codebase.

## How to Use

When the user's request maps to one of the categories below, use the corresponding prompt as your
operating instructions. You can combine multiple prompts for deeper analysis (e.g., run the
Deep Feature Audit first, then Cross-Cutting Consistency on the findings).

**Pro tips to share with the user:**
- Chain with fix commands: after any audit, follow up with "Fix all critical and high items, one at a time, running tests after each"
- Scope down when needed: prepend "For the [module/feature] only:" to any prompt
- Request parallel execution: append "You can run sub-agents in parallel" for faster results

---

## Category 1: Audits & Reviews

### 1.1 Production Readiness Audit

You are a principal engineer performing a production readiness audit. Your goal is to identify
performance bottlenecks, security gaps, dead code, and reliability risks through static code
analysis only. Work like a site reliability engineer reviewing the codebase before a production
deploy: question every query, trace every data flow, probe every boundary. Cover database
performance (indexes, connection pool, migration quality), query optimization, dead code
detection, background jobs, security, observability and monitoring, infrastructure and
deployment, and resilience and error recovery. Generate a severity-prioritized report with
file:line references and recommended diagnostic commands.

### 1.2 Production Readiness Audit (Extended)

Audit this project for production readiness across these dimensions: database performance
(missing indexes, N+1 queries, unbounded growth), query optimization (slow queries, missing
pagination), frontend performance (bundle size, render blocking, memory leaks), dead code and
unused dependencies, API design (error handling, rate limiting, validation), security (injection,
auth bypass, secret exposure), observability (logging gaps, missing metrics, alerting holes),
infrastructure (health checks, graceful shutdown, connection pooling), and resilience (circuit
breakers, retry logic, timeout handling). For each gap, rate severity and estimate fix effort.

### 1.3 Deep Feature-by-Feature Audit

Perform an exhaustive feature-by-feature audit of the codebase. Your goal is NOT summarization —
your goal is deep understanding, decision re-evaluation, gap detection, and breakpoint discovery.
Work like a new tech lead taking ownership of the project: question every decision, trace every
data flow, probe every boundary, and document every gap. Enumerate every feature from multiple
signals (routes, UI, DB schema, background jobs, events, config, tests, docs, git history). For
each feature, trace the complete execution path, re-evaluate architectural decisions, map
connections to other features/UI/DB/external services, assess file size and coupling, and
inventory covered vs missing edge cases. Then do cross-cutting analysis: dependency graph,
consistency audit, security surface, observability. Stress-test inputs adversarially (boundary
values, state-based, sequence-based). Produce a prioritized report with critical findings,
missing features, incomplete features, breakpoints, and an edge case coverage matrix.

### 1.4 Codebase Review & Structured Refactor (16 Dimensions)

Perform a structured codebase review and refactoring across these dimensions: architecture
(structure, separation of concerns, pattern consistency, architectural standards), code quality
(naming conventions, KISS and complexity, code duplication, dead and unused code), reliability
(memory safety, SQL and query optimization, database batching, deprecated API usage), API and
compatibility (breaking changes, backward compatibility), and operations (logging, documentation).
For each issue found, record the file and line, what's wrong specifically, why it matters, a
suggested fix, the effort level, and a severity (Critical/Major/Minor/Info). Generate a
structured report sorted by severity, then execute user-approved changes incrementally.

### 1.5 Comprehensive Code Review with Auto-Fix

Act as a senior staff engineer performing a deep code review with authority to fix issues
autonomously. Review all changes across these dimensions — Critical: security (injection, secrets,
unauthenticated routes, missing validation), correctness (logic errors, race conditions, wrong
types, broken contracts), error handling (unhandled exceptions, swallowed errors). High:
performance (N+1 queries, unbounded fetching, memory leaks), test coverage (changed paths without
tests), type safety (missing types, unsafe casts). Medium: architecture (boundary violations,
business logic in controllers), backwards compatibility. Low: dead code, naming, edge cases,
documentation. Output a structured findings report, then auto-fix all critical and high issues.
Run the full quality pipeline (lint, type check, tests). Commit each logical group of fixes
separately.

### 1.6 Post-Refactor Breakage Audit

Perform a deep post-refactor audit to detect regressions, hidden breaking changes, and semantic
drift across the codebase. Your goal is NOT summarization — your goal is breakage detection and
risk analysis. First, detect the tech stack and map project source boundaries. Gather the
changeset and identify deleted, new, and modified files. Build a mental model of the refactor
pattern. Trace all callers of every changed or deleted public function. Do a project-wide impact
scan: search for all occurrences of old names, changed fields, modified constants, deleted
modules. Detect stale references, cross-module inconsistencies, and orphaned artifacts (unused
test helpers, stale mocks, dead routes). Then deep audit: contract integrity, call graph impact,
logic regression, external boundary risks, side effects, dead code, backwards compatibility, edge
case coverage. Report findings by severity with confidence levels and suggested fixes.

### 1.7 Regression & Refactor Audit (Extended)

Can you regression test the entire codebase to see if recent changes did not break any feature?
Trace every public function, every route, every background job — verify they still work as
intended. Check for stale references, dead code, orphaned artifacts, and hidden breaking changes
across the project. Report findings with file:line evidence.

---

## Category 2: Security & Consistency

### 2.1 Security Surface Scan

Scan the entire codebase for security vulnerabilities. Check: authentication bypass paths (routes
without auth middleware, resources without policy checks), authorization gaps (can users access
data they shouldn't?), input validation holes (SQL injection, XSS, path traversal, command
injection), sensitive data exposure (secrets in logs, PII without encryption, tokens in URLs),
rate limiting gaps (expensive operations without throttling), CORS and CSP configuration, and
dependency vulnerabilities. For each finding, provide a proof-of-concept scenario showing how it
could be exploited and a concrete fix.

### 2.2 Cross-Cutting Consistency Audit

Check for inconsistencies across the entire codebase: error handling patterns (does every feature
handle errors the same way?), validation approaches (middleware vs inline vs schema — is it
consistent?), logging patterns (are log levels used consistently? is context always included?),
response formats (do all endpoints return data in the same shape?), naming conventions (are
modules/functions/variables named consistently?), test patterns (do all features have similar test
coverage and structure?), config access (is config read consistently?). Map the feature dependency
graph. Identify circular dependencies, single points of failure, cascading failure risks, and
implicit coupling through shared database tables or global state.

### 2.3 Cross-Feature Inconsistency Detection (Extended)

Try to find inconsistencies on features and between them when they interact with each other. Look
for: constants defined differently across modules, status/state enums that disagree, race
conditions between concurrent workers, error handling patterns that vary, UI states that don't
refresh when backend data changes, and any place where two modules make different assumptions
about the same data. Map the interaction points and flag where they contradict each other.

### 2.4 Data Integrity & State Machine Audit

Audit every entity that has a status or state field. For each: map all valid state transitions,
verify they're enforced (not just documented), check for impossible states that the code allows,
find places where status is set without going through the state machine, identify race conditions
where concurrent operations can put entities in inconsistent states, and verify that dependent
data is cleaned up on terminal state transitions. Produce a state diagram for each entity and
flag every violation.

---

## Category 3: Performance & Architecture

### 3.1 File Size, Complexity & Coupling Assessment

For each feature's key files, assess structural health. Measure file lines against thresholds: OK
(under 300), Notable (301-500), Concerning (501-800), Critical (over 800). Count public
functions, identify the longest function, and measure branching depth (flag over 3 levels
nested), parameter count (flag over 4), cyclomatic paths (flag over 10). Measure coupling:
fan-out (how many modules this depends on, flag over 8), fan-in (how many depend on this), data
coupling, temporal coupling, shared mutable state. Produce a file size heatmap, coupling
hotspots, and actionable decomposition plans for every Critical or Concerning file with suggested
splits, effort estimate, and risk.

### 3.2 Architecture & Coupling Analysis

Map the dependency graph of this project. For every module, measure fan-out (how many modules it
depends on) and fan-in (how many modules depend on it). Identify: circular dependencies, god
modules (high fan-in + high fan-out + large file size), tightly coupled clusters, single points
of failure, and implicit coupling through shared database tables or global state. For each
"concerning" or "critical" file, suggest a concrete decomposition plan with effort estimate and
risk assessment. Include a file size heatmap sorted by line count.

### 3.3 Input Stress Testing (Adversarial)

Adopt an adversarial mindset. For each feature's entry point, design inputs that could break it.
Boundary value analysis: wrong types, empty strings, 1 million character strings, empty arrays,
10k items, negative numbers, NaN, Infinity, invalid formats, double-encoded URLs, null bytes, RTL
characters. State-based stress testing: empty database, full database, corrupt data, external
service down or returning 500, skipped workflow steps, simultaneous duplicate requests, expired
session mid-operation. Sequence-based: unexpected call order, interrupted long-running operations,
rapid re-submission. Document each breakpoint with: feature affected, exact trigger, behavior
(crash/wrong result/hang/data corruption), severity, root cause, and suggested fix.

---

## Category 4: Testing & Quality

### 4.1 Test Coverage Gap Analysis

Audit every module that contains business logic — workers, services, domain interfaces, state
machines, and critical paths. For each, determine whether it has test coverage for: happy path,
error paths, edge cases, and integration with dependencies. List modules with ZERO tests first
(critical risk), then modules with partial coverage. For each gap, write out the specific test
cases that are missing as a checklist. Prioritize by blast radius — what causes the most damage
if it breaks silently?

### 4.2 Full Quality Gate Pipeline

Run the complete quality pipeline for this project. Execute in order: 1) Code formatting check,
2) Linting with strict mode, 3) Type checking / compile with warnings as errors, 4) Full test
suite. Present results as a summary table (pass/fail per step with counts). If issues are found,
auto-fix formatting and lint issues, then diagnose root causes for type errors and test failures
before attempting fixes. Do not commit until everything passes green.

### 4.3 Pre-Commit Deep Validation

Before I commit these changes, validate them thoroughly. Check: 1) Do all modified files compile
without warnings? 2) Do all existing tests still pass? 3) Are there new code paths that need
test coverage? 4) Do the changes introduce any inconsistency with existing patterns in the
codebase? 5) Are there stale references to renamed/moved code? 6) Do the changes respect domain
boundaries? 7) Is error handling complete for all new failure modes? 8) Are there any security
implications? Run quality checks and tests, then report findings before I commit.

---

## Category 5: Debugging & Fixing

### 5.1 Autonomous Bug Fix (Red-Green Loop)

Given a bug report or failing tests, enter an autonomous red-green-refactor loop. Phase 1:
Reproduce — write a failing test that reproduces the exact bug. Phase 2: Red-Green Loop (max 5
iterations) — for each iteration: form a root cause hypothesis, implement the minimal fix in
source code, run the failing test, log the hypothesis and result, iterate if still failing. Do
NOT ask for user input until either all tests pass green or 5 approaches have been tried.
Phase 3: Quality Gate — run format check, linter, compiler warnings. Phase 4: Commit — stage
only related files, write a conventional commit explaining root cause and fix.

### 5.2 Diagnostic Debugging (Data-Driven)

Follow a data-driven debugging approach for this issue. Do NOT attempt fixes before understanding
root cause. Steps: 1) Reproduce the exact error, 2) Read and trace the full code path from entry
point to error, 3) Add diagnostic logging at key decision points to confirm which branches
execute and what values variables hold, 4) Run again and analyze output, 5) Form a hypothesis
based on evidence — explain the root cause clearly before proposing any fix, 6) Apply the minimal
fix, 7) Run full test suite to verify. If the first fix doesn't work, add MORE logging — don't
try a different approach blindly.

---

## Category 6: Understanding & Onboarding

### 6.1 Code Explanation (16-Point Framework)

Follow a systematic approach to explain this code: (1) Code context analysis — language,
framework, broader purpose, file role. (2) High-level overview — summary, main purpose, problem
being solved, fit in larger system. (3) Code structure breakdown — logical sections,
classes/functions, architecture and design patterns, data and control flow. (4) Line-by-line
analysis of complex or non-obvious lines. (5) Algorithm and logic explanation. (6) Data
structures and types. (7) Framework and library usage. (8) Error handling and edge cases.
(9) Performance considerations. (10) Security implications. (11) Testing and debugging.
(12) Dependencies and integrations. (13) Common patterns and idioms. (14) Potential improvements.
(15) Related code and context. (16) Debugging and troubleshooting. Use clear, non-technical
language when possible. Structure explanations from high-level to detailed.

### 6.2 Codebase Onboarding Map

I'm new to this codebase. Give me the complete mental model I need to be productive. Map out: the
architecture layers and how they connect, the domain model and key entities, the main user flows
end-to-end, every background process and when it runs, all external integrations and their
failure modes, the key conventions and patterns used throughout, and the areas of highest
complexity or technical debt. Organize this as a guided tour — start with the big picture, then
zoom into each area. Reference specific files so I can follow along.

### 6.3 Deep Analysis & Problem Solving (Ultra Think)

Activate deep analysis mode. Parse the problem from multiple angles: Technical (feasibility,
scalability, performance, maintainability, security, technical debt), Business (value, ROI,
time-to-market, competitive advantage, risk vs reward), User (needs, pain points, usability,
accessibility, edge cases, user journeys), System (system-wide impacts, integration points,
dependencies, emergent behaviors). Generate at least 3-5 different approaches with pros/cons,
implementation complexity, resource requirements, risks, and long-term implications. Deep dive on
the most promising solutions with detailed implementation plans, pitfall mitigation, phased
approaches, second and third-order effects, and failure modes. Draw cross-domain parallels. Play
devil's advocate — challenge each solution, identify blind spots, stress-test assumptions.
Synthesize into structured recommendations with confidence levels and areas of uncertainty.

---

## Category 7: Refactoring

### 7.1 Intelligent Refactoring (17-Step Methodology)

Follow a systematic approach to refactor this code: (1) Pre-refactoring analysis — identify what
needs refactoring and why, understand current functionality, review existing tests, identify all
dependencies. (2) Test coverage verification — ensure tests exist BEFORE refactoring, establish a
baseline. (3) Refactoring strategy — define clear goals, choose techniques (extract method,
extract class, rename, move, replace conditional with polymorphism, eliminate dead code), plan
incremental steps. (4) Environment setup — branch, verify tests pass. (5) Incremental
refactoring — small focused changes, run tests after each change, commit frequently. (6) Code
quality improvements — naming, DRY, simplify conditionals, reduce complexity, separation of
concerns. (7) Performance optimizations. (8) Design pattern application. (9) Error handling
improvement. (10) Documentation updates. (11) Testing enhancements. (12) Static analysis.
(13) Performance verification with before/after metrics. (14) Integration testing. (15) Code
review preparation. (16) Documentation of changes. (17) Deployment considerations with rollback
procedures.

---

## Category 8: Operations & Infrastructure

### 8.1 Worker/Job Pipeline Integrity Check

Audit every background job and worker in the system. For each worker, verify: is it idempotent
(safe to retry)? Does it have proper error handling (no silent swallowing)? Are database
operations atomic (no partial writes between steps)? Does it respect health gates and maintenance
flags? Does it have proper deduplication (unique constraints)? Are there race conditions with
other workers operating on the same data? Does it alert on failure without spamming (throttled
notifications)? Map the worker dependency graph and identify cascading failure risks.

### 8.2 Error Handling & Observability Audit

Trace every error path in this codebase. For each module, check: are errors logged before being
sent as alerts? Are specific exception types caught (not bare rescue/catch)? Are error messages
human-readable at system boundaries and machine-readable internally? Is there enough context in
log messages to debug without reproducing? Are there silent failures where errors are swallowed
without logging? Map every place where an operation can fail and verify there's a corresponding
log entry, metric, or alert. Flag any "fire and forget" patterns where failure is invisible.

### 8.3 Dependency & Configuration Health Check

Audit all dependencies and configuration in this project. Check: are there unused dependencies
that can be removed? Are there dependencies with known vulnerabilities? Are there pinned versions
that are significantly behind latest stable? Is every environment variable documented and
validated at startup (not failing silently at runtime)? Are there hardcoded values that should be
configurable? Are there config values that differ between environments in ways that could cause
production surprises? List each finding with the specific risk and remediation step.

### 8.4 UI/UX Consistency Audit

Review every page and component in the application for UI/UX consistency. Check: are similar
actions styled the same way across all pages? Do all forms handle loading, error, empty, and
success states? Are flash messages handled consistently (same types, same styling)? Do all data
tables use the same pagination pattern? Are keyboard shortcuts documented and consistent? Do
real-time updates work (PubSub subscriptions) or do pages show stale data? Are confirmation
dialogs used consistently for destructive actions? List every inconsistency with screenshots or
file:line references.
