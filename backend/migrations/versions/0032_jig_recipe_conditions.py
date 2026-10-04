"""공용 지그에 레시피 · 해석 조건 — `jig_versions.recipe` · `jig_versions.conditions`.

지그 카탈로그는 레시피를 들지 않았다(원본 작업 버전이 든다). 그래서 남의 지그를 「내 작업
공간으로 복사」 해 고치거나 그 지그로 DOE 를 돌릴 길이 없었다 — 부품에는 있는데. 등록할 때
레시피와 해석 조건을 **스냅샷**으로 싣는다(작업이 지워져도 남고, 작업의 조건은 제자리에서 바뀌므로).

이미 등록된 버전의 레시피는 그 버전을 평가한 작업 버전(같은 `job_id`)에서 채운다 — 지그의 STEP 이
이미 공개라 새로 드러나는 것이 없다. 해석 조건은 비워 둔다(공개한다고 고른 적이 없다). 생성기로
만든 옛 버전은 짝이 되는 작업 버전이 없어 레시피가 빈 채로 남는다(복사할 수 없다고 말한다).

Revision ID: 0032_jig_recipe_conditions
Revises: 0031_doe_clone
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_jig_recipe_conditions"
down_revision = "0031_doe_clone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jig_versions",
        sa.Column("recipe", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "jig_versions",
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        """
        UPDATE jig_versions AS jv
           SET recipe = wv.recipe
          FROM work_versions AS wv
         WHERE wv.job_id = jv.job_id
           AND jv.recipe IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("jig_versions", "conditions")
    op.drop_column("jig_versions", "recipe")
