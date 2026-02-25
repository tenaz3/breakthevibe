"""Application settings via Pydantic BaseSettings."""

import warnings
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    database_url: str = "postgresql+asyncpg://breakthevibe:breakthevibe@localhost:5432/breakthevibe"
    use_database: bool = False  # Set True in production to use PostgreSQL repos

    # App
    secret_key: str = "change-me-in-production"
    debug: bool = False
    log_level: str = "INFO"
    artifacts_dir: str = "~/.breakthevibe/projects"

    # Auth (env-var based; if unset, MVP mode accepts any credentials)
    admin_username: str | None = None
    admin_password: str | None = None

    # LLM Providers (all optional)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    settings = Settings()
    if settings.secret_key == "change-me-in-production":
        warnings.warn(
            "SECRET_KEY is using the insecure default. "
            "Set SECRET_KEY environment variable for production.",
            UserWarning,
            stacklevel=2,
        )
    return settings
