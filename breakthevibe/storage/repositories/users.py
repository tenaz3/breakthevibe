"""User repository — PostgreSQL-backed."""

from __future__ import annotations

from typing import Any

import structlog

from breakthevibe.config.settings import SENTINEL_ORG_ID
from breakthevibe.models.database import (
    Organization,
    OrganizationMembership,
    User,
    _utc_now,
)

logger = structlog.get_logger(__name__)


class DatabaseUserRepository:
    """PostgreSQL-backed user store."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def create(self, email: str, name: str = "", role: str = "admin") -> User:
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            user = User(email=email, name=name or email, is_active=True)
            session.add(user)
            await session.flush()  # populate user.id without committing

            # Create org membership for sentinel org (same transaction)
            membership = OrganizationMembership(
                org_id=SENTINEL_ORG_ID,
                user_id=user.id,
                role=role,
            )
            session.add(membership)
            await session.commit()
            await session.refresh(user)

            logger.info("user_created", user_id=user.id, email=email, role=role)
            return user

    async def get_by_id(self, user_id: str) -> User | None:
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(User).where(col(User.id) == user_id, col(User.is_active).is_(True))
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_by_email(self, email: str) -> User | None:
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(User).where(col(User.email) == email, col(User.is_active).is_(True))
            result = await session.execute(stmt)
            return result.scalars().first()

    async def has_any(self) -> bool:
        """Check if any active users exist."""
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(User).where(col(User.is_active).is_(True)).limit(1)
            result = await session.execute(stmt)
            return result.scalars().first() is not None

    async def get_user_org_role(self, user_id: str) -> tuple[str, str] | None:
        """Return (org_id, role) for a user from their org membership."""
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(OrganizationMembership).where(
                col(OrganizationMembership.user_id) == user_id
            )
            result = await session.execute(stmt)
            membership = result.scalars().first()
            if not membership:
                return None
            return membership.org_id, membership.role

    async def ensure_sentinel_org(self) -> None:
        """Ensure the sentinel organization exists (for bootstrap)."""
        from sqlmodel import col, select
        from sqlmodel.ext.asyncio.session import AsyncSession

        async with AsyncSession(self._engine) as session:
            stmt = select(Organization).where(col(Organization.id) == SENTINEL_ORG_ID)
            result = await session.execute(stmt)
            if not result.scalars().first():
                org = Organization(
                    id=SENTINEL_ORG_ID,
                    name="Default Organization",
                    plan="free",
                    created_at=_utc_now(),
                    updated_at=_utc_now(),
                )
                session.add(org)
                await session.commit()
                logger.info("sentinel_org_created")
