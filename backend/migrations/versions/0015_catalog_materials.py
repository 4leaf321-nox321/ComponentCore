"""올려 둔 물성 카탈로그 — MatNexus 에 못 닿을 때의 길.

폐쇄망 · 점검 · 방화벽으로 물성을 못 고르면 작업이 멈춘다. 그쪽의 내보내기 파일을 올려 두고
그것으로 고른다. **MatNexus 가 정본이고 이것은 사본**이라 언제든 다시 받아 덮어쓴다.

Revision ID: 0015_catalog_materials
Revises: 0014_conditions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0015_catalog_materials"
down_revision = "0014_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_materials",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        # 번호가 열쇠다 — 이름은 기준정보 개명에 따라 바뀐다.
        sa.Column("code", sa.String(40), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("family", sa.String(60), nullable=False, server_default=""),
        sa.Column("category", sa.String(60), nullable=False, server_default=""),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("catalog_materials")
