"""작업마다 **폴더** — 「내 작업」 을 폴더 · 하위 폴더로 나눠 둔다.

꼬리표(여러 묶음)와 따로, 작업이 놓이는 **한 곳**이다. 경로 문자열(`고객A/2026/검사지그`)로
들고 폴더 표는 따로 두지 않는다 — 폴더는 그 안에 작업이 있을 때 있다. 있는 작업은 맨 위
(빈 경로)에 둔다.

Revision ID: 0023_work_folder
Revises: 0022_conditions_input_mm
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_work_folder"
down_revision = "0022_conditions_input_mm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "works", sa.Column("folder", sa.String(255), nullable=False, server_default="")
    )
    op.create_index("ix_works_folder", "works", ["folder"])


def downgrade() -> None:
    op.drop_index("ix_works_folder", table_name="works")
    op.drop_column("works", "folder")
