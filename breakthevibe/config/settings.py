"""Application settings via Pydantic BaseSettings."""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings

SENTINEL_ORG_ID = "00000000-0000-0000-0000-000000000001"
SENTINEL_USER_ID = "00000000-0000-0000-0000-000000000002"


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    database_url: str = "postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # App
    secret_key: str = "change-me-in-production"
    debug: bool = False
    log_level: str = "INFO"
    artifacts_dir: str = "~/.breakthevibe/projects"

    # Multi-tenancy
    auth_mode: Literal["single", "clerk", "passkey"] = "single"

    # Auth (env-var based; if unset, MVP mode accepts any credentials)
    admin_username: str | None = None
    admin_password: str | None = None

    # WebAuthn / Passkey (used when auth_mode == "passkey")
    webauthn_rp_id: str = "localhost"  # Relying party ID (domain, no port/scheme)
    webauthn_rp_name: str = "BreakTheVibe"
    webauthn_origin: str = "http://localhost:8000"  # Full origin including scheme + port

    # Clerk (required when auth_mode == "clerk")
    clerk_publishable_key: str | None = None
    clerk_secret_key: str | None = None
    clerk_webhook_secret: str | None = None
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_frontend_api: str | None = None

    # Environment & CORS
    environment: str = "development"
    allowed_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]

    # SSRF
    allow_private_urls: bool = False

    # Object Storage (S3/R2)
    use_s3: bool = False
    s3_bucket: str = ""
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "auto"

    # LLM Providers (all optional)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    @property
    def llm_configured(self) -> bool:
        """Return True if at least one LLM provider API key is set."""
        return bool(self.anthropic_api_key or self.openai_api_key or self.google_api_key)


_DEFAULT_SECRET_KEY = "change-me-in-production"  # nosec B105


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance.

    Raises:
        RuntimeError: When the default secret key is used outside of development.
    """
    settings = Settings()
    if settings.secret_key == _DEFAULT_SECRET_KEY:
        if settings.environment != "development":
            raise RuntimeError(
                "SECRET_KEY must be changed from default for non-development environments"
            )
        warnings.warn(
            "SECRET_KEY is using the insecure default. "
            "Set SECRET_KEY environment variable for production.",
            UserWarning,
            stacklevel=2,
        )
    return settings
