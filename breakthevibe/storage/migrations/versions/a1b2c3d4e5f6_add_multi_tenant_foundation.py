"""add multi-tenant foundation

Revision ID: a1b2c3d4e5f6
Revises: 3a8565d6ccd1
Create Date: 2026-02-26 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "3a8565d6ccd1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SENTINEL_ORG_ID = "00000000-0000-0000-0000-000000000001"
SENTINEL_USER_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    """Add multi-tenant tables and org_id to all existing tables."""
    # --- 1. Create new multi-tenant tables ---
    op.create_table(
        "organizations",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("clerk_org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "plan", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="free"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clerk_org_id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("clerk_user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clerk_user_id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"])

    op.create_table(
        "organization_memberships",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "role",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="member",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_memberships_org_id"),
        "organization_memberships",
        ["org_id"],
    )
    op.create_index(
        op.f("ix_organization_memberships_user_id"),
        "organization_memberships",
        ["user_id"],
    )

    # --- 2. Add nullable org_id to all existing tables ---
    tables = [
        "projects",
        "crawl_runs",
        "routes",
        "test_cases",
        "test_runs",
        "test_results",
        "llm_settings",
    ]
    for table in tables:
        op.add_column(
            table,
            sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        )

    # --- 3. Insert sentinel org and user ---
    op.execute(
        sa.text(
            "INSERT INTO organizations (id, name, plan, created_at, updated_at) "
            "VALUES (:id, :name, :plan, NOW(), NOW())"
        ).bindparams(id=SENTINEL_ORG_ID, name="Default", plan="free")
    )
    op.execute(
        sa.text(
            "INSERT INTO users (id, email, name, is_active, created_at, updated_at) "
            "VALUES (:id, :email, :name, true, NOW(), NOW())"
        ).bindparams(id=SENTINEL_USER_ID, email="admin@localhost", name="Admin")
    )
    op.execute(
        sa.text(
            "INSERT INTO organization_memberships (id, org_id, user_id, role, created_at) "
            "VALUES (:id, :org_id, :user_id, :role, NOW())"
        ).bindparams(
            id="00000000-0000-0000-0000-000000000003",
            org_id=SENTINEL_ORG_ID,
            user_id=SENTINEL_USER_ID,
            role="admin",
        )
    )

    # --- 4. Backfill org_id with sentinel value ---
    for table_name in tables:
        tbl = sa.table(table_name, sa.column("org_id"))
        op.execute(tbl.update().where(tbl.c.org_id.is_(None)).values(org_id=SENTINEL_ORG_ID))

    # --- 5. Set NOT NULL and create indexes ---
    for table in tables:
        op.alter_column(table, "org_id", nullable=False)
        op.create_index(op.f(f"ix_{table}_org_id"), table, ["org_id"])


def downgrade() -> None:
    """Remove multi-tenant tables and org_id columns."""
    tables = [
        "projects",
        "crawl_runs",
        "routes",
        "test_cases",
        "test_runs",
        "test_results",
        "llm_settings",
    ]

    for table in tables:
        op.drop_index(op.f(f"ix_{table}_org_id"), table_name=table)
        op.drop_column(table, "org_id")

    op.drop_index(
        op.f("ix_organization_memberships_user_id"),
        table_name="organization_memberships",
    )
    op.drop_index(
        op.f("ix_organization_memberships_org_id"),
        table_name="organization_memberships",
    )
    op.drop_table("organization_memberships")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_table("organizations")
