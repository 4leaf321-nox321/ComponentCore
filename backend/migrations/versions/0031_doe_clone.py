"""DOE 「내 것으로 복제」 — 어느 DOE 에서 왔나(`doe_studies.cloned_from_id`).

공개된 DOE 를 다른 사람이 이어서 할 때, 원본은 그대로 두고 같은 설계점 · 조건으로 자기 소유의
새 DOE 를 만든다. 결과를 견줄 때 「이 표는 어느 DOE 의 것과 같은 점인가」 를 되짚게 원본을
가리킨다. 원본이 지워지면 비운다 — 복제본은 스냅샷이라 혼자 선다.

Revision ID: 0031_doe_clone
Revises: 0030_part_conditions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_doe_clone"
down_revision = "0030_part_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doe_studies",
        sa.Column("cloned_from_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_doe_studies_cloned_from_id_doe_studies"),
        "doe_studies",
        "doe_studies",
        ["cloned_from_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_doe_studies_cloned_from_id_doe_studies"), "doe_studies", type_="foreignkey"
    )
    op.drop_column("doe_studies", "cloned_from_id")
