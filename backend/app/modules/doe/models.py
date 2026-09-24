"""실험계획(DOE) — 치수 범위에서 뽑은 **설계점 묶음**과 그 결과.

형상 수십 벌을 만들어 해석(ANSYS)으로 넘기는 것이 목적이라, 두 가지를 반드시 남긴다:

- **기준 레시피 스냅샷** — 작업의 레시피는 뒤에 바뀐다. 스냅샷이 없으면 「이 DOE 가 무슨
  형상이었나」 를 나중에 못 찾는다.
- **시드** — LHS 는 난수다. 시드가 없으면 같은 48점을 다시 만들 수 없고, 그러면 해석 결과와
  형상을 잇지 못한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DoeStudy(Base):
    __tablename__ = "doe_studies"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("works.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """어느 작업에서 시작했나. 지워져도 DOE 는 남는다 — 스냅샷이 있으니 혼자 선다."""
    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB)
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """대상 버전의 해석 조건을 **그때 떠 둔 것**. 작업이 나중에 바뀌어도 이 DOE 가 무엇으로
    돌았는지 남는다 — 레시피 스냅샷과 같은 까닭이다."""
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    method: Mapped[str] = mapped_column(String(20), default="factorial")
    samples: Mapped[int] = mapped_column(Integer, default=20)
    seed: Mapped[int] = mapped_column(Integer, default=1)
    local_dir: Mapped[str] = mapped_column(Text, default="", server_default="")
    """서버 보관 폴더(filestore/doe/…). 설계점은 먼저 여기에 만들어진다."""
    export_dir: Mapped[str] = mapped_column(Text, default="", server_default="")
    keep_forever: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """**영구보관** — 보관 기한과 무관하게 공유 폴더에 남긴다.

    기한은 기본값이고 이것이 예외다. 지우는 일은 되돌릴 수 없으니, 「이건 남겨야 한다」 를
    아는 사람이 그때 켤 수 있어야 한다."""
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """해석 쪽이 **다 읽었다**고 알린 때(오케스트레이터의 `doe_release`).

    「성공했다」 가 아니라 「더 안 읽는다」 는 뜻이다 — 실패해서 다시 돌릴 생각이면 알리지
    않는다. 알린 것은 기한을 기다리지 않고 먼저 치운다."""
    """공유 폴더 안의 이 DOE 폴더(서버가 보는 경로). **「보내기」 를 눌러야** 채워진다 — 해석이
    읽는 폴더에 만들다 만 것을 두지 않으려고. 화면은 윈도우 경로로 바꿔 보여 준다."""
    exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """마지막으로 공유 폴더에 보낸 때. 없으면 아직 서버 안에만 있다."""
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    point_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DoePoint(Base):
    """설계점 하나 — 치수 한 벌과 그것으로 만든 형상의 치수표."""

    __tablename__ = "doe_points"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("doe_studies.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    """1 부터. 파일 이름(p0001.step)과 같은 번호다 — 해석 결과를 되짚는 열쇠."""
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    """pending · ok · failed. **실패해도 남긴다** — 왜 빠졌는지 알아야 범위를 고친다."""
    error: Mapped[str] = mapped_column(Text, default="", server_default="")
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """치수표 전체(면 · 구멍 · 관성)."""
    step_file: Mapped[str] = mapped_column(Text, default="", server_default="")
    point_file: Mapped[str] = mapped_column(Text, default="", server_default="")
    """이 설계점의 **모든 것**(`points/pNNNN.json`) — 이 점이 무엇인가(변수 값) · 영역과 바디의
    좌표 지문 · 그 점의 값으로 풀린 조건.

    **STEP 은 이름표를 못 나른다.** 해석이 「어느 면이 고정면이고 무엇을 할 것인가」 를 물을
    곳은 이 파일뿐이다. 영역과 조건은 늘 짝으로 읽히므로 한 파일에 둔다 — 나누면 「하나는
    있고 하나는 없는」 상태가 생길 자리만 는다."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
