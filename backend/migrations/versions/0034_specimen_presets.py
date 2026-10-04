"""사내 시험 규격 — `specimen_presets`.

공개 규격(ASTM · ISO)의 프리셋은 코드(`core/specimens/data`)에 있고, 사내 시험법 · 고객사 규격은
관리자가 이 표에 같은 모양으로 둔다(ADR 0006). 행은 넣지 않는다 — 비어서 시작한다.

Revision ID: 0034_specimen_presets
Revises: 0033_standard_parts
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_specimen_presets"
down_revision = "0033_standard_parts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "specimen_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("test", sa.String(length=20), nullable=False),
        sa.Column("standard", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_specimen_presets_test", "specimen_presets", ["test"])
    op.create_index("ix_specimen_presets_deleted_at", "specimen_presets", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_specimen_presets_deleted_at", table_name="specimen_presets")
    op.drop_index("ix_specimen_presets_test", table_name="specimen_presets")
    op.drop_table("specimen_presets")
