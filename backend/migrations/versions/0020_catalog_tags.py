"""공용 카탈로그에도 꼬리표 — **승격할 때 잃던 것을 되찾는다.**

`works.tags` 는 있었는데 승격이 그것을 안 옮겼고, 받을 칸도 없었다. 사람이 「브래킷 · EMC ·
2026」 이라고 붙여 둔 것이 **공용 공간으로 나가는 순간 없어졌다** — 정작 남이 찾아야 하는
자리에서. 내 작업은 열두 개쯤이라 이름만 봐도 찾지만, 공용 카탈로그는 남의 것까지 쌓인다.

**있던 줄은 원본 작업에서 채운다.** `parts.work_id` · `jigs.work_id` 가 살아 있으므로 지금은
되살릴 수 있다 — 늦을수록 못 살리는 것이 는다(작업을 지운 것은 이미 못 살린다).

템플릿에는 `work_id` 가 없다(작업에서 오지만 그 연결을 안 남긴다). 칸만 만들고 채우지
않는다 — 앞으로 저장하는 것부터 붙는다.

Revision ID: 0020_catalog_tags
Revises: 0019_doe_visibility
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_catalog_tags"
down_revision = "0019_doe_visibility"
branch_labels = None
depends_on = None

_TABLES = ("parts", "jigs", "recipe_templates")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "tags",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default="[]",
            ),
        )
    # **원본에서 되찾는다.** 작업이 아직 있고 꼬리표가 붙어 있는 것만.
    for table in ("parts", "jigs"):
        op.execute(
            sa.text(
                f"UPDATE {table} SET tags = w.tags "
                f"FROM works w WHERE {table}.work_id = w.id "
                "AND w.tags IS NOT NULL AND jsonb_array_length(w.tags) > 0"
            )
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "tags")
