"""StandardPlatform 의 온톨로지 · 객체와 그 기반 — 표 39 개와 `users.home_workspace_id`(ADR 0008).

부서 · 첨부 · 알림 · 감사 기록 · 요청 시간 · 데이터 작업(tasks) · 온톨로지 정의 · 객체 · 관계 · 별칭 ·
참조 색인 · 묶음 · 검토함 · 지표 · 데이터 소스 · 웹훅. 표는 모델에서 생성했고, 모델로 드러나지 않는
DB 객체(함수 · 트리거 · 통계)는 아래 SQL 로 건다 — SP 의 마이그레이션 0049 · 0054 · 0055 · 0061 ·
0062 · 0072 · 0075 가 하나씩 걸던 것을 한 번에. 행은 넣지 않는다 — 비어서 시작한다.

Revision ID: 0036_sp_platform
Revises: 0035_voc
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

#: 아래 SQL 은 StandardPlatform 6e5a773 의 모델 · 색인 모듈에 있는 것을 **값으로 박아 둔 것**이다 —
#: 마이그레이션은 그때의 모양을 지킨다(코드가 나중에 바뀌어도 이 파일은 그대로 돈다).
#: 시험은 같은 SQL 을 `create_all` 의 이벤트로 건다(`objects/models.py` · `refindex.attach` ·
#: `attachment_sync.attach` · `tasks/models.py`).
BIGRAMS_SQL = """
CREATE OR REPLACE FUNCTION sp_bigrams(t text) RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT coalesce(array_agg(DISTINCT substr(lower(t), i, 2)), '{}'::text[])
  FROM generate_series(1, char_length(t) - 1) AS i
$$
"""

DATE_SQL = """
CREATE OR REPLACE FUNCTION sp_date(raw text) RETURNS date
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
  d text := substr(translate(substr(raw, 1, 10), '-', ''), 1, 8);
  y int;
  m int;
  dd int;
BEGIN
  IF length(d) <> 8 OR translate(d, '0123456789', '') <> '' THEN
    RETURN NULL;
  END IF;
  y := substr(d, 1, 4)::int;
  m := substr(d, 5, 2)::int;
  dd := substr(d, 7, 2)::int;
  IF y < 1 OR m < 1 OR m > 12 OR dd < 1 OR dd > (
    CASE
      WHEN m = 2 THEN
        CASE WHEN (mod(y, 4) = 0 AND mod(y, 100) <> 0) OR mod(y, 400) = 0 THEN 29 ELSE 28 END
      WHEN m IN (4, 6, 9, 11) THEN 30
      ELSE 31
    END
  ) THEN
    RETURN NULL;
  END IF;
  RETURN make_date(y, m, dd);
