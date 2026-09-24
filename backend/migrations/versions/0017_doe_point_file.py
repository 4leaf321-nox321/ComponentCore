"""설계점의 파일 둘을 하나로 — `pNNNN.topology.json` + `pNNNN.conditions.json` → `pNNNN.json`.

영역(어디가 어디인가)과 조건(무엇을 할 것인가)은 **늘 짝으로 읽힌다.** 나눠 두면 「하나는 있고
하나는 없는」 상태가 생길 자리만 늘고, 설계점 200개면 파일이 600개에서 400개로 줄지 않는다.
받는 쪽(SimEngBay)이 아직 읽는 코드를 만들기 전이라 지금이 바꿀 적기다.

Revision ID: 0017_doe_point_file
Revises: 0016_doe_retention
"""

from __future__ import annotations

from alembic import op

revision = "0017_doe_point_file"
down_revision = "0016_doe_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 옛 값(`points/pNNNN.topology.json`)은 그대로 둔다 — 다시 보내면 새 이름으로 덮인다.
    op.alter_column("doe_points", "topology_file", new_column_name="point_file")


def downgrade() -> None:
    op.alter_column("doe_points", "point_file", new_column_name="topology_file")
