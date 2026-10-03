"""DOE 의 계획을 더 적는다 — 제약식 · 형상 점검 기준 · 측정값 · 점 더하기 이력.

- `constraints`: 변수끼리의 조건(`간격 > 2 * 지름`). 만들기 전에 어긋난 조합을 거른다.
- `checks`: 형상 점검 기준(최소 벽 두께 · 짧은 모서리 · 좁은 면, mm). 비면 기본값.
- `measures`: 점마다 잴 값(부피 · 크기 · 영역 넓이 · 거리 · 식). 표에 열로 붙는다.
- `batches`: 만든 뒤 **더한** 설계점 묶음의 이력(방식 · 시드 · 범위 · 번호 구간). 첫 묶음은
  스터디 칸(`method` · `samples` · `seed` · `factors`)이 그대로 말한다.

있는 스터디는 모두 빈 값 — 예전과 같이 돈다.

Revision ID: 0025_doe_plan
Revises: 0024_catalog_folders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0025_doe_plan"
down_revision = "0024_catalog_folders"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("constraints", "[]"),
    ("checks", "{}"),
    ("measures", "[]"),
    ("batches", "[]"),
)


def upgrade() -> None:
    for name, empty in _COLUMNS:
        op.add_column(
            "doe_studies",
            sa.Column(name, JSONB(), nullable=False, server_default=empty),
        )


def downgrade() -> None:
    for name, _ in _COLUMNS:
        op.drop_column("doe_studies", name)
