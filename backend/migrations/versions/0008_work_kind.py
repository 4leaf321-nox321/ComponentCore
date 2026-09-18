"""작업의 종류(부품 · 지그) — 그리는 방법은 같고 올라갈 곳이 다르다.

Revision ID: 0008_work_kind
Revises: 0007_doe
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0008_work_kind"
down_revision = "0007_doe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "works", sa.Column("kind", sa.String(10), nullable=False, server_default="part")
    )
    op.create_index("ix_works_kind", "works", ["kind"])
    op.add_column("works", sa.Column("jig_for_part_id", PgUUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_works_jig_for_part",
        "works",
        "parts",
        ["jig_for_part_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_works_jig_for_part", "works", type_="foreignkey")
    op.drop_column("works", "jig_for_part_id")
    op.drop_index("ix_works_kind", table_name="works")
    op.drop_column("works", "kind")