END
$$
"""

BRIEF_SQL = """CREATE OR REPLACE FUNCTION sp_job_brief(r jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  out jsonb;
  k text;
  v jsonb;
  n jsonb;
BEGIN
  IF r IS NULL THEN
    RETURN NULL;
  END IF;
  IF jsonb_typeof(r) = 'object' THEN
    -- 줄 수는 jsonpath 로 센다 — `r -> 'rows'` 로 꺼내면 수십 MB 배열을 통째로 베낀다
    -- (50건에 0.24초 → 0.04초, 2026-10-09 실측). 줄 목록을 뺀 나머지만 훑는다.
    -- strict 라야 배열을 낱개로 풀지 않는다(lax 는 `rows` 의 줄마다 걸러 못 알아본다).
    n := jsonb_path_query_first(r, 'strict $.rows ? (@.type() == "array").size()', '{}', true);
    out := '{}'::jsonb;
    FOR k, v IN SELECT * FROM jsonb_each(CASE WHEN n IS NULL THEN r ELSE r - 'rows' END) LOOP
      out := out || jsonb_build_object(k, sp_job_brief(v));
    END LOOP;
    IF n IS NOT NULL THEN
      out := out || jsonb_build_object('rows', '[]'::jsonb, 'rows_omitted', n);
    END IF;
    RETURN out;
  END IF;
  -- 배열은 안에 객체가 있을 때만 들어간다(묶음의 `objects[].plan.rows`) — 글자 목록
  -- (`errors` 등)을 한 칸씩 부르면 그것만으로 느려진다.
  IF jsonb_typeof(r) = 'array' AND jsonb_typeof(r -> 0) IN ('object', 'array') THEN
    SELECT coalesce(jsonb_agg(sp_job_brief(e) ORDER BY i), '[]'::jsonb)
      INTO out FROM jsonb_array_elements(r) WITH ORDINALITY AS t(e, i);
    RETURN out;
  END IF;
  RETURN r;
END
$$;
"""

REFS_FUNCTIONS = """
CREATE OR REPLACE FUNCTION object_refs_inserted() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO object_refs (src_id, src_type_id, key, dst_id)
    
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM new_rows n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' 
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    
    ON CONFLICT DO NOTHING;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION object_refs_updated() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- 참조가 달라진 행의 달라진 줄만 — 비용 · 이름만 고친 갱신은 아무 줄도 안 건드린다.
    -- 큰 문장은 그때그때 계획한다(굳은 한 줄짜리 계획으로 5천 줄을 돌면 39초, 2026-10-10).
    IF (SELECT count(*) FROM new_rows) > 64 THEN
        EXECUTE $sql$
    WITH ch AS MATERIALIZED (
        SELECT n.id, n.type_id, n.deleted_at, n.properties,
               o.type_id AS old_type_id, o.deleted_at AS old_deleted_at,
               o.properties AS old_properties,
               (o.type_id IS DISTINCT FROM n.type_id
                OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL)) AS whole
          FROM new_rows n
          JOIN old_rows o ON o.id = n.id
          LEFT JOIN (SELECT owner_id, array_agg(key::text) AS keys FROM property_defs WHERE owner_kind = 'type' AND data_type = 'object_ref' GROUP BY owner_id) k ON k.owner_id = n.type_id
         WHERE o.type_id IS DISTINCT FROM n.type_id OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL) OR (o.properties IS DISTINCT FROM n.properties AND EXISTS (SELECT 1 FROM unnest(k.keys) AS r(key) WHERE (o.properties -> r.key) IS DISTINCT FROM (n.properties -> r.key)))
    )
    DELETE FROM object_refs r
     USING ((
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, old_type_id AS type_id, old_deleted_at AS deleted_at, old_properties AS properties, properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ) EXCEPT (
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, type_id, deleted_at, properties, old_properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ))
           AS g (src_id, src_type_id, key, dst_id)
     WHERE r.src_id = g.src_id AND r.key = g.key AND r.dst_id = g.dst_id
        $sql$;
        EXECUTE $sql$
    WITH ch AS MATERIALIZED (
        SELECT n.id, n.type_id, n.deleted_at, n.properties,
               o.type_id AS old_type_id, o.deleted_at AS old_deleted_at,
               o.properties AS old_properties,
               (o.type_id IS DISTINCT FROM n.type_id
                OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL)) AS whole
          FROM new_rows n
          JOIN old_rows o ON o.id = n.id
          LEFT JOIN (SELECT owner_id, array_agg(key::text) AS keys FROM property_defs WHERE owner_kind = 'type' AND data_type = 'object_ref' GROUP BY owner_id) k ON k.owner_id = n.type_id
         WHERE o.type_id IS DISTINCT FROM n.type_id OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL) OR (o.properties IS DISTINCT FROM n.properties AND EXISTS (SELECT 1 FROM unnest(k.keys) AS r(key) WHERE (o.properties -> r.key) IS DISTINCT FROM (n.properties -> r.key)))
    )
    INSERT INTO object_refs (src_id, src_type_id, key, dst_id)
    (
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, type_id, deleted_at, properties, old_properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ) EXCEPT (
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, old_type_id AS type_id, old_deleted_at AS deleted_at, old_properties AS properties, properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )
    ON CONFLICT DO NOTHING
        $sql$;
    ELSE
    WITH ch AS MATERIALIZED (
        SELECT n.id, n.type_id, n.deleted_at, n.properties,
               o.type_id AS old_type_id, o.deleted_at AS old_deleted_at,
               o.properties AS old_properties,
               (o.type_id IS DISTINCT FROM n.type_id
                OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL)) AS whole
          FROM new_rows n
          JOIN old_rows o ON o.id = n.id
          LEFT JOIN (SELECT owner_id, array_agg(key::text) AS keys FROM property_defs WHERE owner_kind = 'type' AND data_type = 'object_ref' GROUP BY owner_id) k ON k.owner_id = n.type_id
         WHERE o.type_id IS DISTINCT FROM n.type_id OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL) OR (o.properties IS DISTINCT FROM n.properties AND EXISTS (SELECT 1 FROM unnest(k.keys) AS r(key) WHERE (o.properties -> r.key) IS DISTINCT FROM (n.properties -> r.key)))
    )
    DELETE FROM object_refs r
     USING ((
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, old_type_id AS type_id, old_deleted_at AS deleted_at, old_properties AS properties, properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ) EXCEPT (
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, type_id, deleted_at, properties, old_properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ))
           AS g (src_id, src_type_id, key, dst_id)
     WHERE r.src_id = g.src_id AND r.key = g.key AND r.dst_id = g.dst_id;
    WITH ch AS MATERIALIZED (
        SELECT n.id, n.type_id, n.deleted_at, n.properties,
               o.type_id AS old_type_id, o.deleted_at AS old_deleted_at,
               o.properties AS old_properties,
               (o.type_id IS DISTINCT FROM n.type_id
                OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL)) AS whole
          FROM new_rows n
          JOIN old_rows o ON o.id = n.id
          LEFT JOIN (SELECT owner_id, array_agg(key::text) AS keys FROM property_defs WHERE owner_kind = 'type' AND data_type = 'object_ref' GROUP BY owner_id) k ON k.owner_id = n.type_id
         WHERE o.type_id IS DISTINCT FROM n.type_id OR (o.deleted_at IS NULL) IS DISTINCT FROM (n.deleted_at IS NULL) OR (o.properties IS DISTINCT FROM n.properties AND EXISTS (SELECT 1 FROM unnest(k.keys) AS r(key) WHERE (o.properties -> r.key) IS DISTINCT FROM (n.properties -> r.key)))
    )
    INSERT INTO object_refs (src_id, src_type_id, key, dst_id)
    (
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, type_id, deleted_at, properties, old_properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    ) EXCEPT (
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT id, old_type_id AS type_id, old_deleted_at AS deleted_at, old_properties AS properties, properties AS other, whole FROM ch) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND (n.whole OR (n.properties -> d.key) IS DISTINCT FROM (n.other -> d.key))
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )
    ON CONFLICT DO NOTHING;
    END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION object_refs_redefined() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.owner_kind = 'type'
       AND OLD.data_type = 'object_ref' THEN
        IF TG_OP = 'DELETE'
           OR NEW.data_type IS DISTINCT FROM 'object_ref'
           OR NEW.key IS DISTINCT FROM OLD.key
           OR NEW.owner_id IS DISTINCT FROM OLD.owner_id THEN
            DELETE FROM object_refs WHERE src_type_id = OLD.owner_id AND key = OLD.key;
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.owner_kind = 'type'
       AND NEW.data_type = 'object_ref' THEN
        IF TG_OP = 'INSERT'
           OR OLD.data_type IS DISTINCT FROM 'object_ref'
           OR OLD.key IS DISTINCT FROM NEW.key
           OR OLD.owner_id IS DISTINCT FROM NEW.owner_id THEN
            INSERT INTO object_refs (src_id, src_type_id, key, dst_id)
            
    SELECT DISTINCT n.id, n.type_id, d.key, v.value::uuid
      FROM (SELECT * FROM objects WHERE type_id = NEW.owner_id) n
      JOIN property_defs d
        ON d.owner_kind = 'type' AND d.owner_id = n.type_id
       AND d.data_type = 'object_ref' AND d.id = NEW.id
      CROSS JOIN LATERAL jsonb_array_elements_text(
          CASE jsonb_typeof(n.properties -> d.key)
              WHEN 'array' THEN n.properties -> d.key
              WHEN 'string' THEN jsonb_build_array(n.properties -> d.key)
              ELSE '[]'::jsonb
          END
      ) AS v(value)
     WHERE n.deleted_at IS NULL
       AND v.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    
            ON CONFLICT DO NOTHING;
        END IF;
    END IF;
    RETURN NULL;
END $$;
"""

REFS_TRIGGERS = """
DROP TRIGGER IF EXISTS object_refs_on_insert ON objects;
CREATE TRIGGER object_refs_on_insert AFTER INSERT ON objects
    REFERENCING NEW TABLE AS new_rows
    FOR EACH STATEMENT EXECUTE FUNCTION object_refs_inserted();
