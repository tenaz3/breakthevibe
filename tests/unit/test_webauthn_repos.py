"""Unit tests for WebAuthn credential and user DB repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from breakthevibe.models.database import WebAuthnCredential
from breakthevibe.storage.repositories.users import DatabaseUserRepository
from breakthevibe.storage.repositories.webauthn import DatabaseWebAuthnCredentialRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.unit
class TestDatabaseWebAuthnCredentialRepository:
    async def test_create_and_get(self, async_engine: AsyncEngine) -> None:
        user_repo = DatabaseUserRepository(async_engine)
        user = await user_repo.create(email="cred-test@example.com")
        repo = DatabaseWebAuthnCredentialRepository(async_engine)
        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"cred-id-123",
            public_key=b"pub-key-456",
            sign_count=0,
        )
        await repo.create(cred)
        found = await repo.get_by_credential_id(b"cred-id-123")
        assert found is not None
        assert found.user_id == user.id
        assert found.public_key == b"pub-key-456"

    async def test_get_missing(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseWebAuthnCredentialRepository(async_engine)
        assert await repo.get_by_credential_id(b"nonexistent") is None

    async def test_list_for_user(self, async_engine: AsyncEngine) -> None:
        user_repo = DatabaseUserRepository(async_engine)
        user1 = await user_repo.create(email="user1@example.com")
        user2 = await user_repo.create(email="user2@example.com")

        repo = DatabaseWebAuthnCredentialRepository(async_engine)
        cred1 = WebAuthnCredential(
            user_id=user1.id,
            credential_id=b"cred-1",
            public_key=b"key-1",
        )
        cred2 = WebAuthnCredential(
            user_id=user1.id,
            credential_id=b"cred-2",
            public_key=b"key-2",
        )
        cred3 = WebAuthnCredential(
            user_id=user2.id,
            credential_id=b"cred-3",
            public_key=b"key-3",
        )
        await repo.create(cred1)
        await repo.create(cred2)
        await repo.create(cred3)

        user1_creds = await repo.list_for_user(user1.id)
        assert len(user1_creds) == 2
        user2_creds = await repo.list_for_user(user2.id)
        assert len(user2_creds) == 1

    async def test_update_sign_count(self, async_engine: AsyncEngine) -> None:
        user_repo = DatabaseUserRepository(async_engine)
        user = await user_repo.create(email="sign-count@example.com")

        repo = DatabaseWebAuthnCredentialRepository(async_engine)
        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"cred-1",
            public_key=b"key-1",
            sign_count=0,
        )
        await repo.create(cred)
        await repo.update_sign_count(b"cred-1", new_count=5)

        found = await repo.get_by_credential_id(b"cred-1")
        assert found is not None
        assert found.sign_count == 5
        assert found.last_used_at is not None

    async def test_delete(self, async_engine: AsyncEngine) -> None:
        user_repo = DatabaseUserRepository(async_engine)
        user = await user_repo.create(email="delete@example.com")

        repo = DatabaseWebAuthnCredentialRepository(async_engine)
        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"cred-1",
            public_key=b"key-1",
        )
        await repo.create(cred)
        assert await repo.delete(b"cred-1") is True
        assert await repo.get_by_credential_id(b"cred-1") is None
        assert await repo.delete(b"cred-1") is False

    async def test_has_any(self, async_engine: AsyncEngine) -> None:
        user_repo = DatabaseUserRepository(async_engine)
        user = await user_repo.create(email="has-any@example.com")

        repo = DatabaseWebAuthnCredentialRepository(async_engine)
        assert await repo.has_any() is False

        cred = WebAuthnCredential(
            user_id=user.id,
            credential_id=b"cred-1",
            public_key=b"key-1",
        )
        await repo.create(cred)
        assert await repo.has_any() is True


@pytest.mark.unit
class TestDatabaseUserRepository:
    async def test_create_and_get(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseUserRepository(async_engine)
        user = await repo.create(email="test@example.com", name="Test User")
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.is_active is True

        found = await repo.get_by_id(user.id)
        assert found is not None
        assert found.email == "test@example.com"

    async def test_get_by_email(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseUserRepository(async_engine)
        await repo.create(email="test@example.com")
        found = await repo.get_by_email("test@example.com")
        assert found is not None
        assert found.email == "test@example.com"

    async def test_get_by_email_missing(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseUserRepository(async_engine)
        assert await repo.get_by_email("nonexistent@example.com") is None

    async def test_has_any(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseUserRepository(async_engine)
        assert await repo.has_any() is False
        await repo.create(email="test@example.com")
        assert await repo.has_any() is True

    async def test_get_user_org_role(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseUserRepository(async_engine)
        user = await repo.create(email="test@example.com")
        result = await repo.get_user_org_role(user.id)
        assert result is not None
        org_id, role = result
        assert role == "admin"

    async def test_get_user_org_role_missing(self, async_engine: AsyncEngine) -> None:
        repo = DatabaseUserRepository(async_engine)
        assert await repo.get_user_org_role("nonexistent") is None
