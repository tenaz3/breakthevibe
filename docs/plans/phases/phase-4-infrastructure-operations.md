# Phase 4: Infrastructure & Operations

> **Status**: Not started
> **Depends on**: Independent (can start anytime)
> **Estimated scope**: ~6 files created, ~5 modified
> **Branch**: `feat/multi-tenant-saas`

---

## 1. Objective

Make the Docker Compose stack production-grade. Add configurable CORS, TLS via Caddy, security headers, enhanced health checks, and structured monitoring. Enable multi-worker app deployment behind a reverse proxy.

---

## 2. Configurable CORS

**Modify: `breakthevibe/config/settings.py`**

```python
# Infrastructure
environment: str = "development"   # development | staging | production
allowed_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
```

**Modify: `breakthevibe/web/app.py`**

```python
# BEFORE:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    ...
)

# AFTER:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

---

## 3. Security Headers Middleware

**Create: `breakthevibe/web/security_headers.py`**

```python
"""Security headers middleware for defense-in-depth."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        # CSP — allow self and inline styles for Jinja templates
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; img-src 'self' data:;"
        )
        return response
```

**Add to `app.py`**:

```python
from breakthevibe.web.security_headers import SecurityHeadersMiddleware

# In create_app(), add before other middleware:
app.add_middleware(SecurityHeadersMiddleware)
```

---

## 4. Enhanced Health Check

**Create: `breakthevibe/web/health.py`**

```python
"""Enhanced health check with dependency status."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def check_health() -> dict[str, Any]:
    """Return detailed health status including dependencies."""
    from breakthevibe.config.settings import get_settings

    settings = get_settings()
    checks: dict[str, str] = {}

    # Database check
    if settings.use_database:
        try:
            from sqlalchemy import text
            from sqlmodel.ext.asyncio.session import AsyncSession
            from breakthevibe.storage.database import get_engine

            async with AsyncSession(get_engine()) as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "healthy"
        except Exception as e:
            checks["database"] = f"unhealthy: {e}"
    else:
        checks["database"] = "skipped (in-memory mode)"

    # Determine overall status
    overall = "healthy"
    for status in checks.values():
        if "unhealthy" in status:
            overall = "degraded"
            break

    return {
        "status": overall,
        "version": "0.1.0",
        "auth_mode": settings.auth_mode,
        "environment": settings.environment,
        "checks": checks,
    }
```

**Update health route in `app.py`**:

```python
@app.get("/api/health")
async def health_check() -> dict:
    from breakthevibe.web.health import check_health
    return await check_health()
```

---

## 5. Docker Compose Production Overlay

**Create: `docker-compose.prod.yml`**

```yaml
# Production overlay — use with: docker compose -f docker-compose.yml -f docker-compose.prod.yml up
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      app:
        condition: service_healthy
    restart: unless-stopped

  db:
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD required}
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
    restart: unless-stopped

  app:
    ports: []  # Remove direct port exposure; Caddy handles it
    environment:
      DATABASE_URL: postgresql+asyncpg://breakthevibe:${DB_PASSWORD}@db:5432/breakthevibe
      USE_DATABASE: "true"
      SECRET_KEY: ${SECRET_KEY:?SECRET_KEY required}
      ENVIRONMENT: production
      LOG_LEVEL: INFO
      ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-https://app.breakthevibe.io}
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
          cpus: "2.0"
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
```

**Create: `docker-compose.clerk.yml`**

```yaml
# Clerk overlay — use with: docker compose -f docker-compose.yml -f docker-compose.clerk.yml up
services:
  app:
    environment:
      AUTH_MODE: clerk
      CLERK_SECRET_KEY: ${CLERK_SECRET_KEY:?required}
      CLERK_PUBLISHABLE_KEY: ${CLERK_PUBLISHABLE_KEY:-}
      CLERK_WEBHOOK_SECRET: ${CLERK_WEBHOOK_SECRET:?required}
      CLERK_ISSUER: ${CLERK_ISSUER:?required}
      CLERK_JWKS_URL: ${CLERK_JWKS_URL:?required}
      CLERK_AUDIENCE: ${CLERK_AUDIENCE:-}
