"""찾기 — `pg_trgm` 과 GIN 색인(이름 · 설명 · 꼬리표).

찾기 규칙을 한 곳(`shared/search.py`)으로 모으면서, 그 `ILIKE '%낱말%'` 이 색인을 타게 한다.
보통의 색인은 앞이 열린 무늬를 못 타지만 트라이그램 색인은 탄다 — 한글도 글자 단위라
상관없다. 지금 줄 수에서 속도가 문제는 아니다. 규칙을 모으는 김에 넣는다.

`pg_trgm` 은 신뢰 확장이라 DB 의 주인이 만들 수 있다 — `deploy.sh` 는 DB 를 앱 계정 소유로
만들므로 보통은 여기서 확장과 색인이 함께 생긴다. 확장을 만들 권한이 없는 DB(`CREATE` 권한
없음)나 꾸러미가 없는 서버라면 **색인 없이 지나간다** — 찾기 답은 같고 느릴 뿐이다(그때
`alembic check` 가 모델과의 차이를 말한다). 이 판은 이미 올린 것으로 적히므로 `upgrade head`
만으로는 다시 돌지 않는다 — 관리자가 `CREATE EXTENSION pg_trgm` 을 한 뒤 `alembic downgrade
0027_doe_outputs` → `alembic upgrade head` 로 다시 올린다(내리기는 색인을 `IF EXISTS` 로 지운다).

Revision ID: 0028_search_trgm
Revises: 0027_doe_outputs
"""

from __future__ import annotations

import warnings

import sqlalchemy as sa
from alembic import op

revision = "0028_search_trgm"
down_revision = "0027_doe_outputs"
branch_labels = None
depends_on = None

#: 표 → 꼬리표 칸이 있나. 이름 · 설명은 다섯 표 모두에 있다.
TABLES = {
    "works": True,
    "parts": True,
    "jigs": True,
    "recipe_templates": True,
    "doe_studies": False,
}


def _names(table: str, has_tags: bool) -> list[str]:
    out = [f"ix_{table}_name_trgm", f"ix_{table}_description_trgm"]
    if has_tags:
        out.append(f"ix_{table}_tags_trgm")
    return out


def upgrade() -> None:
    bind = op.get_bind()
    installed = bind.execute(
        sa.text("select 1 from pg_extension where extname = 'pg_trgm'")
    ).scalar()
    if not installed:
        allowed = bind.execute(
            sa.text(
                "select has_database_privilege(current_user, current_database(), 'CREATE')"
            )
        ).scalar()
        available = bind.execute(
            sa.text("select 1 from pg_available_extensions where name = 'pg_trgm'")
        ).scalar()
        if not (allowed and available):
            warnings.warn(
                "pg_trgm 을 만들 수 없어 찾기 색인을 건너뜁니다 — 찾기 답은 같고 느릴 뿐입니다. "
                "관리자가 `CREATE EXTENSION pg_trgm` 을 한 뒤 `alembic downgrade 0027_doe_outputs`"
                " → `alembic upgrade head` 로 이 판을 다시 올리면 색인이 생깁니다.",
                stacklevel=1,
            )
            return
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for table, has_tags in TABLES.items():
        for column in ("name", "description"):
            op.create_index(
                f"ix_{table}_{column}_trgm",
                table,
                [column],
                postgresql_using="gin",
                postgresql_ops={column: "gin_trgm_ops"},
            )
        if has_tags:
            op.create_index(
                f"ix_{table}_tags_trgm",
                table,
                [sa.text("(tags::text) gin_trgm_ops")],
                postgresql_using="gin",
            )


def downgrade() -> None:
    for table, has_tags in TABLES.items():
        for name in _names(table, has_tags):
            op.execute(f"DROP INDEX IF EXISTS {name}")
    # 확장은 둔다 — 다른 것이 쓰고 있을 수 있다.
