"""add audit logs table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-26 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add audit_logs table."""
    op.create_table(
        "audit_logs",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "user_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "resource_type",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "resource_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "details_json",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "ip_address",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "request_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_org_id"), "audit_logs", ["org_id"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    # Composite index for common query pattern
    op.create_index(
        "ix_audit_logs_org_created",
        "audit_logs",
        ["org_id", "created_at"],
    )


def downgrade() -> None:
    """Remove audit_logs table."""
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_org_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
