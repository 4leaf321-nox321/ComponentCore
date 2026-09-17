"""초기 스키마 — 계정 · 토큰 · 접근 로그 · 지그 프로젝트 · 실행.

**행은 여기서 안 심는다.** 첫 관리자 계정은 설치 시드가 만든다(`scripts/seed_install.py`).

Revision ID: 0001_initial
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _pk() -> sa.Column:
    return sa.Column("id", PgUUID(as_uuid=True), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("is_system_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    op.create_table(
        "refresh_tokens",
        _pk(),
        sa.Column("user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_replaced_by_id_refresh_tokens",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index(
        "ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True
    )

    op.create_table(
        "access_logs",
        _pk(),
        sa.Column("user_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(40), nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_access_logs_user_id_users", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_access_logs_user_id", "access_logs", ["user_id"])
    op.create_index("ix_access_logs_action", "access_logs", ["action"])
    op.create_index("ix_access_logs_created_at", "access_logs", ["created_at"])

    op.create_table(
        "jig_projects",
        _pk(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("product_filename", sa.String(255), nullable=True),
        sa.Column("product_path", sa.String(500), nullable=True),
        sa.Column("product_size_bytes", sa.Integer(), nullable=True),
        sa.Column("product_spec", JSONB(), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_jig_projects_owner_id_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_jig_projects_owner_id", "jig_projects", ["owner_id"])
    op.create_index("ix_jig_projects_deleted_at", "jig_projects", ["deleted_at"])

    op.create_table(
        "jig_runs",
        _pk(),
        sa.Column("project_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("options", JSONB(), nullable=False, server_default="{}"),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_dir", sa.String(500), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["jig_projects.id"],
            name="fk_jig_runs_project_id_jig_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name="fk_jig_runs_requested_by_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_jig_runs_project_id", "jig_runs", ["project_id"])


def downgrade() -> None:
    op.drop_table("jig_runs")
    op.drop_table("jig_projects")
    op.drop_table("access_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
