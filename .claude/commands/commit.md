---
description: Safe commit with quality checks — format, lint, test, then commit
argument-hint: [optional commit message or description of changes]
---

# Safe Commit Workflow

Before committing, run a full quality gate to catch issues early.

## Steps

1. **Check staged files**: Run `git diff --cached --name-only` and `git status` to see what will be committed. Flag any unrelated files or sensitive files (.env, credentials).

2. **Format**: Run `uv run ruff format breakthevibe/ tests/` to auto-format all Python code.

3. **Lint**: Run `uv run ruff check breakthevibe/ tests/ --fix` to fix linting issues. If unfixable issues remain, report them.

4. **Test**: Run `uv run pytest tests/ -x -q` to run the full test suite. Stop on first failure. If tests fail, diagnose and fix before committing.

5. **Review changes**: Run `git diff` to review all unstaged changes (from formatting/lint fixes). Stage any auto-fixed files.

6. **Commit**: Generate a conventional commit message (feat:, fix:, docs:, refactor:, test:) based on the actual changes. If the user provided a message hint in $ARGUMENTS, use that as guidance. Stage relevant files and commit.

## Rules
- NEVER commit if tests are failing
- NEVER include .env, credentials, or API keys
- NEVER use `git add -A` or `git add .` — add specific files
- If formatting or linting made changes, include those in the commit
- Review `git diff --cached` one final time before the actual commit
