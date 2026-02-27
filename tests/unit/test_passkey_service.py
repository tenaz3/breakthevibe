"""Unit tests for PasskeyService."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from breakthevibe.models.database import WebAuthnCredential
from breakthevibe.storage.repositories.users import DatabaseUserRepository
from breakthevibe.storage.repositories.webauthn import DatabaseWebAuthnCredentialRepository
from breakthevibe.web.auth.passkey_service import PasskeyService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _make_service(
    engine: AsyncEngine,
) -> tuple[PasskeyService, DatabaseWebAuthnCredentialRepository, DatabaseUserRepository]:
    """Create a PasskeyService with DB repos for testing."""
    cred_repo = DatabaseWebAuthnCredentialRepository(engine)
    user_repo = DatabaseUserRepository(engine)
    service = PasskeyService(
        credential_repo=cred_repo,
        user_repo=user_repo,
        rp_id="localhost",
        rp_name="TestApp",
        origin="http://localhost:8000",
    )
    return service, cred_repo, user_repo


@pytest.mark.unit
class TestPasskeyServiceRegistration:
    async def test_begin_registration_returns_options(self, async_engine: AsyncEngine) -> None:
        service, _, user_repo = _make_service(async_engine)
        await user_repo.create(email="test@example.com")
        user = await user_repo.get_by_email("test@example.com")
        assert user is not None

        result = await service.begin_registration(
            user_id=user.id,
            user_email="test@example.com",
        )
        assert "options" in result
        assert "challenge_key" in result
        assert result["options"]["rp"]["id"] == "localhost"
        assert result["options"]["user"]["name"] == "test@example.com"

    async def test_begin_registration_excludes_existing_credentials(
        self, async_engine: AsyncEngine
    ) -> None:
        service, cred_repo, user_repo = _make_service(async_engine)
        user = await user_repo.create(email="test@example.com")

        existing = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"existing-cred",
            public_key=b"existing-key",
        )
        await cred_repo.create(existing)

        result = await service.begin_registration(
            user_id=user.id,
            user_email="test@example.com",
        )
        options = result["options"]
        assert "excludeCredentials" in options
        assert len(options["excludeCredentials"]) == 1

    async def test_complete_registration_expired_challenge(self, async_engine: AsyncEngine) -> None:
        service, _, _ = _make_service(async_engine)
        with pytest.raises(ValueError, match="Challenge expired"):
            await service.complete_registration(
                user_id="user-1",
                credential_json="{}",
                challenge_key="nonexistent-key",
            )


@pytest.mark.unit
class TestPasskeyServiceAuthentication:
    async def test_begin_authentication_returns_options(self, async_engine: AsyncEngine) -> None:
        service, _, _ = _make_service(async_engine)
        result = await service.begin_authentication()
        assert "options" in result
        assert "challenge_key" in result

    async def test_begin_authentication_with_email(self, async_engine: AsyncEngine) -> None:
        service, cred_repo, user_repo = _make_service(async_engine)
        user = await user_repo.create(email="test@example.com")

        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"cred-1",
            public_key=b"key-1",
            transports='["internal"]',
        )
        await cred_repo.create(cred)

        result = await service.begin_authentication(email="test@example.com")
        assert "options" in result
        options = result["options"]
        assert "allowCredentials" in options
        assert len(options["allowCredentials"]) == 1

    async def test_complete_authentication_expired_challenge(
        self, async_engine: AsyncEngine
    ) -> None:
        service, _, _ = _make_service(async_engine)
        with pytest.raises(ValueError, match="Challenge expired"):
            await service.complete_authentication(
                credential_json='{"id": "test", "rawId": "dGVzdA"}',
                challenge_key="nonexistent-key",
            )


@pytest.mark.unit
class TestPasskeyServiceHelpers:
    async def test_has_any_credentials_empty(self, async_engine: AsyncEngine) -> None:
        service, _, _ = _make_service(async_engine)
        assert await service.has_any_credentials() is False

    async def test_has_any_credentials_with_data(self, async_engine: AsyncEngine) -> None:
        service, cred_repo, user_repo = _make_service(async_engine)
        user = await user_repo.create(email="test@example.com")
        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"cred-1",
            public_key=b"key-1",
        )
        await cred_repo.create(cred)
        assert await service.has_any_credentials() is True
