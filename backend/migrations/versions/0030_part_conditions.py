"""공용 부품에 해석 조건 — `part_versions.conditions`.

부품으로 등록할 때 그 작업 버전의 해석 조건(경계 · 하중 · 접촉 · 물성 …)을 **스냅샷으로**
싣는다. 작업의 조건은 버전에 붙어 제자리에서 바뀌므로(`set_conditions`), 가리키지 않고 복사한다.
「내 작업으로 복사」 가 이것을 새 작업으로 옮긴다 — 같은 형상이라 선택 그룹이 그대로 맞는다.

이미 등록된 버전은 비워 둔다. 등록할 때 조건까지 공개한다고 고른 적이 없기 때문이다.

Revision ID: 0030_part_conditions
Revises: 0029_portal_sso
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_part_conditions"
down_revision = "0029_portal_sso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "part_versions",
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("part_versions", "conditions")
