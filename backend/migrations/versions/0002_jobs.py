"""작업 · 작업물 — jig_runs 를 jobs(kind="jig") 로 흡수한다.

옛 실행 행은 옮기고, 그 결과 파일은 요약의 files 에서 artifacts 행을 만든다. 그 뒤 jig_runs 를
지운다.

Revision ID: 0002_jobs
Revises: 0001_initial
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision = "0002_jobs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_MIME = {
    "jig_step": "application/step",
    "assembly_step": "application/step",
    "jig_glb": "model/gltf-binary",
    "product_glb": "model/gltf-binary",
    "jig_stl": "model/stl",
}


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("requested_by_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("project_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("input", JSONB(), nullable=False, server_default="{}"),
        sa.Column("options", JSONB(), nullable=False, server_default="{}"),
        sa.Column("progress", JSONB(), nullable=False, server_default="[]"),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_dir", sa.String(500), nullable=True),
        sa.Column("worker_id", sa.String(80), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name="fk_jobs_requested_by_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["jig_projects.id"],
            name="fk_jobs_project_id_jig_projects",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_jobs_kind", "jobs", ["kind"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_requested_by_id", "jobs", ["requested_by_id"])
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    op.create_table(
        "artifacts",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("project_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("owner_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("parent_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_artifacts_job_id_jobs", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["jig_projects.id"],
            name="fk_artifacts_project_id_jig_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_artifacts_owner_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["artifacts.id"],
            name="fk_artifacts_parent_id_artifacts",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])
    op.create_index("ix_artifacts_created_at", "artifacts", ["created_at"])

    # --- 옛 실행을 옮긴다 ----------------------------------------------------------
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, project_id, requested_by_id, status, options, summary, error, "
            "output_dir, started_at, finished_at FROM jig_runs"
        )
    ).mappings()
    for row in rows:
        summary = row["summary"]
        if isinstance(summary, str):
            summary = json.loads(summary)
        options = row["options"]
        if isinstance(options, str):
            options = json.loads(options)
        progress = (summary or {}).get("stages", [])
        connection.execute(
            sa.text(
                "INSERT INTO jobs (id, kind, status, requested_by_id, project_id, input, options, "
                "progress, summary, error, output_dir, attempts, created_at, started_at, finished_at) "
                "VALUES (:id, 'jig', :status, :requested_by_id, :project_id, '{}', :options, "
                ":progress, :summary, :error, :output_dir, 1, :started_at, :started_at, :finished_at)"
            ),
            {
                "id": row["id"],
                "status": row["status"],
                "requested_by_id": row["requested_by_id"],
                "project_id": row["project_id"],
                "options": json.dumps(options or {}),
                "progress": json.dumps(progress),
                "summary": json.dumps(summary) if summary is not None else None,
                "error": row["error"],
                "output_dir": row["output_dir"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
            },
        )
        if row["status"] == "done" and summary and row["output_dir"]:
            for key, filename in (summary.get("files") or {}).items():
                if key not in _MIME:
                    continue
                connection.execute(
                    sa.text(
                        "INSERT INTO artifacts (id, job_id, project_id, owner_id, kind, filename, "
                        "path, content_type, size_bytes, created_at) VALUES (:id, :job_id, "
                        ":project_id, :owner_id, :kind, :filename, :path, :content_type, 0, "
                        "COALESCE(:finished_at, now()))"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "job_id": row["id"],
                        "project_id": row["project_id"],
                        "owner_id": row["requested_by_id"],
                        "kind": key,
                        "filename": filename,
                        "path": f"{row['output_dir']}/{filename}",
                        "content_type": _MIME[key],
                        "finished_at": row["finished_at"],
                    },
                )

    op.drop_table("jig_runs")


def downgrade() -> None:
    raise RuntimeError("jig_runs 로 되돌리지 않는다 — 작업 · 작업물이 그 자리를 대신한다.")