DROP TRIGGER IF EXISTS object_refs_on_update ON objects;
CREATE TRIGGER object_refs_on_update AFTER UPDATE ON objects
    REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
    FOR EACH STATEMENT EXECUTE FUNCTION object_refs_updated();
DROP TRIGGER IF EXISTS object_refs_on_redefine ON property_defs;
CREATE TRIGGER object_refs_on_redefine AFTER INSERT OR UPDATE OR DELETE ON property_defs
    FOR EACH ROW EXECUTE FUNCTION object_refs_redefined();
"""

ATTACH_FUNCTION = """
CREATE OR REPLACE FUNCTION attachments_follow_object() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE attachments SET workspace_id = NEW.owner_workspace_id
     WHERE owner_table = 'objects' AND owner_id = NEW.id
       AND workspace_id IS DISTINCT FROM NEW.owner_workspace_id;
    RETURN NULL;
END $$;
"""

ATTACH_TRIGGER = """
DROP TRIGGER IF EXISTS attachments_follow_object ON objects;
CREATE TRIGGER attachments_follow_object AFTER UPDATE OF owner_workspace_id ON objects
    FOR EACH ROW WHEN (OLD.owner_workspace_id IS DISTINCT FROM NEW.owner_workspace_id)
    EXECUTE FUNCTION attachments_follow_object();
