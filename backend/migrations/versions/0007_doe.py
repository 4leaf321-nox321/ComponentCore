"""실험계획(DOE) — 설계점 묶음과 그 결과.

Revision ID: 0007_doe
Revises: 0006_recipe_templates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0007_doe"
down_revision = "0006_recipe_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doe_studies",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("work_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("recipe", JSONB(), nullable=False),
        sa.Column("factors", JSONB(), nullable=False),
        sa.Column("method", sa.String(20), nullable=False, server_default="factorial"),
        sa.Column("samples", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("material", sa.String(30), nullable=False, server_default="aluminum"),
        sa.Column("export_dir", sa.Text(), nullable=False, server_default=""),
        sa.Column("job_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_doe_studies_owner_id", "doe_studies", ["owner_id"])
    op.create_index("ix_doe_studies_work_id", "doe_studies", ["work_id"])

    op.create_table(
        "doe_points",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("params", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("geometry", JSONB(), nullable=True),
        sa.Column("step_file", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["study_id"], ["doe_studies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_doe_points_study_id", "doe_points", ["study_id"])
    op.create_index("ix_doe_points_status", "doe_points", ["status"])


def downgrade() -> None:
    op.drop_table("doe_points")
    op.drop_table("doe_studies")
