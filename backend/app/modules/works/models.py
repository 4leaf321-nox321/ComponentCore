"""내 작업(Work) — 사람이 그리고 있는 문서. **내 공간**의 것이라 소유자(와 관리자)만 본다.

**부품이든 지그든 그리는 방법은 같다** — 레시피(연산 트리) 하나다. 다른 것은 작업의 `kind`
뿐이고, 그것이 「이 그림이 무엇인가」 와 「어느 카탈로그로 올라가나」 를 정한다:

- `part`  제품 · 부품을 그린다. 덤으로 **지그 생성기**를 쓸 수 있다(이 부품을 잡는 지그를
  규칙으로 만들어 준다 — `jig_options`).
- `jig`   지그를 그린다. 생성기가 만들 수 없는 것(공진 시험 지그 · 특수 치구)이 이쪽이다.
  덤으로 **어느 부품을 잡는지**(`jig_for_part_id`)를 이어 둘 수 있다.

승격은 종류를 따라간다 — 부품 작업은 부품으로, 지그 작업은 지그로. 그래서 「이 레시피를
무엇으로 올릴까」 를 물을 일이 없다.

**버전은 고치지 않는다.** 새 버전을 만든다. 되돌리기도 옛 레시피로 새 버전. 올린 STEP 도
`import_step` 노드 하나짜리 버전이다 — 그래서 제품은 늘 「이 작업의 형상」 하나로 통일된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 버전이 어디서 왔나.
VERSION_SOURCES = ("template", "manual", "ai", "import", "restore", "copy")
#: 이 작업이 만드는 것.
#:
#: - `part` · `jig` 는 **그리는 것**이다. 둘은 서로 아무 관계가 없다 — 각자 제 도면이다.
#: - `assembly` 는 **놓는 것**이다. 부품 · 지그를 가져다 서로 위치시킨다(`component` 피처).
WORK_KINDS = ("part", "jig", "assembly")


class Work(Base):
    __tablename__ = "works"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(
        String(10), default="part", server_default="part", index=True
    )
    """part | jig — 무엇을 그리는 작업인가. 그리는 방법은 같다."""
    jig_for_part_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("parts.id", ondelete="SET NULL"), nullable=True
    )
    """지그 작업일 때 — 이 지그가 잡는 부품. 승격할 때 그대로 이어진다."""
    current_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jig_options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """부품 작업일 때 — 마지막으로 쓴 **지그 생성기** 옵션. 다음에 열면 그대로 있다."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class WorkVersion(Base):
    __tablename__ = "work_versions"
    __table_args__ = (UniqueConstraint("work_id", "number", name="uq_work_versions_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    """이 버전을 평가한 작업(`kind="cad"`). 상태 · 요약 · STEP · glTF 는 그쪽에 있다."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
