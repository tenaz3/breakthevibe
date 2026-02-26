.PHONY: dev test lint format typecheck setup migrate

setup:
	uv sync
	playwright install chromium

dev:
	uv run uvicorn breakthevibe.web.app:create_app --factory --reload

test:
	pytest -v

test-unit:
	pytest -v -m unit

test-integration:
	pytest -v -m integration

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy breakthevibe/

migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"
