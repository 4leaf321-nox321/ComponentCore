"""규격 부품 — 공용 부품의 규격 사양(`parts.standard`).

관리자가 공용 부품(사내에서 그린 받침 · 위치 핀 · 토글 클램프)에 종류 · 품번 · 쓰는 버전 ·
치수를 붙이면 지그 생성기가 요구에 맞는 것을 골라 놓고 부품표에 품번 · 수량을 남긴다. 비면 일반
부품이다.

Revision ID: 0033_standard_parts
Revises: 0032_jig_recipe_conditions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_standard_parts"
down_revision = "0032_jig_recipe_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parts",
        sa.Column("standard", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parts", "standard")
