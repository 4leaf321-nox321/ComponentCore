"""공유 폴더의 보관 기한 — 영구보관과 「다 읽었다」.

공유 폴더는 보관소가 아니라 전달 큐다(`docs/오케스트레이션-연계-설계.md`). 기한이 지나면
**사본만** 지우고 서버 보관 폴더와 설정은 남긴다 — 「보내기」 를 다시 누르면 같은 폴더가 다시
선다. 다만 지우는 일은 되돌릴 수 없으니 스터디마다 예외를 켤 수 있어야 한다.

Revision ID: 0016_doe_retention
Revises: 0015_catalog_materials
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_doe_retention"
down_revision = "0015_catalog_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doe_studies",
        sa.Column("keep_forever", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "doe_studies", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("doe_studies", "released_at")
    op.drop_column("doe_studies", "keep_forever")
