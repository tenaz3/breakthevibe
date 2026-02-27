#!/usr/bin/env bash
set -euo pipefail

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting BreakTheVibe..."
exec uv run uvicorn breakthevibe.web.app:create_app \
    --factory \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}"
