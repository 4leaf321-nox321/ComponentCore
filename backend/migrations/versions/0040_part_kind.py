"""공용 조립 — 부품 카탈로그에 `kind`(part · assembly).

조립을 공용 공간에 올린다. 버전 · 내 작업 공간으로 복사 · 태그 · 폴더 · STEP 이 부품과 똑같아
카탈로그를 한 벌 더 만들지 않고 부품 표에 종류를 단다. 부품 목록은 기본이 `part` 다(지그 생성기 ·
제품 시험이 고르는 「부품」 에 조립이 섞이지 않게).

Revision ID: 0040_part_kind
Revises: 0039_notices
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0040_part_kind"
down_revision: Union[str, None] = "0039_notices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parts", sa.Column("kind", sa.String(10), nullable=False, server_default="part")
    )
    op.create_index("ix_parts_kind", "parts", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_parts_kind", table_name="parts")
    op.drop_column("parts", "kind")
