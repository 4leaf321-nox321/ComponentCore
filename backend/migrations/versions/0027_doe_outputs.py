"""DOE 가 설계점마다 **더 내보낼 것** — 지금은 중간면(`midsurface`).

얇은 판을 셸 요소로 해석하는 쪽은 입체 STEP 이 아니라 두께 가운데의 면을 받는다. 고르면 점마다
`<형상>_mid.step` 이 형상 STEP 곁에 생기고, 점 파일 · `manifest.csv` 가 그것을 가리킨다.

있는 스터디는 빈 목록 — 예전과 같이 돈다.

Revision ID: 0027_doe_outputs
Revises: 0026_job_cancel_workers
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0027_doe_outputs"
down_revision = "0026_job_cancel_workers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doe_studies",
        sa.Column("outputs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("doe_studies", "outputs")
