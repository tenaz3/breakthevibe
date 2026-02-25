# Stage 1: Build dependencies
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy installed dependencies from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY breakthevibe/ breakthevibe/
COPY pyproject.toml ./
COPY alembic.ini* ./

# Install project itself
RUN uv sync --frozen --no-dev

# Install Playwright browsers
RUN uv run playwright install chromium

# Create artifact directory
RUN mkdir -p /data/artifacts

ENV PYTHONUNBUFFERED=1
ENV BTV_ARTIFACT_DIR=/data/artifacts
ENV BTV_DATABASE_URL=postgresql+asyncpg://breakthevibe:breakthevibe@db:5432/breakthevibe

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uv", "run", "uvicorn", "breakthevibe.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
