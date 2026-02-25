.PHONY: dev test lint format typecheck setup migrate

setup:
	uv sync
	playwright install chromium

dev:
	fastapi dev breakthevibe/main.py

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
