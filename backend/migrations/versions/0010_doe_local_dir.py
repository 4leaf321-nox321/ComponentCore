"""실험계획은 서버 보관 폴더에 먼저 만들고, 「보내기」 로 공유 폴더에 간다.

Revision ID: 0010_doe_local_dir
Revises: 0009_server_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_doe_local_dir"
down_revision = "0009_server_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doe_studies", sa.Column("local_dir", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "doe_studies", sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True)
    )
    # 이미 만든 것은 공유 폴더에 바로 썼다 — 그 폴더가 곧 보관 폴더이고, 이미 보낸 것으로 친다.
    op.execute("UPDATE doe_studies SET local_dir = export_dir, exported_at = created_at")


def downgrade() -> None:
    op.drop_column("doe_studies", "exported_at")
    op.drop_column("doe_studies", "local_dir")
