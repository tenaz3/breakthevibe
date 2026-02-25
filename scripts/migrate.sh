#!/usr/bin/env bash
set -euo pipefail

echo "Running database migrations..."

if [ "${1:-}" = "new" ]; then
    if [ -z "${2:-}" ]; then
        echo "Usage: ./scripts/migrate.sh new 'migration message'"
        exit 1
    fi
    alembic revision --autogenerate -m "$2"
else
    alembic upgrade head
fi

echo "Migrations complete."
