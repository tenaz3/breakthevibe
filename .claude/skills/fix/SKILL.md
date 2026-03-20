---
name: fix
description: >
  Autonomous bug fix workflow. Reproduces the bug with a failing test, enters a red-green-refactor
  loop (up to 5 iterations), runs full test suite + quality checks, then commits with a descriptive
  message. Use /fix with a bug description or when tests are failing.
---

# Autonomous Fix Workflow

Given a bug report or failing tests, enter an autonomous red-green-refactor loop and commit when green.

## Phase 1: Reproduce

1. If a bug is described, write a failing test that reproduces the exact bug
2. Run the project's test command to confirm it fails for the right reason
3. If tests are already failing (no bug description), skip to Phase 2

## Phase 2: Red-Green Loop (max 5 iterations)

For each iteration:

1. **Hypothesize** — Form a root cause hypothesis based on the failure output
2. **Fix** — Implement the minimal fix in source code (prefer fixing source over changing tests unless the test is wrong)
3. **Verify** — Run the failing test. If it passes, run the full test suite
4. **Track** — Log each hypothesis and result in TodoWrite
5. **Iterate** — If tests still fail, diagnose whether it's a regression from the fix or pre-existing, and try the next approach

**Autonomy rule**: Do NOT ask for user input until either all tests pass green, or 5 different approaches have been tried and need direction.

## Phase 3: Quality Gate

After all tests pass, run the project's quality checks. Auto-detect the stack:

- **Elixir**: `mix format --check-formatted` + `mix credo --strict` + `mix compile --warnings-as-errors`
- **TypeScript/JavaScript**: `npm run lint` (or equivalent from package.json) + `npx tsc --noEmit` (if TypeScript)
- **Python**: `ruff check` or `flake8` + `mypy` (if configured)

Fix any issues found.

## Phase 4: Commit

1. Run `git status` and `git diff` to review changes
2. Stage ONLY files related to this fix (never `git add .`)
3. Unstage any unrelated changes
4. Write a conventional commit message explaining:
   - What the bug was (root cause)
   - How it was fixed
5. Verify clean state with `git status`
