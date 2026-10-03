"""작업 취소와 워커 상태.

- `jobs.cancel_requested_at` — 도는 작업에 **취소를 요청한** 때. 워커는 단계마다 이것을 보고
  멈춘다(돌던 계산을 칼로 자르지 않는다 — 파일이 반쯤 쓰인 채 남는다). 대기 중이면 바로
  `cancelled` 가 되므로 이 칸이 필요 없다.
- `workers` — 워커마다 한 줄. **살아 있다는 신호**(`last_seen_at`)와 지금 하는 일. 서버 화면이
  「워커가 살아 있나 · 무엇을 하나 · 줄이 얼마나 길까」 를 여기서 본다. 신호가 끊긴 워커가 잡은
  작업은 30분을 기다리지 않고 되살린다.

Revision ID: 0026_job_cancel_workers
Revises: 0025_doe_plan
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0026_job_cancel_workers"
down_revision = "0025_doe_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "workers",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("hostname", sa.String(120), nullable=False, server_default=""),
        sa.Column("pid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.String(40), nullable=False, server_default=""),
        sa.Column("state", sa.String(20), nullable=False, server_default="idle"),
        sa.Column(
            "current_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_workers_last_seen_at", "workers", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_workers_last_seen_at", table_name="workers")
    op.drop_table("workers")
    op.drop_column("jobs", "cancel_requested_at")
