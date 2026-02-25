import pytest

from breakthevibe.config.settings import Settings


@pytest.mark.unit
class TestSettings:
    def test_default_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        settings = Settings()
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert "postgresql" in str(settings.database_url)

    def test_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/mydb")
        monkeypatch.setenv("SECRET_KEY", "my-secret")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        settings = Settings()
        assert settings.debug is True
        assert settings.log_level == "DEBUG"

    def test_anthropic_key_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        settings = Settings()
        assert settings.anthropic_api_key is None

    def test_ollama_base_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        settings = Settings()
        assert settings.ollama_base_url == "http://localhost:11434"
