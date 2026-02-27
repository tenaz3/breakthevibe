"""Enhance test_runs table for full pipeline result storage.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pipeline result columns to test_runs."""
    op.add_column("test_runs", sa.Column("run_uuid", AutoString(), nullable=True))
    op.add_column("test_runs", sa.Column("completed_stages_json", sa.Text(), nullable=True))
    op.add_column("test_runs", sa.Column("failed_stage", AutoString(), nullable=True))
    op.add_column("test_runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("test_runs", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column("test_runs", sa.Column("suites_json", sa.Text(), nullable=True))
    op.add_column("test_runs", sa.Column("heal_warnings_json", sa.Text(), nullable=True))
    op.create_index("ix_test_runs_run_uuid", "test_runs", ["run_uuid"])


def downgrade() -> None:
    """Remove pipeline result columns from test_runs."""
    op.drop_index("ix_test_runs_run_uuid", table_name="test_runs")
    op.drop_column("test_runs", "heal_warnings_json")
    op.drop_column("test_runs", "suites_json")
    op.drop_column("test_runs", "duration_seconds")
    op.drop_column("test_runs", "error_message")
    op.drop_column("test_runs", "failed_stage")
    op.drop_column("test_runs", "completed_stages_json")
    op.drop_column("test_runs", "run_uuid")
