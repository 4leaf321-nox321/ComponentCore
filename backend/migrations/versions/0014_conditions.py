"""해석 조건 — 작업 버전에 붙고, 실험계획이 스냅샷을 뜬다.

조건은 **형상의 성질**이다(「이 지그는 바닥으로 시험대에 앉는다」) — 어떻게 훑든 변하지
않으므로 버전에 붙인다. 실험계획은 레시피를 스냅샷 뜨듯 조건도 떠서, 나중에 작업이 바뀌어도
그 DOE 가 무엇으로 돌았는지 남는다.

Revision ID: 0014_conditions
Revises: 0013_drop_doe_metrics
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014_conditions"
down_revision = "0013_drop_doe_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_versions",
        sa.Column("conditions", JSONB, nullable=False, server_default="{}"),
    )
    op.add_column(
        "doe_studies",
        sa.Column("conditions", JSONB, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("doe_studies", "conditions")
    op.drop_column("work_versions", "conditions")
