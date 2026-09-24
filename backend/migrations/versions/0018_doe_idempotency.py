"""두 번 불러도 한 벌 — 멱등 열쇠.

기계는 재시도한다. 망이 끊겨 답을 못 받았을 뿐인데 다시 걸면 **스터디 둘 · 폴더 둘**이 생기고,
해석 쪽은 어느 것이 진짜인지 모른다. 열쇠가 같으면 **이미 있는 것을 돌려준다.**

열쇠는 **사람마다** 유일하다(`owner_id` 와 함께) — 남이 쓴 열쇠 때문에 내 요청이 남의 스터디를
받아 오면 그것이야말로 사고다. 빈 열쇠는 「멱등하지 않다」 는 뜻이라 유일성에서 뺀다(부분
인덱스) — 사람은 열쇠 없이 부르고, 같은 설정으로 한 벌 더 만드는 것은 정상이다.

Revision ID: 0018_doe_idempotency
Revises: 0017_doe_point_file
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_doe_idempotency"
down_revision = "0017_doe_point_file"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doe_studies",
        sa.Column("idempotency_key", sa.Text(), nullable=False, server_default=""),
    )
    # 빈 열쇠는 뺀다 — 열쇠 없이 부른 것끼리는 겹쳐도 된다.
    op.create_index(
        "ux_doe_studies_owner_idempotency",
        "doe_studies",
        ["owner_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key <> ''"),
    )


def downgrade() -> None:
    op.drop_index("ux_doe_studies_owner_idempotency", table_name="doe_studies")
    op.drop_column("doe_studies", "idempotency_key")
