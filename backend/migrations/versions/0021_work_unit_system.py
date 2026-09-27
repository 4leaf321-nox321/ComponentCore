"""작업마다 **기본 단위계** — 새 시뮬레이션 조건이 이 계로 시작한다.

단위계는 조건 한 벌마다 고르는데(`conditions.units.system`), 새 조건은 늘 mm · N · tonne 으로
시작했다. SI 로 일하는 사람은 조건을 만들 때마다 바꿔야 했고, 잊으면 그 조건만 다른 계가 된다.
있는 작업은 모두 지금까지의 기본(`mm_n_tonne`)으로 채운다 — 있는 조건의 계는 건드리지 않는다.

Revision ID: 0021_work_unit_system
Revises: 0020_catalog_tags
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_work_unit_system"
down_revision = "0020_catalog_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "works",
        sa.Column("unit_system", sa.String(20), nullable=False, server_default="mm_n_tonne"),
    )


def downgrade() -> None:
    op.drop_column("works", "unit_system")
