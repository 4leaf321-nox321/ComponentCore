"""공용 공간(부품 · 지그 · 템플릿)에도 **폴더** — 내 작업과 같은 경로 한 칸.

폴더 표는 두지 않는다(ADR 0004) — 항목이 경로를 들고, 폴더는 그 안에 항목이 있을 때 있다.
있는 항목은 맨 위(빈 경로)에 둔다.

Revision ID: 0024_catalog_folders
Revises: 0023_work_folder
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_catalog_folders"
down_revision = "0023_work_folder"
branch_labels = None
depends_on = None

_TABLES = ("parts", "jigs", "recipe_templates")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("folder", sa.String(255), nullable=False, server_default="")
        )
        op.create_index(f"ix_{table}_folder", table, ["folder"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_folder", table_name=table)
        op.drop_column(table, "folder")
