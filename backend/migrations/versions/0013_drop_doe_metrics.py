"""설계점의 `metrics` 열을 뺀다 — 결과는 해석 플랫폼이 들고 거기서 본다.

해석 결과를 이쪽에 되돌려 쓰는 길을 만들지 않기로 했다(`docs/해석-조건-설계.md` 0장).
그러면 이 열은 **영원히 비어 있는 칸**이고, 남겨 두면 다음 사람이 「왜 늘 비어 있지」 를
묻는다. 지우는 것이 정직하다 — 되돌리려면 `downgrade` 가 같은 모양으로 다시 만든다.

Revision ID: 0013_drop_doe_metrics
Revises: 0012_doe_topology_file
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_drop_doe_metrics"
down_revision = "0012_doe_topology_file"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("doe_points", "metrics")


def downgrade() -> None:
    op.add_column("doe_points", sa.Column("metrics", JSONB, nullable=True))