```

---

## 6. Caddyfile

**Create: `Caddyfile`**

```
{$DOMAIN:localhost} {
    reverse_proxy app:8000 {
        lb_policy round_robin
        health_uri /api/health
        health_interval 10s
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    log {
        output stdout
        format json
    }
}
```

---

## 7. Database Connection Pooling

**Modify: `breakthevibe/storage/database.py`**

```python
@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,         # NEW: verify connections before use
        pool_recycle=3600,           # NEW: recycle after 1 hour
    )
```

---

## 8. Environment Configuration Reference

| Setting | Development | Staging | Production |
|---|---|---|---|
| `ENVIRONMENT` | development | staging | production |
| `DEBUG` | true | false | false |
| `USE_DATABASE` | false | true | true |
| `AUTH_MODE` | single | clerk | clerk |
| `LOG_LEVEL` | DEBUG | INFO | INFO |
| `ALLOWED_ORIGINS` | http://localhost:8000 | https://staging.breakthevibe.io | https://app.breakthevibe.io |
| `SECRET_KEY` | change-me-in-production | (random 64-char) | (random 64-char) |
| `DB_PASSWORD` | breakthevibe | (random) | (random) |

---

## 9. CI/CD Enhancements

**Modify: `.github/workflows/ci.yml`**

Add migration safety check job:

```yaml
  migration-check:
    runs-on: ubuntu-latest
    needs: [lint, typecheck]
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: breakthevibe
          POSTGRES_PASSWORD: breakthevibe
          POSTGRES_DB: breakthevibe
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --frozen
      - name: Check for pending migrations
        env:
          DATABASE_URL: postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe
        run: |
          uv run alembic upgrade head
          uv run alembic check
```

---

## 10. .env.example Update

**Modify: `.env.example`**

Add all new variables:

```bash
# === Core ===
DATABASE_URL=postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe
USE_DATABASE=false
SECRET_KEY=change-me-in-production
DEBUG=true
LOG_LEVEL=INFO
ENVIRONMENT=development
ARTIFACTS_DIR=~/.breakthevibe/projects

# === Auth ===
AUTH_MODE=single
ADMIN_USERNAME=
ADMIN_PASSWORD=

# === Clerk (required when AUTH_MODE=clerk) ===
CLERK_SECRET_KEY=
CLERK_PUBLISHABLE_KEY=
CLERK_WEBHOOK_SECRET=
CLERK_ISSUER=
CLERK_AUDIENCE=
CLERK_JWKS_URL=

# === CORS ===
ALLOWED_ORIGINS=["http://localhost:8000"]

# === LLM Providers ===
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# === S3/R2 (Phase 7) ===
USE_S3=false
S3_BUCKET=
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_REGION=auto
```

---

## 11. Verification Checklist

- [ ] CORS allows configured origins only
- [ ] Security headers present on all responses
- [ ] Health check returns DB status
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` starts
- [ ] Caddy terminates TLS and proxies to app
- [ ] App runs with 2 replicas behind Caddy
- [ ] DB connection pool handles concurrent requests
- [ ] CI migration check job passes
- [ ] `.env.example` documents all variables

---

## 12. Files Summary

| Action | File |
|---|---|
| CREATE | `breakthevibe/web/security_headers.py` (~25 lines) |
| CREATE | `breakthevibe/web/health.py` (~45 lines) |
| CREATE | `docker-compose.prod.yml` (~45 lines) |
| CREATE | `docker-compose.clerk.yml` (~15 lines) |
| CREATE | `Caddyfile` (~20 lines) |
| MODIFY | `breakthevibe/config/settings.py` (environment, allowed_origins) |
| MODIFY | `breakthevibe/web/app.py` (dynamic CORS, security headers, health) |
| MODIFY | `breakthevibe/storage/database.py` (pool settings) |
| MODIFY | `.github/workflows/ci.yml` (migration check) |
| MODIFY | `.env.example` (all new variables) |
