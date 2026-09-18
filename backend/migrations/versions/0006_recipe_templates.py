"""레시피 템플릿 — 사람이 저장한 「그리기」 의 출발점.

Revision ID: 0006_recipe_templates
Revises: 0005_personal_access_tokens
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0006_recipe_templates"
down_revision = "0005_personal_access_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_templates",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("recipe", JSONB(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_recipe_templates_owner_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_recipe_templates_owner_id", "recipe_templates", ["owner_id"])


def downgrade() -> None:
    op.drop_table("recipe_templates")
