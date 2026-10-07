"""VOC 게시판 — `voc_items` · `voc_events` · `voc_attachments`.

MatNexus 의 VOC 게시판과 같은 형태다(번호 · 상태 · 이력 · 첨부). 건은 지워도 행이 남는다
(`deleted_at`). 행은 넣지 않는다 — 비어서 시작한다.

Revision ID: 0035_voc
Revises: 0034_specimen_presets
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_voc"
down_revision = "0034_specimen_presets"
branch_labels = None
depends_on = None


def _user(name: str) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


def upgrade() -> None:
    op.create_table(
        "voc_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.Integer(), sa.Identity(), nullable=False, unique=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("page_path", sa.String(length=300), nullable=True),
        _user("created_by_id"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "status_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        _user("status_by_id"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voc_items_status", "voc_items", ["status"])
    op.create_index("ix_voc_items_created_at", "voc_items", ["created_at"])
    op.create_index("ix_voc_items_deleted_at", "voc_items", ["deleted_at"])

    op.create_table(
        "voc_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voc_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _user("by_id"),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_voc_events_item_id", "voc_events", ["item_id"])
    op.create_index("ix_voc_events_at", "voc_events", ["at"])

    op.create_table(
        "voc_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voc_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        _user("created_by_id"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_voc_attachments_item_id", "voc_attachments", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_voc_attachments_item_id", table_name="voc_attachments")
    op.drop_table("voc_attachments")
    op.drop_index("ix_voc_events_at", table_name="voc_events")
    op.drop_index("ix_voc_events_item_id", table_name="voc_events")
    op.drop_table("voc_events")
    op.drop_index("ix_voc_items_deleted_at", table_name="voc_items")
    op.drop_index("ix_voc_items_created_at", table_name="voc_items")
    op.drop_index("ix_voc_items_status", table_name="voc_items")
    op.drop_table("voc_items")
