"""태그를 온톨로지로 — 글자 꼬리표를 「일반 태그」 객체와 선으로 옮기고 `tags` 칸을 지운다(ADR 0011).

1. `tag_types` — 태그로 쓰는 타입(관리자가 고른다).
2. 기본 정의 — 작업 · 부품 · 지그를 비추는 시스템 타입(관리자가 만든 것이 있으면 그것), 「일반
   태그」(`cc_tag`, 늘리기), 태그 관계(`cc_tagged`, 작업 · 부품 · 지그 → 아무 타입).
3. 옛 꼬리표 — 이름마다 「일반 태그」 의 전역 객체 하나(같은 이름은 대소문자 없이 하나), 행마다
   붙어 있던 순서대로 선 하나.
4. `works` · `parts` · `jigs` 의 `tags` 칸과 그 트라이그램 색인을 지운다 — 정본은 선 하나다.

앱은 같은 기본 정의를 처음 쓸 때도 만든다(`tagging.services.ensure`, 시험 · 새 설치). 여기 SQL 은
그때의 모양을 값으로 박아 둔 것이다.

되돌리기는 칸을 되살리고 선에서 이름을 다시 채운다. 객체 · 선은 남긴다 — 다시 올리면 같은 것을
찾아 쓴다(겹치지 않는다).

Revision ID: 0037_tags_in_ontology
Revises: 0036_sp_platform
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0037_tags_in_ontology"
down_revision: Union[str, None] = "0036_sp_platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: (원 표 키, 표, 없을 때 만드는 slug, 이름, 부르는 말)
TARGETS = (
    ("work", "works", "cc_work", "CompCore 작업", "작업"),
    ("part", "parts", "cc_part", "CompCore 부품", "부품"),
    ("jig", "jigs", "cc_jig", "CompCore 지그", "지그"),
)


def _system_slug(bind: sa.Connection, source: str) -> str | None:
    return bind.execute(
        sa.text(
            "SELECT slug FROM object_types WHERE kind_class = 'system' AND system_source = :s "
            "ORDER BY is_active DESC, sort_order, slug LIMIT 1"
        ),
        {"s": source},
    ).scalar()


def upgrade() -> None:
    op.create_table(
        "tag_types",
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(length=10), server_default="pick", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["type_id"], ["object_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("type_id"),
    )
    bind = op.get_bind()

    # --- 기본 정의 ---
    sources: dict[str, str] = {}
    for key, _table, slug, label, noun in TARGETS:
        found = _system_slug(bind, key)
        if found is None:
            bind.execute(
                sa.text(
                    "INSERT INTO object_types (id, slug, label, kind_class, system_source, "
                    "description) VALUES (gen_random_uuid(), :slug, :label, 'system', :key, :d)"
                ),
                {
                    "slug": slug,
                    "label": label,
                    "key": key,
                    "d": f"CompCore 의 {noun} — 원 표를 비춘다(행을 복제하지 않는다).",
                },
            )
            found = slug
        sources[key] = found
    bind.execute(
        sa.text(
            "INSERT INTO object_types (id, slug, label, icon, kind_class, description) "
            "VALUES (gen_random_uuid(), 'cc_tag', '일반 태그', 'tag', 'reference', :d) "
            "ON CONFLICT (slug) DO NOTHING"
        ),
        {"d": "타입을 고르지 않고 붙인 태그 — 붙이는 사람 누구나 늘린다."},
    )
    tag_type = bind.execute(
        sa.text("SELECT id FROM object_types WHERE slug = 'cc_tag'")
    ).scalar()
    bind.execute(
        sa.text("INSERT INTO tag_types (type_id, mode) VALUES (:t, 'grow')"), {"t": tag_type}
    )
    wanted = sorted(set(sources.values()))
    relation = bind.execute(
        sa.text("SELECT src_type_slugs FROM relation_types WHERE slug = 'cc_tagged'")
    ).first()
    if relation is None:
        bind.execute(
            sa.text(
                "INSERT INTO relation_types (id, slug, label, inverse_label, description, "
                "cardinality, src_type_slugs, dst_type_slugs) VALUES (gen_random_uuid(), "
                "'cc_tagged', '태그', '태그가 붙은 것', :d, 'many_to_many', "
                "CAST(:src AS jsonb), NULL)"
            ),
            {
                "d": "작업 · 부품 · 지그에 붙인 태그(ADR 0011). 상대 타입은 정하지 않는다 — 어느 "
                "타입이 태그인지는 관리 › 온톨로지 › 태그가 정한다.",
                "src": _json(wanted),
            },
        )
    elif relation[0] is not None:
        bind.execute(
            sa.text(
                "UPDATE relation_types SET src_type_slugs = CAST(:src AS jsonb) "
                "WHERE slug = 'cc_tagged'"
            ),
            {"src": _json(sorted({*relation[0], *wanted}))},
        )

    # --- 옛 꼬리표 → 「일반 태그」 객체 · 선 ---
    for key, table, _slug, _label, _noun in TARGETS:
        # 이름마다 전역 객체 하나 — 이미 있으면(대소문자 무시) 그것.
        bind.execute(
            sa.text(
                f"""
                INSERT INTO objects (id, type_id, label)
                SELECT gen_random_uuid(), :t, MIN(name)
                FROM (
                    SELECT DISTINCT left(btrim(regexp_replace(one, '\\s+', ' ', 'g')), 80) AS name
                    FROM {table}, jsonb_array_elements_text({table}.tags) AS one
                ) AS names
                WHERE name <> '' AND NOT EXISTS (
                    SELECT 1 FROM objects o
                    WHERE o.type_id = :t AND o.owner_workspace_id IS NULL
                      AND o.deleted_at IS NULL AND lower(o.label) = lower(names.name)
                )
                GROUP BY lower(name)
                """
            ),
            {"t": tag_type},
        )
        # 행마다 붙어 있던 순서대로 — 시각을 한 칸씩 늦춰 순서를 남긴다.
        bind.execute(
            sa.text(
                f"""
                INSERT INTO object_links (id, src_type, src_id, dst_type, dst_id, relation,
                                          created_by_id, created_at)
                SELECT gen_random_uuid(), :src, r.id, 'cc_tag', o.id, 'cc_tagged', r.owner_id,
                       now() + (tag.n * interval '1 millisecond')
                FROM {table} r,
                     jsonb_array_elements_text(r.tags) WITH ORDINALITY AS tag(one, n),
                     LATERAL (
                         SELECT id FROM objects o
                         WHERE o.type_id = :t AND o.owner_workspace_id IS NULL
                           AND o.deleted_at IS NULL
                           AND lower(o.label) = lower(
                               left(btrim(regexp_replace(tag.one, '\\s+', ' ', 'g')), 80))
                         ORDER BY o.created_at LIMIT 1
                     ) AS o
                ON CONFLICT ON CONSTRAINT uq_object_links_edge DO NOTHING
                """
            ),
            {"src": sources[key], "t": tag_type},
        )
        op.drop_index(f"ix_{table}_tags_trgm", table_name=table)
        op.drop_column(table, "tags")


def _json(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def downgrade() -> None:
    bind = op.get_bind()
    for _key, table, _slug, _label, _noun in TARGETS:
        op.add_column(
            table,
            sa.Column(
                "tags",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default="[]",
                nullable=False,
            ),
        )
        bind.execute(
            sa.text(
                f"""
                UPDATE {table} r SET tags = found.names
                FROM (
                    SELECT l.src_id, jsonb_agg(o.label ORDER BY l.created_at) AS names
                    FROM object_links l JOIN objects o ON o.id = l.dst_id
                    WHERE l.relation = 'cc_tagged' AND o.deleted_at IS NULL
                      AND o.owner_workspace_id IS NULL
                    GROUP BY l.src_id
                ) AS found
                WHERE found.src_id = r.id
                """
            )
        )
        op.create_index(
            f"ix_{table}_tags_trgm",
            table,
            [sa.text("(tags::text) gin_trgm_ops")],
            postgresql_using="gin",
        )
    op.drop_table("tag_types")
