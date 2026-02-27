"""WebAuthn credential repository — PostgreSQL-backed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from breakthevibe.models.database import WebAuthnCredential, _utc_now

if TYPE_CHECKING:
    from datetime import datetime

logger = structlog.get_logger(__name__)


class DatabaseWebAuthnCredentialRepository:
    """PostgreSQL-backed credential store."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def create(self, credential: WebAuthnCredential) -> WebAuthnCredential:
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            session.add(credential)
            await session.commit()
            await session.refresh(credential)
            logger.info("webauthn_credential_created", user_id=credential.user_id)
            return credential

    async def get_by_credential_id(self, credential_id: bytes) -> WebAuthnCredential | None:
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(WebAuthnCredential).where(
                col(WebAuthnCredential.credential_id) == credential_id
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def list_for_user(self, user_id: str) -> list[WebAuthnCredential]:
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(WebAuthnCredential).where(col(WebAuthnCredential.user_id) == user_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_sign_count(
        self,
        credential_id: bytes,
        new_count: int,
        last_used_at: datetime | None = None,
    ) -> None:
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(WebAuthnCredential).where(
                col(WebAuthnCredential.credential_id) == credential_id
            )
            result = await session.execute(stmt)
            cred = result.scalars().first()
            if cred:
                cred.sign_count = new_count
                cred.last_used_at = last_used_at or _utc_now()
                session.add(cred)
                await session.commit()

    async def delete(self, credential_id: bytes) -> bool:
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(WebAuthnCredential).where(
                col(WebAuthnCredential.credential_id) == credential_id
            )
            result = await session.execute(stmt)
            cred = result.scalars().first()
            if not cred:
                return False
            await session.delete(cred)
            await session.commit()
            return True

    async def has_any(self) -> bool:
        """Check if any credentials exist (used for bootstrap detection)."""
        from sqlmodel import select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(WebAuthnCredential).limit(1)
            result = await session.execute(stmt)
            return result.scalars().first() is not None
