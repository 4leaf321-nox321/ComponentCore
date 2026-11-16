"""공지 — MatNexus 와 같은 게시판, 버전마다 업데이트 안내가 배포에 실려 온다(씨앗).

`notices`(제목 · 본문 · 발행 · 팝업 · 쓴 사람 · 씨앗 키), `notice_reads`(누가 읽었나 — 팝업을 한
번만 띄운다), `notice_seed_keys`(넣은 적이 있는 씨앗 키 — 공지를 지워도 남는다, 지운 초안이 다음
배포에 되살아나지 않게).

Revision ID: 0039_notices
Revises: 0038_template_tags_in_ontology
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0039_notices"
down_revision: Union[str, None] = "0038_template_tags_in_ontology"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_popup", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seed_key", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_notices_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notices")),
        sa.UniqueConstraint("seed_key", name=op.f("uq_notices_seed_key")),
    )
    op.create_index(op.f("ix_notices_created_at"), "notices", ["created_at"], unique=False)
    op.create_table(
        "notice_reads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["notice_id"],
            ["notices.id"],
            name=op.f("fk_notice_reads_notice_id_notices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notice_reads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notice_reads")),
        sa.UniqueConstraint("notice_id", "user_id", name="uq_notice_reads_pair"),
    )
    op.create_index(
        op.f("ix_notice_reads_notice_id"), "notice_reads", ["notice_id"], unique=False
    )
    op.create_index(op.f("ix_notice_reads_user_id"), "notice_reads", ["user_id"], unique=False)
    op.create_table(
        "notice_seed_keys",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_notice_seed_keys")),
    )


def downgrade() -> None:
    op.drop_table("notice_seed_keys")
    op.drop_index(op.f("ix_notice_reads_user_id"), table_name="notice_reads")
    op.drop_index(op.f("ix_notice_reads_notice_id"), table_name="notice_reads")
    op.drop_table("notice_reads")
    op.drop_index(op.f("ix_notices_created_at"), table_name="notices")
    op.drop_table("notices")
