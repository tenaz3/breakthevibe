"""add subscription and usage tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-26 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add subscription and usage tracking tables."""
    op.create_table(
        "subscriptions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "plan", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="free"
        ),
        sa.Column(
            "status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="active"
        ),
        sa.Column("stripe_customer_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("stripe_subscription_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id"),
    )
    op.create_index(op.f("ix_subscriptions_org_id"), "subscriptions", ["org_id"])

    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("metric", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("period", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_records_org_id"), "usage_records", ["org_id"])
    op.create_index(op.f("ix_usage_records_metric"), "usage_records", ["metric"])
    # Unique constraint for ON CONFLICT upsert (C-5)
    op.create_unique_constraint(
        "uq_usage_records_org_metric_period",
        "usage_records",
        ["org_id", "metric", "period"],
    )


def downgrade() -> None:
    """Remove subscription and usage tables."""
    op.drop_constraint("uq_usage_records_org_metric_period", "usage_records", type_="unique")
    op.drop_index(op.f("ix_usage_records_metric"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_org_id"), table_name="usage_records")
    op.drop_table("usage_records")

    op.drop_index(op.f("ix_subscriptions_org_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
