---
name: pr-llm-review
description: >
  Deep codebase review and structured refactoring across 16 dimensions: architecture,
  separation of concerns, naming conventions, dead code, pattern consistency, KISS
  compliance, code duplication, memory safety, SQL optimization, database batching,
  deprecated APIs, breaking changes, logging, and documentation. Produces a severity-
  prioritized report with file:line references, then executes user-approved changes.

  Use this skill whenever the user wants to: review code quality, refactor a codebase
  or module, clean up code, detect code smells, reduce technical debt, improve
  maintainability, find dead code, check architectural standards, or perform any kind
  of structural code improvement. Also use when the user says things like "review this",
  "clean this up", "refactor", "code quality check", "find issues", "reduce complexity",
  or mentions any specific review dimension (naming, duplication, separation of concerns,
  etc.). Works with any language and framework — adapts analysis to the detected stack.
---

# Codebase Review & Refactor

You are performing a structured codebase review and refactoring. This is a two-phase
process: first you analyze and report, then you execute approved changes. Never skip the
report phase — the user needs to see findings and approve changes before you touch code.

## Phase 1: Scope Definition

Before analyzing anything, establish the review scope with the user:

1. **What to review** — Ask: "What would you like me to review?" Offer options:
   - Entire codebase
   - Specific directory or module (e.g., `lib/auth/`, `src/components/`)
   - Specific files
   - Changes on current branch (git diff)

2. **Focus areas** — Ask if they want all dimensions or specific ones. List categories:
   - Architecture (structure, separation of concerns, patterns)
   - Code Quality (naming, KISS, duplication, dead code)
   - Reliability (memory safety, SQL, batching, deprecated APIs)
   - API & Compatibility (breaking changes, backward compat)
   - Operations (logging, documentation)

3. **Constraints** — Ask about:
   - Is this a solo project or team codebase?
   - Any areas off-limits or intentionally structured a certain way?
   - Build/test commands to validate changes afterward?

Once scope is clear, proceed to analysis.

## Phase 2: Discovery

Explore the scoped codebase to understand context before judging it:

1. **Detect the tech stack** — Languages, frameworks, build tools, test frameworks,
   linters, formatters. This determines which language-specific patterns to check.

2. **Map the structure** — Top-level directories, module boundaries, entry points,
   configuration files. Understand the existing organizational pattern before
   suggesting changes to it.

3. **Identify conventions** — Look at 3-5 well-written files to establish the
   project's existing conventions: naming style, error handling pattern, import
   organization, comment style. The goal is to enforce consistency with what the
   project already does, not impose external standards.

4. **Check for project docs** — README, CLAUDE.md, CONTRIBUTING.md, architecture
   docs. These reveal intentional design decisions that shouldn't be "fixed."

## Phase 3: Analysis

Analyze the scoped code across each selected dimension. For each issue found, record:
- **File and line** (e.g., `src/auth/login.ts:42`)
- **What's wrong** (specific, not vague)
- **Why it matters** (impact on maintainability, reliability, or correctness)
- **Suggested fix** (concrete recommendation)
- **Effort** (Low / Medium / High)
- **Severity** (Critical / Major / Minor / Info)

### Severity Guide

- **Critical**: Bugs, security issues, data loss risks, OOM potential, broken APIs
- **Major**: Significant maintainability problems, architectural violations, major
  duplication, missing error handling that could cause silent failures
- **Minor**: Style inconsistencies, naming issues, small duplication, missing docs
  for public APIs
- **Info**: Suggestions and improvement opportunities, not problems per se

### Analysis Dimensions

#### Architecture

**A1. Structure & Organization**
- Are files grouped logically (by feature, layer, or domain)?
- Are there files in wrong directories or modules spanning too many concerns?
- Is nesting depth reasonable (< 4 levels)?
- Are there circular dependencies between modules?

**A2. Separation of Concerns**
- Is business logic separate from presentation/UI?
- Is data access separate from business rules?
- Is infrastructure (HTTP, file I/O, external APIs) isolated behind interfaces?
- Are cross-cutting concerns (auth, logging, validation) handled consistently?

