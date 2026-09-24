"""누가 만들었고 누가 보나 — 대행과 읽기 공개.

오케스트레이터(기계)가 PAT 으로 DOE 를 만들면 소유자가 **서비스 계정**이 된다. 지금처럼
개인 전용이면 정작 사람이 제 활동에서 못 찾고 403 을 받는다. 둘을 함께 푼다:

- `requested_by_id` — **실제로 부른 쪽**(서비스 계정). 소유자는 대행 대상인 사람이 된다.
  「만든 책임은 사람에게, 실행은 기계가」 를 폴더와 화면이 둘 다 말할 수 있어야 한다.
- `visibility` — **읽기는 모두에게**가 기본이다. DOE 는 이 조직의 설계 이력이고, 옆 사람이
  같은 훑기를 다시 도는 것이 더 큰 손해다. 쓰는 일(보내기 · 지우기 · 영구보관)은 그대로
  소유자와 관리자만 한다.

**있던 줄도 `read` 로 채운다.** 새것만 공개하면 정작 쌓여 있는 이력이 안 보여서, 이 변경이
누구에게도 도움이 안 된다. 감추고 싶은 것은 소유자가 하나씩 `private` 로 돌린다.

Revision ID: 0019_doe_visibility
Revises: 0018_doe_idempotency
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_doe_visibility"
down_revision = "0018_doe_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doe_studies",
        sa.Column(
            "requested_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "doe_studies",
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="read"),
    )


def downgrade() -> None:
    op.drop_column("doe_studies", "visibility")
    op.drop_column("doe_studies", "requested_by_id")
