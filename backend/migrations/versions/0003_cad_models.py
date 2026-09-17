"""CAD 모델 · 버전(레시피) — 지그 프로젝트가 모델을 제품으로 가리킬 수 있다.

Revision ID: 0003_cad_models
Revises: 0002_jobs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0003_cad_models"
down_revision = "0002_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cad_models",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_cad_models_owner_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_cad_models_owner_id", "cad_models", ["owner_id"])
    op.create_index("ix_cad_models_deleted_at", "cad_models", ["deleted_at"])

    op.create_table(
        "cad_model_versions",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("recipe", JSONB(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("job_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["cad_models.id"],
            name="fk_cad_model_versions_model_id_cad_models",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_cad_model_versions_created_by_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_cad_model_versions_job_id_jobs",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("model_id", "number", name="uq_cad_model_versions_number"),
    )
    op.create_index("ix_cad_model_versions_model_id", "cad_model_versions", ["model_id"])

    op.add_column(
        "jig_projects", sa.Column("product_model_id", PgUUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_jig_projects_product_model_id_cad_models",
        "jig_projects",
        "cad_models",
        ["product_model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jig_projects_product_model_id", "jig_projects", ["product_model_id"])


def downgrade() -> None:
    op.drop_index("ix_jig_projects_product_model_id", table_name="jig_projects")
    op.drop_constraint(
        "fk_jig_projects_product_model_id_cad_models", "jig_projects", type_="foreignkey"
    )
    op.drop_column("jig_projects", "product_model_id")
    op.drop_table("cad_model_versions")
    op.drop_table("cad_models")
