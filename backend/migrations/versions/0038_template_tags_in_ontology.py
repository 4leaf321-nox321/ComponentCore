"""템플릿 태그도 온톨로지로 — 글자 꼬리표를 「일반 태그」 객체와 선으로 옮기고 `tags` 칸을 지운다
(ADR 0011, 0037 의 뒤를 잇는다).

1. 템플릿을 비추는 시스템 타입(관리자가 만든 것이 있으면 그것, 없으면 `cc_template`)과, 태그 관계
   (`cc_tagged`)의 출발 타입에 그것을 더한다.
2. 옛 꼬리표 — 이름마다 「일반 태그」 의 전역 객체 하나(이미 있으면 그것, 대소문자 무시), 템플릿마다
   붙어 있던 순서대로 선 하나.
3. `recipe_templates.tags` 와 그 트라이그램 색인을 지운다.

되돌리기는 칸을 되살리고 선에서 이름을 다시 채운다(객체 · 선은 남긴다).

Revision ID: 0038_template_tags_in_ontology
Revises: 0037_tags_in_ontology
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0038_template_tags_in_ontology"
down_revision: Union[str, None] = "0037_tags_in_ontology"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    source = bind.execute(
        sa.text(
            "SELECT slug FROM object_types WHERE kind_class = 'system' "
            "AND system_source = 'template' ORDER BY is_active DESC, sort_order, slug LIMIT 1"
        )
    ).scalar()
    if source is None:
        bind.execute(
            sa.text(
                "INSERT INTO object_types (id, slug, label, kind_class, system_source, "
                "description) VALUES (gen_random_uuid(), 'cc_template', 'CompCore 템플릿', "
                "'system', 'template', :d)"
            ),
            {"d": "CompCore 의 템플릿 — 원 표를 비춘다(행을 복제하지 않는다)."},
        )
        source = "cc_template"
    relation = bind.execute(
        sa.text("SELECT src_type_slugs FROM relation_types WHERE slug = 'cc_tagged'")
    ).first()
    if relation is not None and relation[0] is not None and source not in relation[0]:
        bind.execute(
            sa.text(
                "UPDATE relation_types SET src_type_slugs = CAST(:src AS jsonb) "
                "WHERE slug = 'cc_tagged'"
            ),
            {"src": json.dumps(sorted({*relation[0], source}), ensure_ascii=False)},
        )
    tag_type = bind.execute(
        sa.text("SELECT id FROM object_types WHERE slug = 'cc_tag'")
    ).scalar()
    if tag_type is not None:
        bind.execute(
            sa.text(
                """
                INSERT INTO objects (id, type_id, label)
                SELECT gen_random_uuid(), :t, MIN(name)
                FROM (
                    SELECT DISTINCT left(btrim(regexp_replace(one, '\\s+', ' ', 'g')), 80) AS name
                    FROM recipe_templates, jsonb_array_elements_text(recipe_templates.tags) AS one
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
        bind.execute(
            sa.text(
                """
                INSERT INTO object_links (id, src_type, src_id, dst_type, dst_id, relation,
                                          created_by_id, created_at)
                SELECT gen_random_uuid(), :src, r.id, 'cc_tag', o.id, 'cc_tagged', r.owner_id,
                       now() + (tag.n * interval '1 millisecond')
                FROM recipe_templates r,
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
            {"src": source, "t": tag_type},
        )
    op.drop_index("ix_recipe_templates_tags_trgm", table_name="recipe_templates")
    op.drop_column("recipe_templates", "tags")


def downgrade() -> None:
    op.add_column(
        "recipe_templates",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.get_bind().execute(
        sa.text(
            """
            UPDATE recipe_templates r SET tags = found.names
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
        "ix_recipe_templates_tags_trgm",
        "recipe_templates",
        [sa.text("(tags::text) gin_trgm_ops")],
        postgresql_using="gin",
    )
