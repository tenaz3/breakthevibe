---
description: Run full quality gate — format, lint, type check, and test
argument-hint: [optional: specific path or test to focus on]
---

# Quality Gate

Run the full quality pipeline to verify code health.

## Steps

1. **Format check**: Run `uv run ruff format --check breakthevibe/ tests/`. Report any unformatted files.

2. **Lint**: Run `uv run ruff check breakthevibe/ tests/`. Report any issues with file and line numbers.

3. **Type check**: Run `uv run mypy breakthevibe/ --strict`. Report any type errors.

4. **Tests**: Run `uv run pytest tests/ -q`. Report pass/fail counts.

5. **Summary**: Present a clear table of results:
   - Format: pass/fail
   - Lint: pass/fail (N issues)
   - Types: pass/fail (N errors)
   - Tests: pass/fail (N passed, M failed)

If $ARGUMENTS specifies a path, focus checks on that path only. Otherwise run against the full codebase.

## If issues are found
- Offer to auto-fix formatting and lint issues
- For type errors and test failures, diagnose the root cause before attempting fixes
