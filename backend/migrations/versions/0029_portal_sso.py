"""HWAX 포털 SSO — 사내 SSO 의 바뀌지 않는 키(`users.sso_login_id`)와 1회용 launch 토큰 기록
(`sso_used_jti`).

포털 로그인(jwt-handoff)은 90초짜리 launch 토큰을 한 번만 받는다 — 워커가 여럿이라 재생은 DB 에서
막는다. 있는 계정은 그대로이고, 포털로 처음 들어올 때 이메일로 이어진다(그때 LoginId 를 새긴다).

Revision ID: 0029_portal_sso
Revises: 0028_search_trgm
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_portal_sso"
down_revision = "0028_search_trgm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sso_login_id", sa.String(128), nullable=True))
    op.create_index(op.f("ix_users_sso_login_id"), "users", ["sso_login_id"], unique=True)
    op.create_table(
        "sso_used_jti",
        sa.Column("jti", sa.String(128), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_sso_used_jti_expires_at"), "sso_used_jti", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sso_used_jti_expires_at"), table_name="sso_used_jti")
    op.drop_table("sso_used_jti")
    op.drop_index(op.f("ix_users_sso_login_id"), table_name="users")
    op.drop_column("users", "sso_login_id")
