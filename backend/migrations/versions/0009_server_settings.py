"""관리자가 화면에서 바꾸는 서버 설정 · 실험계획에서 재료를 뺀다.

Revision ID: 0009_server_settings
Revises: 0008_work_kind
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0009_server_settings"
down_revision = "0008_work_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_settings",
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value", JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            PgUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # 재료는 질량 계산에만 쓰던 값 — 실험계획은 바꾼 변수만 다루기로 했다.
    op.drop_column("doe_studies", "material")


def downgrade() -> None:
    op.add_column(
        "doe_studies",
        sa.Column("material", sa.String(30), nullable=False, server_default="aluminum"),
    )
    op.drop_table("server_settings")