**A3. Architectural Standards**
- Does the code follow the framework's recommended patterns?
- Are there anti-patterns specific to the detected framework?
- Is the dependency direction correct (inner layers don't depend on outer)?

**A4. Pattern Consistency**
- Are similar problems solved the same way throughout?
- Is error handling consistent (same pattern for same kind of errors)?
- Are data transformations done in consistent locations?

#### Code Quality

**Q1. Naming Conventions**
- Are names descriptive and unambiguous?
- Is casing consistent (camelCase, snake_case, PascalCase) per language norms?
- Do file names match their primary export/module?
- Are abbreviations used consistently or avoided?
- Check for misleading names (function named `getX` that actually sets something)

**Q2. KISS & Complexity**
- Files over 300 lines — can they be split meaningfully?
- Functions over 40 lines — can they be decomposed?
- Nesting depth over 3 levels — can early returns or extraction reduce it?
- Overly clever code that's hard to read — can it be simplified?
- Over-engineered abstractions for simple problems
- When a large component genuinely can't be split, evaluate whether an external
  library handles the concern better

**Q3. Code Duplication**
- Near-identical code blocks (3+ lines) appearing in multiple places
- Similar patterns that differ only in parameters — extract and parameterize
- Copy-pasted logic with minor variations — unify with a shared function
- Be pragmatic: 2-3 similar lines might be fine; 10+ duplicated lines are not

**Q4. Dead & Unused Code**
- Unused imports, variables, functions, types, classes
- Commented-out code blocks (remove or explain why they're kept)
- Unreachable code paths (dead branches after early returns)
- Feature flags that are permanently on/off
- For unused code that looks intentional: evaluate whether it should be reused
  as part of this refactor, documented as TODO, or removed

#### Reliability

**R1. Memory Safety**
- Unbounded collection growth (lists, maps growing without limits)
- Large file reads without streaming
- Missing pagination on database queries
- Caching without eviction/TTL
- String concatenation in loops (language-dependent)

**R2. SQL & Query Optimization**
- N+1 query patterns (loading associations in loops)
- Missing database indexes for frequently queried columns
- SQL parameter limits (e.g., PostgreSQL's 65535 parameter limit for IN clauses)
- Queries that could benefit from preloading/eager loading
- Raw SQL that should use parameterized queries (injection risk)

**R3. Database Batching**
- Individual inserts/updates in loops that should be batch operations
- Missing bulk upsert for large datasets
- Transaction scope too broad or too narrow

**R4. Deprecated API Usage**
- Deprecated language features or stdlib functions
- Deprecated library functions (check against latest stable versions)
- Framework features marked for removal

#### API & Compatibility

**C1. Breaking Changes**
- Changed function signatures without updating callers
- Removed or renamed public functions/endpoints
- Changed return types or error formats
- Modified configuration keys or environment variables

**C2. Backward Compatibility**
- When the codebase is fully controlled: flag changes but don't block on them
- When it has external consumers: breaking changes need migration paths
- Database schema changes that affect running instances

#### Operations

**O1. Logging**
- Scattered ad-hoc logging vs centralized approach
- Inconsistent log levels (debug used for errors, etc.)
- Missing context in log messages (no request ID, user ID, etc.)
- Sensitive data in logs (passwords, tokens, PII)
- Evaluate whether a centralized logging module/utility would help

**O2. Documentation**
- Missing or outdated README
- Public modules/functions without documentation
- Stale comments that describe code that has changed
- Missing setup/installation instructions
- Undocumented configuration options or environment variables
- Unnecessary comments that just restate the code

## Phase 4: Report

Generate a structured markdown report. Ask the user where to save it (default:
`docs/review-report.md`). Use this structure:

```markdown
# Codebase Review Report

**Scope**: [what was reviewed]
**Tech Stack**: [detected languages, frameworks, tools]
**Date**: [current date]

## Summary

| Severity | Count |
|----------|-------|
| Critical | X     |
| Major    | X     |
| Minor    | X     |
| Info     | X     |

## Critical Issues

### [CRT-001] [Dimension ID] Short title
- **File**: `path/to/file.ext:42`
- **Problem**: What's wrong, specifically
- **Impact**: What could go wrong / what's degraded
- **Fix**: Concrete recommendation
- **Effort**: Low / Medium / High

## Major Issues
### [MAJ-001] ...

## Minor Issues
### [MIN-001] ...

## Improvement Opportunities
### [INF-001] ...

## Approved Changes Checklist
- [ ] CRT-001: [short description]
- [ ] MAJ-001: [short description]
- ...

---
**Which items would you like me to fix?** You can approve all, select specific
IDs (e.g., CRT-001, MAJ-003), or tell me to skip certain ones.
```

The approval question at the end of the report is important — it must be part of the
saved `.md` file, not just said in conversation. This ensures anyone reading the report
(including future you) sees the action prompt.

After saving the report, also highlight the most impactful items conversationally.

## Phase 5: Execution

Once the user approves specific items:

1. **Plan the execution order** — Group related changes, handle dependencies (e.g.,
   extract a utility before updating its callers). Critical issues first.

2. **Make changes incrementally** — One logical change at a time. After each change:
   - Verify the file still parses/compiles
   - Verify closely related tests still pass
   - If a change cascades to other files, handle all affected files together

3. **Track progress** — Update the checklist in the report as items are completed.

4. **Handle surprises** — If executing a change reveals a new issue not in the
   report, flag it to the user rather than silently fixing it. Scope creep is
   the enemy of clean refactors.

## Phase 6: Validation

After all approved changes are executed:

1. **Run the build** — Use the project's build command. Fix any build errors
   introduced by the changes.

2. **Run tests** — Use the project's test command. Fix any test failures introduced
   by the changes. If a test failure reveals a bug in the refactor, fix the refactor
   — don't fix the test to match broken code.

3. **Run linters/formatters** — Use the project's quality tools. Apply formatting.

4. **Summary** — Tell the user what was done:
   - Number of files modified
   - Issues resolved (by ID)
   - Any new issues discovered during execution
   - Test/build status

## Language-Specific Patterns

Adapt your analysis to the detected tech stack. Apply the relevant patterns:

### Elixir / Phoenix / Ash
- Pattern match on function heads instead of case/if in body
- Use `with` chains for multi-step fallible operations
- Pipeline style for data transformations
- Resources should use code_interface for clean APIs
- LiveView: extract components, avoid large render/1 functions
- Check for `require Ash.Query` when using query macros
- Verify upsert_fields don't overwrite status fields

### TypeScript / React
- Prefer named exports over default exports for refactoring safety
- Extract custom hooks for shared stateful logic
- Components over 200 lines likely need splitting
- Check for proper cleanup in useEffect
- Ensure proper TypeScript strictness (no implicit any)

### Python
- Follow PEP 8 naming (snake_case functions, PascalCase classes)
- Use type hints for public function signatures
- Prefer dataclasses or Pydantic over raw dicts for structured data
- Check for bare `except:` clauses (should catch specific exceptions)

### Go
- Check error handling (no ignored errors without explicit comment)
- Exported vs unexported naming (PascalCase vs camelCase)
- Interface segregation (small, focused interfaces)
- Context propagation for cancellation

### General (All Languages)
- Check for hardcoded secrets, API keys, or credentials
- Verify .env files aren't committed
- Check for proper error propagation (not swallowing errors)
- Ensure graceful degradation for external service failures