"""


# revision identifiers, used by Alembic.
revision: str = "0036_sp_platform"
down_revision: Union[str, Sequence[str], None] = "0035_voc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 표 · 색인보다 먼저 — 두 글자 조각 색인(`sp_bigrams`)과 기본값이 이 함수들을 부른다.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(BIGRAMS_SQL)
    op.execute(DATE_SQL)
    op.execute(BRIEF_SQL)
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "nav_groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=40), server_default="", nullable=False),
        sa.Column("audience", sa.String(length=20), server_default="everyone", nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("color", sa.String(length=7), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["nav_groups.id"],
            name=op.f("fk_nav_groups_parent_id_nav_groups"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nav_groups")),
        sa.UniqueConstraint("slug", name="uq_nav_groups_slug"),
    )
    op.create_index(op.f("ix_nav_groups_parent_id"), "nav_groups", ["parent_id"], unique=False)
    op.create_table(
        "object_interfaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=40), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "extends_slugs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "list_view",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("managed_by", sa.String(length=40), server_default="", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_interfaces")),
        sa.UniqueConstraint("slug", name="uq_object_interfaces_slug"),
    )
    op.create_table(
        "object_relation_tombstones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("src_object_id", sa.UUID(), nullable=False),
        sa.Column("dst_object_id", sa.UUID(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column(
            "removed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_relation_tombstones")),
    )
    op.create_index(
        op.f("ix_object_relation_tombstones_relation"),
        "object_relation_tombstones",
        ["relation"],
        unique=False,
    )
    op.create_index(
        op.f("ix_object_relation_tombstones_src_object_id"),
        "object_relation_tombstones",
        ["src_object_id"],
        unique=False,
    )
    op.create_index(
        "ix_relation_tombstones_removed",
        "object_relation_tombstones",
        ["removed_at"],
        unique=False,
    )
    op.create_table(
        "property_defs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_kind", sa.String(length=20), server_default="type", nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=False),
        sa.Column("unit", sa.String(length=24), server_default="", nullable=False),
        sa.Column("help", sa.String(length=200), server_default="", nullable=False),
        sa.Column("required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("multi", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("enum_options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ref_type_slug", sa.String(length=32), nullable=True),
        sa.Column("inverse_label", sa.String(length=64), server_default="", nullable=False),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("decimals", sa.Integer(), nullable=True),
        sa.Column("pattern", sa.String(length=200), nullable=True),
        sa.Column("accept", sa.String(length=16), nullable=True),
        sa.Column("default_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("unique", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("section", sa.String(length=48), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_defs")),
        sa.UniqueConstraint(
            "owner_kind", "owner_id", "key", name="uq_property_defs_owner_key"
        ),
    )
    op.create_index(
        op.f("ix_property_defs_owner_id"), "property_defs", ["owner_id"], unique=False
    )
    op.create_table(
        "relation_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("inverse_label", sa.String(length=64), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("directed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("transitive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("acyclic", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "cardinality", sa.String(length=20), server_default="many_to_many", nullable=False
        ),
        sa.Column("src_type_slugs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dst_type_slugs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("managed_by", sa.String(length=40), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relation_types")),
        sa.UniqueConstraint("slug", name="uq_relation_types_slug"),
    )
    op.create_table(
        "request_timings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("route", sa.String(length=300, collation="C"), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("response_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("request_id", sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_timings")),
    )
    op.create_index(
        op.f("ix_request_timings_created_at"), "request_timings", ["created_at"], unique=False
    )
    op.create_index(
        "ix_request_timings_route",
        "request_timings",
        ["route", "method", "created_at"],
        unique=False,
    )
    op.create_table(
        "task_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(data IS NULL) <> (path IS NULL)", name=op.f("ck_task_files_one_place")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_files")),
    )
    op.create_index(
        op.f("ix_task_files_expires_at"), "task_files", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_task_files_sha256"), "task_files", ["sha256"], unique=False)
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=80), nullable=False),
        sa.Column("host", sa.String(length=120), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("current_job_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("worker_id", name=op.f("pk_worker_heartbeats")),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), server_default="", nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("restricted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["workspaces.id"],
            name=op.f("fk_workspaces_parent_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_index(op.f("ix_workspaces_parent_id"), "workspaces", ["parent_id"], unique=False)
    op.create_index(op.f("ix_workspaces_slug"), "workspaces", ["slug"], unique=True)
    op.create_table(
        "object_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=40), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("nav_group_id", sa.UUID(), nullable=True),
        sa.Column("kind_class", sa.String(length=20), server_default="record", nullable=False),
        sa.Column("system_source", sa.String(length=40), server_default="", nullable=False),
        sa.Column("entry_policy", sa.String(length=20), server_default="open", nullable=False),
        sa.Column(
            "interface_slugs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("core", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("managed_by", sa.String(length=40), server_default="", nullable=False),
        sa.Column("key_policy", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("key_scope", sa.String(length=20), server_default="global", nullable=False),
        sa.Column(
            "temporal_kind", sa.String(length=20), server_default="evergreen", nullable=False
        ),
        sa.Column("usage", sa.String(length=16), server_default="axis", nullable=False),
        sa.Column(
            "list_view",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "form_view",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "detail_view",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("title_template", sa.String(length=200), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["nav_group_id"],
            ["nav_groups.id"],
            name=op.f("fk_object_types_nav_group_id_nav_groups"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_types")),
        sa.UniqueConstraint("slug", name="uq_object_types_slug"),
    )
    op.create_table(
        "attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_table", sa.String(length=60), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("owner_field", sa.String(length=48), nullable=True),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("media", sa.String(length=8), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("thumb_path", sa.String(length=300), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("relative_path", sa.String(length=300), nullable=False),
        sa.Column("uploaded_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_attachments_uploaded_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_attachments_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
    )
    op.create_index(
        op.f("ix_attachments_created_at"), "attachments", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_attachments_deleted_at"), "attachments", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_attachments_owner_field"), "attachments", ["owner_field"], unique=False
    )
    op.create_index(op.f("ix_attachments_owner_id"), "attachments", ["owner_id"], unique=False)
    op.create_index(
        op.f("ix_attachments_owner_table"), "attachments", ["owner_table"], unique=False
    )
    op.create_index(op.f("ix_attachments_sha256"), "attachments", ["sha256"], unique=False)
    op.create_index(
        op.f("ix_attachments_workspace_id"), "attachments", ["workspace_id"], unique=False
    )
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.String(length=200), nullable=False),
        sa.Column("actor_client", sa.String(length=40), nullable=True),
        sa.Column("actor_token", sa.String(length=100), nullable=True),
        sa.Column("target_table", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("target_label", sa.String(length=300), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=40), nullable=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_entries_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_entries")),
        sa.UniqueConstraint("seq", name=op.f("uq_audit_entries_seq")),
    )
    op.create_index(op.f("ix_audit_entries_action"), "audit_entries", ["action"], unique=False)
    op.create_index(
        op.f("ix_audit_entries_actor_client"), "audit_entries", ["actor_client"], unique=False
    )
    op.create_index(
        op.f("ix_audit_entries_actor_id"), "audit_entries", ["actor_id"], unique=False
    )
    op.create_index(
        "ix_audit_entries_changes_batch",
        "audit_entries",
        [sa.literal_column("((changes -> '_batch') ->> 'id')")],
        unique=False,
    )
    op.create_index(
        "ix_audit_entries_changes_dst",
        "audit_entries",
        [sa.literal_column("(changes ->> 'dst')")],
        unique=False,
    )
    op.create_index(
        "ix_audit_entries_changes_src",
        "audit_entries",
        [sa.literal_column("(changes ->> 'src')")],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_entries_created_at"), "audit_entries", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_audit_entries_request_id"), "audit_entries", ["request_id"], unique=False
    )
    op.create_index(
        op.f("ix_audit_entries_target_id"), "audit_entries", ["target_id"], unique=False
    )
    op.create_index(
        op.f("ix_audit_entries_target_table"), "audit_entries", ["target_table"], unique=False
    )
    op.create_index(
        op.f("ix_audit_entries_workspace_id"), "audit_entries", ["workspace_id"], unique=False
    )
    op.create_table(
        "bundle_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by_id", sa.UUID(), nullable=True),
        sa.Column("undo_note", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_bundle_runs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by_id"],
            ["users.id"],
            name=op.f("fk_bundle_runs_undone_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bundle_runs")),
    )
    op.create_index("ix_bundle_runs_at", "bundle_runs", ["at"], unique=False)
    op.create_table(
        "data_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=20), server_default="odata", nullable=False),
        sa.Column("base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("entity_set", sa.String(length=500), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("filter", sa.Text(), server_default="", nullable=False),
        sa.Column("select", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "auth",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("page_size", sa.Integer(), server_default="500", nullable=False),
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column(
            "mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("since_mark", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "relations_since_mark", sa.String(length=64), server_default="", nullable=False
        ),
        sa.Column(
            "relations_waiting",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_name", sa.String(length=100), server_default="", nullable=False),
        sa.Column("deprecate_missing", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("interval_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_data_sources_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["object_types.id"],
            name=op.f("fk_data_sources_type_id_object_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_data_sources_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_sources")),
        sa.UniqueConstraint("slug", name=op.f("uq_data_sources_slug")),
    )
    op.create_table(
        "metric_defs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("source_type_id", sa.UUID(), nullable=False),
        sa.Column(
            "spec",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("interval_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overlap", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("current_run_id", sa.UUID(), nullable=True),
        sa.Column("cells_run_id", sa.UUID(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("cells", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_metric_defs_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_type_id"],
            ["object_types.id"],
            name=op.f("fk_metric_defs_source_type_id_object_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_defs")),
        sa.UniqueConstraint("slug", name=op.f("uq_metric_defs_slug")),
    )
    op.create_index(
        op.f("ix_metric_defs_source_type_id"), "metric_defs", ["source_type_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        op.f("ix_notifications_created_at"), "notifications", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_notifications_kind"), "notifications", ["kind"], unique=False)
    op.create_index(
        op.f("ix_notifications_read_at"), "notifications", ["read_at"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False
    )
    op.create_table(
        "object_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("src_type", sa.String(length=32), nullable=False),
        sa.Column("src_id", sa.UUID(), nullable=False),
        sa.Column("dst_type", sa.String(length=32), nullable=False),
        sa.Column("dst_id", sa.UUID(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("evidence_note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_object_links_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_links")),
        sa.UniqueConstraint("src_id", "dst_id", "relation", name="uq_object_links_edge"),
    )
    op.create_index(
        "ix_object_links_dst", "object_links", ["dst_id", "relation"], unique=False
    )
    op.create_index(
        op.f("ix_object_links_relation"), "object_links", ["relation"], unique=False
    )
    op.create_index(
        "ix_object_links_src", "object_links", ["src_id", "relation"], unique=False
    )
    op.create_table(
        "objects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("owner_workspace_id", sa.UUID(), nullable=True),
        sa.Column("valid_from_year", sa.Integer(), nullable=True),
        sa.Column("valid_to_year", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
        sa.Column(
            "human_edits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "previous_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("merged_into_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_objects_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["objects.id"],
            name=op.f("fk_objects_merged_into_id_objects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_objects_owner_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["object_types.id"],
            name=op.f("fk_objects_type_id_object_types"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objects")),
    )
    op.create_index(op.f("ix_objects_deleted_at"), "objects", ["deleted_at"], unique=False)
    op.create_index(
        "ix_objects_key_bigram",
        "objects",
        [sa.literal_column("sp_bigrams(key)")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_objects_key_trgm",
        "objects",
        ["key"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"key": "gin_trgm_ops"},
    )
    op.create_index("ix_objects_key_type", "objects", ["key", "type_id"], unique=False)
    op.create_index(op.f("ix_objects_label"), "objects", ["label"], unique=False)
    op.create_index(
        "ix_objects_label_bigram",
        "objects",
        [sa.literal_column("sp_bigrams(label)")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_objects_label_trgm",
        "objects",
        ["label"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"label": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_objects_merged_into",
        "objects",
        ["merged_into_id"],
        unique=False,
        postgresql_where=sa.text("merged_into_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_objects_owner_workspace_id"), "objects", ["owner_workspace_id"], unique=False
    )
    op.create_index(op.f("ix_objects_type_id"), "objects", ["type_id"], unique=False)
    op.create_index(
        "ix_objects_type_key_norm",
        "objects",
        [
            "type_id",
            sa.literal_column(
                "lower(normalize(regexp_replace(btrim(key), '\\s+', ' ', 'g'), NFKC))"
            ),
        ],
        unique=False,
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.create_index(
        "ix_objects_type_label_lower",
        "objects",
        ["type_id", sa.literal_column("lower(label)")],
        unique=False,
    )
    op.create_index("ix_objects_type_status", "objects", ["type_id", "status"], unique=False)
    op.create_index(
        "ix_objects_type_updated", "objects", ["type_id", "updated_at"], unique=False
    )
    op.create_table(
        "ontology_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.String(length=120), server_default="", nullable=False),
        sa.Column("reason", sa.String(length=200), server_default="", nullable=False),
        sa.Column(
            "schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_ontology_snapshots_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ontology_snapshots")),
    )
    op.create_index(
        op.f("ix_ontology_snapshots_taken_at"),
        "ontology_snapshots",
        ["taken_at"],
        unique=False,
    )
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("item_id", sa.String(length=300), nullable=False),
        sa.Column("question", sa.String(length=500), server_default="", nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("choice", sa.String(length=200), server_default="", nullable=False),
        sa.Column("choice_label", sa.String(length=300), server_default="", nullable=False),
        sa.Column("recommended", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("followed", sa.Boolean(), nullable=True),
        sa.Column("mode", sa.String(length=12), server_default="one", nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("message", sa.String(length=500), server_default="", nullable=False),
        sa.Column("rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("signature", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "undo",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("undoable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("type_slug", sa.String(length=64), server_default="", nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_review_decisions_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by_id"],
            ["users.id"],
            name=op.f("fk_review_decisions_undone_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_review_decisions_workspace_id_workspaces"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_decisions")),
    )
    op.create_index(
        "ix_review_decisions_batch", "review_decisions", ["batch_id"], unique=False
    )
    op.create_index(
        "ix_review_decisions_item", "review_decisions", ["kind", "item_id"], unique=False
    )
    op.create_index(
        "ix_review_decisions_kind_at", "review_decisions", ["kind", "decided_at"], unique=False
    )
    op.create_table(
        "saved_views",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column(
            "query",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("home_order", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_saved_views_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["object_types.id"],
            name=op.f("fk_saved_views_type_id_object_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_saved_views_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_views")),
    )
    op.create_index(
        op.f("ix_saved_views_home_order"), "saved_views", ["home_order"], unique=False
    )
    op.create_index(op.f("ix_saved_views_type_id"), "saved_views", ["type_id"], unique=False)
    op.create_index(
        "ix_saved_views_type_owner", "saved_views", ["type_id", "owner_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_saved_views_workspace_id"), "saved_views", ["workspace_id"], unique=False
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("input_file_id", sa.UUID(), nullable=True),
        sa.Column("output_file_id", sa.UUID(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column("worker_id", sa.String(length=80), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["input_file_id"],
            ["task_files.id"],
            name=op.f("fk_tasks_input_file_id_task_files"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["output_file_id"],
            ["task_files.id"],
            name=op.f("fk_tasks_output_file_id_task_files"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["tasks.id"],
            name=op.f("fk_tasks_parent_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_tasks_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_tasks_workspace_id_workspaces"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_created_at"), "tasks", ["created_at"], unique=False)
    op.create_index(op.f("ix_tasks_kind"), "tasks", ["kind"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index(op.f("ix_tasks_workspace_id"), "tasks", ["workspace_id"], unique=False)
    op.create_table(
        "webhooks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("secret", sa.String(length=200), server_default="", nullable=False),
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("type_slugs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("core_types_only", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_webhooks_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhooks")),
    )
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_workspace_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_members_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_members")),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_pair"),
    )
    op.create_index(
        op.f("ix_workspace_members_user_id"), "workspace_members", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_workspace_members_workspace_id"),
        "workspace_members",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "attachment_tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_name", sa.String(length=100), nullable=True),
        sa.Column("owner_table", sa.String(length=60), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("owner_field", sa.String(length=48), nullable=True),
        sa.Column("filename", sa.String(length=255), server_default="", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attachment_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name=op.f("fk_attachment_tickets_attachment_id_attachments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_attachment_tickets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachment_tickets")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_attachment_tickets_token_hash")),
    )
    op.create_index(
        op.f("ix_attachment_tickets_user_id"), "attachment_tickets", ["user_id"], unique=False
    )
    op.create_table(
        "bundle_undo_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["bundle_runs.id"],
            name=op.f("fk_bundle_undo_entries_run_id_bundle_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bundle_undo_entries")),
    )
    op.create_index(
        "ix_bundle_undo_entries_run", "bundle_undo_entries", ["run_id", "seq"], unique=False
    )
    op.create_table(
        "data_source_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("actor_label", sa.String(length=200), server_default="", nullable=False),
        sa.Column("rows_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_data_source_runs_source_id_data_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source_runs")),
    )
    op.create_index(
        op.f("ix_data_source_runs_source_id"), "data_source_runs", ["source_id"], unique=False
    )
    op.create_index(
        "ix_data_source_runs_source_started",
        "data_source_runs",
        ["source_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "home_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("metric_id", sa.UUID(), nullable=False),
        sa.Column("home_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("split", sa.String(length=100), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_home_metrics_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"],
            ["metric_defs.id"],
            name=op.f("fk_home_metrics_metric_id_metric_defs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_home_metrics_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_home_metrics")),
        sa.UniqueConstraint(
            "workspace_id", "metric_id", name="uq_home_metrics_workspace_metric"
        ),
    )
    op.create_index(
        op.f("ix_home_metrics_metric_id"), "home_metrics", ["metric_id"], unique=False
    )
    op.create_index(
        op.f("ix_home_metrics_workspace_id"), "home_metrics", ["workspace_id"], unique=False
    )
    op.create_table(
        "metric_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("metric_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("recipe", sa.String(length=20), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.UUID(), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["metric_id"],
            ["metric_defs.id"],
            name=op.f("fk_metric_alerts_metric_id_metric_defs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_metric_alerts_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_alerts")),
    )
    op.create_index(
        op.f("ix_metric_alerts_metric_id"), "metric_alerts", ["metric_id"], unique=False
    )
    op.create_index(
        op.f("ix_metric_alerts_owner_id"), "metric_alerts", ["owner_id"], unique=False
    )
    op.create_table(
        "metric_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("metric_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False),
        sa.Column("mode", sa.String(length=12), server_default="full", nullable=False),
        sa.Column("spec_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("periods", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("note", sa.String(length=300), server_default="", nullable=False),
        sa.Column("watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cells", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"],
            ["metric_defs.id"],
            name=op.f("fk_metric_runs_metric_id_metric_defs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_runs")),
    )
    op.create_index(
        op.f("ix_metric_runs_metric_id"), "metric_runs", ["metric_id"], unique=False
    )
    op.create_index(
        "ix_metric_runs_metric_started",
        "metric_runs",
        ["metric_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "object_aliases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("object_id", sa.UUID(), nullable=False),
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=80), server_default="alias", nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.Column("norm", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=80), server_default="", nullable=False),
        sa.Column("note", sa.String(length=200), server_default="", nullable=False),
        sa.Column("verified_by_id", sa.UUID(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name=op.f("fk_object_aliases_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["object_types.id"],
            name=op.f("fk_object_aliases_type_id_object_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_id"],
            ["users.id"],
            name=op.f("fk_object_aliases_verified_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_aliases")),
        sa.UniqueConstraint("type_id", "kind", "norm", name="uq_object_aliases_value"),
    )
    op.create_index(
        "ix_object_aliases_lookup", "object_aliases", ["type_id", "norm"], unique=False
    )
    op.create_index("ix_object_aliases_object", "object_aliases", ["object_id"], unique=False)
    op.create_index(
        "ix_object_aliases_value_bigram",
        "object_aliases",
        [sa.literal_column("sp_bigrams(value)")],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_object_aliases_value_trgm",
        "object_aliases",
        ["value"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"value": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_object_aliases_verified",
        "object_aliases",
        ["type_id", "verified_at"],
        unique=False,
    )
    op.create_table(
        "object_refs",
        sa.Column("src_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("dst_id", sa.UUID(), nullable=False),
        sa.Column("src_type_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["src_id"],
            ["objects.id"],
            name=op.f("fk_object_refs_src_id_objects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("src_id", "key", "dst_id", name=op.f("pk_object_refs")),
    )
    op.create_index("ix_object_refs_dst", "object_refs", ["dst_id", "key"], unique=False)
    op.create_index(
        "ix_object_refs_src_type", "object_refs", ["src_type_id", "key"], unique=False
    )
    op.create_table(
        "object_relations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("src_object_id", sa.UUID(), nullable=False),
        sa.Column("dst_object_id", sa.UUID(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("evidence_note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
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
        sa.Column("datasource_id", sa.UUID(), nullable=True),
        sa.Column("datasource_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_object_relations_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_id"],
            ["data_sources.id"],
            name=op.f("fk_object_relations_datasource_id_data_sources"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dst_object_id"],
            ["objects.id"],
            name=op.f("fk_object_relations_dst_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["src_object_id"],
            ["objects.id"],
            name=op.f("fk_object_relations_src_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_relations")),
        sa.UniqueConstraint(
            "src_object_id", "dst_object_id", "relation", name="uq_object_relations_edge"
        ),
    )
    op.create_index(
        "ix_object_relations_datasource",
        "object_relations",
        ["datasource_id"],
        unique=False,
        postgresql_where=sa.text("datasource_id IS NOT NULL"),
    )
    op.create_index(
        "ix_object_relations_dst",
        "object_relations",
        ["dst_object_id", "relation"],
        unique=False,
    )
    op.create_index(
        op.f("ix_object_relations_dst_object_id"),
        "object_relations",
        ["dst_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_object_relations_relation"), "object_relations", ["relation"], unique=False
    )
    op.create_index(
        "ix_object_relations_src",
        "object_relations",
        ["src_object_id", "relation"],
        unique=False,
    )
    op.create_index(
        op.f("ix_object_relations_src_object_id"),
        "object_relations",
        ["src_object_id"],
        unique=False,
    )
    op.create_index(
        "ix_object_relations_updated",
        "object_relations",
        ["relation", "updated_at"],
        unique=False,
    )
    op.create_table(
        "object_watches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("object_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name=op.f("fk_object_watches_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_object_watches_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_watches")),
        sa.UniqueConstraint("object_id", "user_id", name="uq_object_watches_pair"),
    )
    op.create_index(
        op.f("ix_object_watches_object_id"), "object_watches", ["object_id"], unique=False
    )
    op.create_index(
        op.f("ix_object_watches_user_id"), "object_watches", ["user_id"], unique=False
    )
    op.create_table(
        "object_years",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("object_id", sa.UUID(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name=op.f("fk_object_years_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_years")),
        sa.UniqueConstraint("object_id", "year", name="uq_object_years_object_year"),
    )
    op.create_index(
        op.f("ix_object_years_object_id"), "object_years", ["object_id"], unique=False
    )
    op.create_index(op.f("ix_object_years_year"), "object_years", ["year"], unique=False)
    op.create_table(
        "search_misses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=32), server_default="", nullable=False),
        sa.Column("norm", sa.String(length=200), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("hits", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "askers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "vias",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("object_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_search_misses_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name=op.f("fk_search_misses_object_id_objects"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_misses")),
        sa.UniqueConstraint("scope", "norm", name="uq_search_misses_scope_norm"),
    )
    op.create_index("ix_search_misses_last_at", "search_misses", ["last_at"], unique=False)
    op.create_index(
        "ix_search_misses_status_hits", "search_misses", ["status", "hits"], unique=False
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("webhook_id", sa.UUID(), nullable=False),
        sa.Column("event", sa.String(length=60), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["webhook_id"],
            ["webhooks.id"],
            name=op.f("fk_webhook_deliveries_webhook_id_webhooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
    )
    op.create_index(
        "ix_webhook_deliveries_hook_created",
        "webhook_deliveries",
        ["webhook_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webhook_deliveries_status"), "webhook_deliveries", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_deliveries_webhook_id"),
        "webhook_deliveries",
        ["webhook_id"],
        unique=False,
    )
    op.create_table(
        "metric_alert_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("baseline", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["metric_alerts.id"],
            name=op.f("fk_metric_alert_events_alert_id_metric_alerts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_alert_events")),
        sa.UniqueConstraint("alert_id", "key", name="uq_metric_alert_events_key"),
    )
    op.create_index(
        "ix_metric_alert_events_alert_created",
        "metric_alert_events",
        ["alert_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "metric_values",
        sa.Column("metric_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("cell_hash", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=True),
        sa.Column("period", sa.Date(), nullable=True),
        sa.Column("cohort", sa.Date(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column(
            "dims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.Column("value_count", sa.BigInteger(), nullable=False),
        sa.Column("sum", sa.Float(), nullable=True),
        sa.Column("min", sa.Float(), nullable=True),
        sa.Column("max", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["metric_id"],
            ["metric_defs.id"],
            name=op.f("fk_metric_values_metric_id_metric_defs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["metric_runs.id"],
            name=op.f("fk_metric_values_run_id_metric_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "metric_id", "run_id", "cell_hash", name=op.f("pk_metric_values")
        ),
    )
    op.create_index(
        "ix_metric_values_cohort",
        "metric_values",
        ["metric_id", "run_id", "cohort"],
        unique=False,
    )
    op.create_index(
        "ix_metric_values_dims",
        "metric_values",
        ["dims"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"dims": "jsonb_path_ops"},
    )
    op.create_index(
        "ix_metric_values_period",
        "metric_values",
        ["metric_id", "run_id", "period"],
        unique=False,
    )
    op.add_column("users", sa.Column("home_workspace_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_home_workspace_id_workspaces"),
        "users",
        "workspaces",
        ["home_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # ### end Alembic commands ###
    # 표가 다 선 뒤 — 참조 색인 · 첨부의 부서 따라가기 트리거와 계획기 통계.
    op.execute(REFS_FUNCTIONS)
    op.execute(REFS_TRIGGERS)
    op.execute(ATTACH_FUNCTION)
    op.execute(ATTACH_TRIGGER)
    op.execute(
        "CREATE STATISTICS IF NOT EXISTS st_object_refs_type_key (dependencies, ndistinct) "
        "ON src_type_id, key FROM object_refs"
    )
    op.execute(
        "CREATE STATISTICS IF NOT EXISTS st_object_refs_dst_key (dependencies, ndistinct) "
        "ON dst_id, key FROM object_refs"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP STATISTICS IF EXISTS st_object_refs_dst_key")
    op.execute("DROP STATISTICS IF EXISTS st_object_refs_type_key")
    op.execute("DROP TRIGGER IF EXISTS attachments_follow_object ON objects")
    op.execute("DROP TRIGGER IF EXISTS object_refs_on_redefine ON property_defs")
    op.execute("DROP TRIGGER IF EXISTS object_refs_on_update ON objects")
    op.execute("DROP TRIGGER IF EXISTS object_refs_on_insert ON objects")
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("fk_users_home_workspace_id_workspaces"), "users", type_="foreignkey"
    )
    op.drop_column("users", "home_workspace_id")
    op.drop_index("ix_metric_values_period", table_name="metric_values")
    op.drop_index(
        "ix_metric_values_dims",
        table_name="metric_values",
        postgresql_using="gin",
        postgresql_ops={"dims": "jsonb_path_ops"},
    )
    op.drop_index("ix_metric_values_cohort", table_name="metric_values")
    op.drop_table("metric_values")
    op.drop_index("ix_metric_alert_events_alert_created", table_name="metric_alert_events")
    op.drop_table("metric_alert_events")
    op.drop_index(op.f("ix_webhook_deliveries_webhook_id"), table_name="webhook_deliveries")
    op.drop_index(op.f("ix_webhook_deliveries_status"), table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_hook_created", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_search_misses_status_hits", table_name="search_misses")
    op.drop_index("ix_search_misses_last_at", table_name="search_misses")
    op.drop_table("search_misses")
    op.drop_index(op.f("ix_object_years_year"), table_name="object_years")
    op.drop_index(op.f("ix_object_years_object_id"), table_name="object_years")
    op.drop_table("object_years")
    op.drop_index(op.f("ix_object_watches_user_id"), table_name="object_watches")
    op.drop_index(op.f("ix_object_watches_object_id"), table_name="object_watches")
    op.drop_table("object_watches")
    op.drop_index("ix_object_relations_updated", table_name="object_relations")
    op.drop_index(op.f("ix_object_relations_src_object_id"), table_name="object_relations")
    op.drop_index("ix_object_relations_src", table_name="object_relations")
    op.drop_index(op.f("ix_object_relations_relation"), table_name="object_relations")
    op.drop_index(op.f("ix_object_relations_dst_object_id"), table_name="object_relations")
    op.drop_index("ix_object_relations_dst", table_name="object_relations")
    op.drop_index(
        "ix_object_relations_datasource",
        table_name="object_relations",
        postgresql_where=sa.text("datasource_id IS NOT NULL"),
    )
    op.drop_table("object_relations")
    op.drop_index("ix_object_refs_src_type", table_name="object_refs")
    op.drop_index("ix_object_refs_dst", table_name="object_refs")
    op.drop_table("object_refs")
    op.drop_index("ix_object_aliases_verified", table_name="object_aliases")
    op.drop_index(
        "ix_object_aliases_value_trgm",
        table_name="object_aliases",
        postgresql_using="gin",
        postgresql_ops={"value": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_object_aliases_value_bigram", table_name="object_aliases", postgresql_using="gin"
    )
    op.drop_index("ix_object_aliases_object", table_name="object_aliases")
    op.drop_index("ix_object_aliases_lookup", table_name="object_aliases")
    op.drop_table("object_aliases")
    op.drop_index("ix_metric_runs_metric_started", table_name="metric_runs")
    op.drop_index(op.f("ix_metric_runs_metric_id"), table_name="metric_runs")
    op.drop_table("metric_runs")
    op.drop_index(op.f("ix_metric_alerts_owner_id"), table_name="metric_alerts")
    op.drop_index(op.f("ix_metric_alerts_metric_id"), table_name="metric_alerts")
    op.drop_table("metric_alerts")
    op.drop_index(op.f("ix_home_metrics_workspace_id"), table_name="home_metrics")
    op.drop_index(op.f("ix_home_metrics_metric_id"), table_name="home_metrics")
    op.drop_table("home_metrics")
    op.drop_index("ix_data_source_runs_source_started", table_name="data_source_runs")
    op.drop_index(op.f("ix_data_source_runs_source_id"), table_name="data_source_runs")
    op.drop_table("data_source_runs")
    op.drop_index("ix_bundle_undo_entries_run", table_name="bundle_undo_entries")
    op.drop_table("bundle_undo_entries")
    op.drop_index(op.f("ix_attachment_tickets_user_id"), table_name="attachment_tickets")
    op.drop_table("attachment_tickets")
    op.drop_index(op.f("ix_workspace_members_workspace_id"), table_name="workspace_members")
    op.drop_index(op.f("ix_workspace_members_user_id"), table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_table("webhooks")
    op.drop_index(op.f("ix_tasks_workspace_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_kind"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_created_at"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_saved_views_workspace_id"), table_name="saved_views")
    op.drop_index("ix_saved_views_type_owner", table_name="saved_views")
    op.drop_index(op.f("ix_saved_views_type_id"), table_name="saved_views")
    op.drop_index(op.f("ix_saved_views_home_order"), table_name="saved_views")
    op.drop_table("saved_views")
    op.drop_index("ix_review_decisions_kind_at", table_name="review_decisions")
    op.drop_index("ix_review_decisions_item", table_name="review_decisions")
    op.drop_index("ix_review_decisions_batch", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index(op.f("ix_ontology_snapshots_taken_at"), table_name="ontology_snapshots")
    op.drop_table("ontology_snapshots")
    op.drop_index("ix_objects_type_updated", table_name="objects")
    op.drop_index("ix_objects_type_status", table_name="objects")
    op.drop_index("ix_objects_type_label_lower", table_name="objects")
    op.drop_index(
        "ix_objects_type_key_norm",
        table_name="objects",
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.drop_index(op.f("ix_objects_type_id"), table_name="objects")
    op.drop_index(op.f("ix_objects_owner_workspace_id"), table_name="objects")
    op.drop_index(
        "ix_objects_merged_into",
        table_name="objects",
        postgresql_where=sa.text("merged_into_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_objects_label_trgm",
        table_name="objects",
        postgresql_using="gin",
        postgresql_ops={"label": "gin_trgm_ops"},
    )
    op.drop_index("ix_objects_label_bigram", table_name="objects", postgresql_using="gin")
    op.drop_index(op.f("ix_objects_label"), table_name="objects")
    op.drop_index("ix_objects_key_type", table_name="objects")
    op.drop_index(
        "ix_objects_key_trgm",
        table_name="objects",
        postgresql_using="gin",
        postgresql_ops={"key": "gin_trgm_ops"},
    )
    op.drop_index("ix_objects_key_bigram", table_name="objects", postgresql_using="gin")
    op.drop_index(op.f("ix_objects_deleted_at"), table_name="objects")
    op.drop_table("objects")
    op.drop_index("ix_object_links_src", table_name="object_links")
    op.drop_index(op.f("ix_object_links_relation"), table_name="object_links")
    op.drop_index("ix_object_links_dst", table_name="object_links")
    op.drop_table("object_links")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_read_at"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_kind"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_created_at"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_metric_defs_source_type_id"), table_name="metric_defs")
    op.drop_table("metric_defs")
    op.drop_table("data_sources")
    op.drop_index("ix_bundle_runs_at", table_name="bundle_runs")
    op.drop_table("bundle_runs")
    op.drop_index(op.f("ix_audit_entries_workspace_id"), table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_target_table"), table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_target_id"), table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_request_id"), table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_created_at"), table_name="audit_entries")
    op.drop_index("ix_audit_entries_changes_src", table_name="audit_entries")
    op.drop_index("ix_audit_entries_changes_dst", table_name="audit_entries")
    op.drop_index("ix_audit_entries_changes_batch", table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_actor_id"), table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_actor_client"), table_name="audit_entries")
    op.drop_index(op.f("ix_audit_entries_action"), table_name="audit_entries")
    op.drop_table("audit_entries")
    op.drop_index(op.f("ix_attachments_workspace_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_sha256"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_owner_table"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_owner_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_owner_field"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_deleted_at"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_created_at"), table_name="attachments")
    op.drop_table("attachments")
    op.drop_table("object_types")
    op.drop_index(op.f("ix_workspaces_slug"), table_name="workspaces")
    op.drop_index(op.f("ix_workspaces_parent_id"), table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_table("worker_heartbeats")
    op.drop_index(op.f("ix_task_files_sha256"), table_name="task_files")
    op.drop_index(op.f("ix_task_files_expires_at"), table_name="task_files")
    op.drop_table("task_files")
    op.drop_index("ix_request_timings_route", table_name="request_timings")
    op.drop_index(op.f("ix_request_timings_created_at"), table_name="request_timings")
    op.drop_table("request_timings")
    op.drop_table("relation_types")
    op.drop_index(op.f("ix_property_defs_owner_id"), table_name="property_defs")
    op.drop_table("property_defs")
    op.drop_index("ix_relation_tombstones_removed", table_name="object_relation_tombstones")
    op.drop_index(
        op.f("ix_object_relation_tombstones_src_object_id"),
        table_name="object_relation_tombstones",
    )
    op.drop_index(
        op.f("ix_object_relation_tombstones_relation"), table_name="object_relation_tombstones"
    )
    op.drop_table("object_relation_tombstones")
    op.drop_table("object_interfaces")
    op.drop_index(op.f("ix_nav_groups_parent_id"), table_name="nav_groups")
    op.drop_table("nav_groups")
    # ### end Alembic commands ###
    op.execute("DROP FUNCTION IF EXISTS attachments_follow_object()")
    op.execute("DROP FUNCTION IF EXISTS object_refs_redefined()")
    op.execute("DROP FUNCTION IF EXISTS object_refs_updated()")
    op.execute("DROP FUNCTION IF EXISTS object_refs_inserted()")
    op.execute("DROP FUNCTION IF EXISTS sp_job_brief(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS sp_date(text)")
    op.execute("DROP FUNCTION IF EXISTS sp_bigrams(text)")
