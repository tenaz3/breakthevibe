#!/usr/bin/env bash
set -euo pipefail

echo "Starting BreakTheVibe..."

# Run database migrations
alembic upgrade head

# Start the application
exec uvicorn breakthevibe.web.app:create_app --factory --host 0.0.0.0 --port 8000
