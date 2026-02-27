"""Add webauthn_credentials table.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", AutoString(), primary_key=True),
        sa.Column("user_id", AutoString(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aaguid", AutoString(), nullable=False, server_default=""),
        sa.Column("transports", AutoString(), nullable=False, server_default="[]"),
        sa.Column("device_type", AutoString(), nullable=False, server_default="single_device"),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("webauthn_user_id", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
