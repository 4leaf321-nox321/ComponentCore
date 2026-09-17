"""내 작업(works) · 부품 · 지그 카탈로그 — CAD 모델과 지그 프로젝트를 「내 작업」 으로 흡수한다.

- cad_models / cad_model_versions → works / work_versions (이름만 바뀐다)
- jig_projects → works: 제품이 모델이면 그 작업으로 합치고, 아니면 새 작업(제품 STEP 이 있으면
  import_step 버전, 도형 스펙이면 템플릿 레시피 버전). 그 프로젝트의 지그 작업 · 작업물이 따라간다.
- jobs.project_id / artifacts.project_id → work_id
- parts · part_versions · jigs · jig_versions 새로

Revision ID: 0004_works_and_catalogs
Revises: 0003_cad_models
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0004_works_and_catalogs"
down_revision = "0003_cad_models"
branch_labels = None
depends_on = None


def _versioned_catalog(name: str, owner_fk: str, extra: list[sa.Column]) -> None:
    op.create_table(
        name,
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("work_id", PgUUID(as_uuid=True), nullable=True),
        *extra,
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=owner_fk, ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["work_id"], ["works.id"], name=f"fk_{name}_work_id_works", ondelete="SET NULL"
        ),
    )
    op.create_index(f"ix_{name}_owner_id", name, ["owner_id"])
    op.create_index(f"ix_{name}_deleted_at", name, ["deleted_at"])


def upgrade() -> None:
    connection = op.get_bind()

    # --- 1. cad_models → works ------------------------------------------------------
    op.rename_table("cad_models", "works")
    op.add_column(
        "works", sa.Column("jig_options", JSONB(), nullable=False, server_default="{}")
    )
    op.execute("ALTER INDEX ix_cad_models_owner_id RENAME TO ix_works_owner_id")
    op.execute("ALTER INDEX ix_cad_models_deleted_at RENAME TO ix_works_deleted_at")
    op.execute("ALTER TABLE works RENAME CONSTRAINT pk_cad_models TO pk_works")
    op.execute(
        "ALTER TABLE works RENAME CONSTRAINT fk_cad_models_owner_id_users TO fk_works_owner_id_users"
    )

    op.rename_table("cad_model_versions", "work_versions")
    op.alter_column("work_versions", "model_id", new_column_name="work_id")
    op.execute("ALTER INDEX ix_cad_model_versions_model_id RENAME TO ix_work_versions_work_id")
    op.execute(
        "ALTER TABLE work_versions RENAME CONSTRAINT pk_cad_model_versions TO pk_work_versions"
    )
    op.execute(
        "ALTER TABLE work_versions RENAME CONSTRAINT uq_cad_model_versions_number "
        "TO uq_work_versions_number"
    )
    op.execute(
        "ALTER TABLE work_versions RENAME CONSTRAINT fk_cad_model_versions_model_id_cad_models "
        "TO fk_work_versions_work_id_works"
    )
    op.execute(
        "ALTER TABLE work_versions RENAME CONSTRAINT fk_cad_model_versions_created_by_id_users "
        "TO fk_work_versions_created_by_id_users"
    )
    op.execute(
        "ALTER TABLE work_versions RENAME CONSTRAINT fk_cad_model_versions_job_id_jobs "
        "TO fk_work_versions_job_id_jobs"
    )

    # --- 2. jobs · artifacts: project_id → work_id ------------------------------------
    for table in ("jobs", "artifacts"):
        op.drop_constraint(f"fk_{table}_project_id_jig_projects", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_project_id", table_name=table)
        op.add_column(table, sa.Column("work_id", PgUUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table}_work_id", table, ["work_id"])

    # --- 3. jig_projects → works ---------------------------------------------------------
    projects = list(
        connection.execute(
            sa.text(
                "SELECT id, name, description, owner_id, product_filename, product_path, "
                "product_size_bytes, product_spec, product_model_id, created_at, updated_at, "
                "deleted_at FROM jig_projects"
            )
        ).mappings()
    )
    for row in projects:
        if row["product_model_id"] is not None:
            work_id = row["product_model_id"]
        else:
            work_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO works (id, name, description, owner_id, current_version, "
                    "jig_options, created_at, updated_at, deleted_at) VALUES (:id, :name, :desc, "
                    ":owner, 0, '{}', :created, :updated, :deleted)"
                ),
                {
                    "id": work_id,
                    "name": row["name"],
                    "desc": row["description"] or "",
                    "owner": row["owner_id"],
                    "created": row["created_at"],
                    "updated": row["updated_at"],
                    "deleted": row["deleted_at"],
                },
            )
            recipe: dict[str, object] | None = None
            if row["product_path"]:
                artifact_id = uuid.uuid4()
                connection.execute(
                    sa.text(
                        "INSERT INTO artifacts (id, job_id, work_id, owner_id, kind, filename, "
                        "path, content_type, size_bytes, created_at) VALUES (:id, NULL, :work, "
                        ":owner, 'import_step', :filename, :path, 'application/step', :size, "
                        ":created)"
                    ),
                    {
                        "id": artifact_id,
                        "work": work_id,
                        "owner": row["owner_id"],
                        "filename": row["product_filename"] or "product.step",
                        "path": row["product_path"],
                        "size": row["product_size_bytes"] or 0,
                        "created": row["created_at"],
                    },
                )
                recipe = {
                    "version": 1,
                    "nodes": [
                        {
                            "id": "imported",
                            "op": "import_step",
                            "label": row["product_filename"] or "product.step",
                            "file": str(artifact_id),
                        }
                    ],
                }
            elif row["product_spec"]:
                spec = row["product_spec"]
                if isinstance(spec, str):
                    spec = json.loads(spec)
                try:
                    from app.core.recipe import templates

                    recipe = templates.from_primitive_spec(dict(spec))
                except Exception:
                    recipe = None
            if recipe is not None:
                connection.execute(
                    sa.text(
                        "INSERT INTO work_versions (id, work_id, number, recipe, source, note, "
                        "created_by_id, job_id, created_at) VALUES (:id, :work, 1, :recipe, "
                        "'import', '지그 프로젝트에서 옮김', :owner, NULL, :created)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "work": work_id,
                        "recipe": json.dumps(recipe),
                        "owner": row["owner_id"],
                        "created": row["created_at"],
                    },
                )
                connection.execute(
                    sa.text("UPDATE works SET current_version = 1 WHERE id = :id"),
                    {"id": work_id},
                )
        for table in ("jobs", "artifacts"):
            connection.execute(
                sa.text(f"UPDATE {table} SET work_id = :work WHERE project_id = :project"),
                {"work": work_id, "project": row["id"]},
            )

    # cad 작업(모델 평가)은 input 의 model_id 로 작업을 찾는다.
    connection.execute(
        sa.text(
            "UPDATE jobs SET work_id = (input->>'model_id')::uuid "
            "WHERE kind = 'cad' AND work_id IS NULL AND input ? 'model_id' "
            "AND EXISTS (SELECT 1 FROM works WHERE works.id = (jobs.input->>'model_id')::uuid)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE artifacts SET work_id = jobs.work_id FROM jobs "
            "WHERE artifacts.job_id = jobs.id AND artifacts.work_id IS NULL"
        )
    )

    for table in ("jobs", "artifacts"):
        op.drop_column(table, "project_id")
        op.create_foreign_key(
            f"fk_{table}_work_id_works",
            table,
            "works",
            ["work_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.drop_table("jig_projects")

    # --- 4. 카탈로그 ----------------------------------------------------------------------
    _versioned_catalog("parts", "fk_parts_owner_id_users", [])
    op.create_table(
        "part_versions",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("part_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("work_version_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("recipe", JSONB(), nullable=False),
        sa.Column("job_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("promoted_by_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["part_id"],
            ["parts.id"],
            name="fk_part_versions_part_id_parts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_version_id"],
            ["work_versions.id"],
            name="fk_part_versions_work_version_id_work_versions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_part_versions_job_id_jobs", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["promoted_by_id"],
            ["users.id"],
            name="fk_part_versions_promoted_by_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("part_id", "number", name="uq_part_versions_number"),
    )
    op.create_index("ix_part_versions_part_id", "part_versions", ["part_id"])
    op.create_index("ix_part_versions_work_version_id", "part_versions", ["work_version_id"])

    _versioned_catalog(
        "jigs",
        "fk_jigs_owner_id_users",
        [sa.Column("part_id", PgUUID(as_uuid=True), nullable=True)],
    )
    op.create_foreign_key(
        "fk_jigs_part_id_parts", "jigs", "parts", ["part_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_jigs_part_id", "jigs", ["part_id"])
    op.create_table(
        "jig_versions",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("jig_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("job_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("part_version_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("options", JSONB(), nullable=False, server_default="{}"),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("promoted_by_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["jig_id"], ["jigs.id"], name="fk_jig_versions_jig_id_jigs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_jig_versions_job_id_jobs", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["part_version_id"],
            ["part_versions.id"],
            name="fk_jig_versions_part_version_id_part_versions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["promoted_by_id"],
            ["users.id"],
            name="fk_jig_versions_promoted_by_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("jig_id", "number", name="uq_jig_versions_number"),
    )
    op.create_index("ix_jig_versions_jig_id", "jig_versions", ["jig_id"])
    op.create_index("ix_jig_versions_part_version_id", "jig_versions", ["part_version_id"])


def downgrade() -> None:
    raise RuntimeError("되돌리지 않는다 — 내 작업 · 카탈로그가 옛 표를 대신한다.")
