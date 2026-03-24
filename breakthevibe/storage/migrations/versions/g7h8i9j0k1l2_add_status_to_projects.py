"""Add status column to projects table.

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g7h8i9j0k1l2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable first, backfill, then set server default
    op.add_column(
        "projects",
        sa.Column("status", sa.String(), nullable=True),
    )
    op.execute("UPDATE projects SET status = 'created' WHERE status IS NULL")
    op.alter_column("projects", "status", nullable=False, server_default="created")


def downgrade() -> None:
    op.drop_column("projects", "status")
