"""작업 꼬리표 — 프로젝트 · 제품군으로 거른다.

Revision ID: 0011_work_tags
Revises: 0010_doe_local_dir
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_work_tags"
down_revision = "0010_doe_local_dir"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("works", sa.Column("tags", JSONB, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("works", "tags")
