.PHONY: install setup dev test test-unit test-integration lint format typecheck migrate migrate-new quality

# --- Setup ---

install:
	uv sync
	uv run playwright install chromium

setup: install migrate

# --- Development ---

dev:
	docker compose up -d db
	@sleep 2
	uv run alembic upgrade head
	uv run uvicorn breakthevibe.web.app:create_app --factory --reload --port 8000

# --- Testing ---

test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit/ -v

test-integration:
	uv run pytest tests/integration/ -v

# --- Code Quality ---

lint:
	uv run ruff check breakthevibe/ tests/

format:
	uv run ruff format breakthevibe/ tests/

typecheck:
	uv run mypy breakthevibe/ --strict

quality: format lint test

# --- Database ---

migrate:
	uv run alembic upgrade head

migrate-new:
	uv run alembic revision --autogenerate -m "$(msg)"
