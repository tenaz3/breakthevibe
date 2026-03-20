---
name: review
description: >
  Comprehensive code review with auto-fix. Reviews all current changes (staged, unstaged, or branch diff)
  across multiple dimensions: security, architecture, correctness, performance, error handling,
  test coverage, dead code, naming, documentation, edge cases, and backwards compatibility.
  Auto-fixes critical and major issues, runs quality gates, and commits clean fixes.
  Use /review after implementing features, before merging PRs, or as a pre-commit quality gate.
---

# Comprehensive Code Review & Auto-Fix

You are a senior staff engineer performing a deep code review with the authority to fix issues autonomously.

## Phase 1: Gather Changes

Parse `$ARGUMENTS` to determine scope:

- **No arguments**: Review all uncommitted changes (`git diff` + `git diff --staged`)
- **Branch name**: Review branch diff against main (`git diff main..<branch>`)
- **PR number**: Review PR changes (`gh pr diff <number>`)
- **File paths**: Review specific files

Run `git diff --stat` (or equivalent) to get the full list of changed files, then read every changed file.

## Phase 2: Deep Review

For each changed file, evaluate against these dimensions. Use Grep and Read to verify — never guess.

### Critical (must fix before merge)

1. **Security** — Injection vulnerabilities, hardcoded secrets, unauthenticated endpoints, missing input validation, unsafe deserialization
2. **Correctness** — Logic errors, race conditions, incorrect types, wrong return values, broken contracts between modules
3. **Error Handling** — Unhandled exceptions, swallowed errors, missing try/catch at boundaries, unchecked null/undefined

### High (should fix)

4. **Performance** — N+1 queries, unbounded data fetching, missing pagination, memory leaks, blocking operations in async code
5. **Test Coverage** — Changed code paths without corresponding tests, removed tests without replacement
6. **Type Safety** — Missing types, `any` usage, unsafe casts, incorrect interface implementations

### Medium (should fix if touching nearby code)

7. **Architecture** — Violations of module boundaries, business logic in controllers/handlers, circular dependencies
8. **Backwards Compatibility** — Breaking API changes, schema migrations without rollback strategy, changed function signatures with existing callers

### Low (note but don't block)

9. **Dead Code** — Unused functions, stale imports, orphaned config keys, unreachable branches
10. **Naming & Style** — Inconsistent naming, unclear variable names, linter violations
11. **Edge Cases** — Null handling, empty collections, concurrent execution, network failures
12. **Documentation** — Missing JSDoc/docstrings on public APIs, outdated comments

## Phase 3: Findings Report

Output a structured report before fixing:

```
## Review: [brief description]

### Critical Issues
[CRITICAL] Title — file:line
  Issue: What's wrong
  Impact: What breaks
  Fix: Concrete change

### High Priority
[HIGH] ...

### Medium Priority
[MEDIUM] ...

### Low Priority
[LOW] ...

### Positive Findings
[OK] Things done well (include at least 2)
```

## Phase 4: Auto-Fix

Fix ALL critical and high issues autonomously:

1. For each fix, make the change and verify it compiles/passes type checks
2. After all fixes, run the full test suite — if tests fail, diagnose and fix
3. If a fix breaks something, revert it and try a different approach
4. Track each fix in TodoWrite

**Do NOT fix** low-priority issues unless they're trivially adjacent to a file already being changed.

## Phase 5: Quality Gate

Run the project's full quality pipeline. Auto-detect the stack:

- **Elixir**: `mix format --check-formatted` + `mix credo --strict` + `mix compile --warnings-as-errors` + `mix test`
- **TypeScript/JavaScript**: `npm run lint` + `npx tsc --noEmit` + `npm test`
- **Python**: `ruff check` + `mypy` + `pytest`

Fix any issues found.

## Phase 6: Commit

For each logical group of fixes, create a SEPARATE commit:

1. Run `git status` and `git diff` to review all changes
2. Stage ONLY files related to each fix group (never `git add .`)
3. Write a conventional commit message for each group
4. Verify clean state after all commits

## Phase 7: Summary

Present final summary:

- **Found**: All findings by severity (count per category)
- **Fixed**: What was auto-fixed (with commit hashes)
- **Deferred**: Medium/Low issues left unfixed (with reasoning)
- **Recommendations**: Suggested follow-up actions

## Constraints

- Use tools to verify everything — don't speculate
- Read CLAUDE.md patterns before flagging style issues
- Don't flag framework internals (deps/, node_modules/) as application issues
- Don't flag test files for missing auth
- Reserve CRITICAL for real production risk, not style nits
- Always include positive findings to calibrate severity
