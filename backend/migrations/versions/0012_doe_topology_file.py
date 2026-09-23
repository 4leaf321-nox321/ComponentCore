"""설계점마다 영역 지문 파일 — STEP 은 이름표를 못 나른다.

해석이 「어느 면이 고정면인가」 를 물을 곳은 `points/pNNNN.topology.json` 뿐이다.
그 경로를 설계점 줄에 적어 둔다 — 폴더를 훑어 짐작하지 않게.

Revision ID: 0012_doe_topology_file
Revises: 0011_work_tags
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_doe_topology_file"
down_revision = "0011_work_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 옛 설계점은 빈 칸이다 — 그때는 이 파일을 안 썼다. 다시 만들면 채워진다.
    op.add_column(
        "doe_points",
        sa.Column("topology_file", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("doe_points", "topology_file")
