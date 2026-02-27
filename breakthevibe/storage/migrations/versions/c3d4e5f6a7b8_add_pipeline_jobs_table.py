"""add pipeline jobs table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-26 19:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pipeline_jobs table."""
    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("org_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "job_type",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="full",
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column(
            "rules_yaml", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""
        ),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_jobs_org_id"), "pipeline_jobs", ["org_id"])


def downgrade() -> None:
    """Remove pipeline_jobs table."""
    op.drop_index(op.f("ix_pipeline_jobs_org_id"), table_name="pipeline_jobs")
    op.drop_table("pipeline_jobs")
