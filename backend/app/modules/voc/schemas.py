"""VOC API 형태 — MatNexus 의 것과 같은 모양이다(화면 · 내보내기가 같은 칸을 읽는다)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class VocOut(BaseModel):
    """게시판 한 줄. **상세는 `VocDetailOut`** — 목록에 본문과 이력을 다 실으면 100건짜리
    화면이 느려지고, 그 느림은 목록에서만 보인다."""

    id: uuid.UUID
    seq: int
    """게시판 번호 — 「VOC 12번」."""
    title: str
    status: str
    status_label: str
    """상태를 사람이 읽는 말 — 내보내기 · MCP 가 읽는다. 화면의 말과 색은 `StatusBadge`."""
    page_path: str | None
    created_at: datetime
    created_by: str | None
    """낸 사람. 누가 겪은 문제인지 알아야 되물을 수 있다."""
    status_at: datetime
    """지금 상태가 된 때 — 목록의 「최근 처리」."""
    status_by: str | None
    """지금 상태로 옮긴 사람."""
    is_mine: bool
    """내가 낸 것인가. **이름으로 짐작하지 않는다** — 동명이인이면 남의 것에 수정 단추가
    달린다."""
    can_edit: bool
    """고치거나 지울 수 있는가. 서버가 정한다 — 화면이 규칙을 두 벌로 갖지 않게."""
    event_count: int
    """등록을 뺀 이벤트 수. 목록에서 「말이 오간 건」 을 구별한다."""
    attachment_count: int = 0


class VocEventOut(BaseModel):
    id: uuid.UUID
    at: datetime
    by: str | None
    from_status: str | None
    to_status: str
    to_status_label: str
    note: str | None


class VocAttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size: int
    created_at: datetime
    created_by: str | None
    url: str
    """내려받는 주소. 토큰이 있어야 열린다 — 화면은 `downloadFile` 로 받는다."""


class VocDetailOut(VocOut):
    body: str
    events: list[VocEventOut]
    """등록부터 지금까지, 시간순."""
    attachments: list[VocAttachmentOut] = Field(default_factory=list)
    can_attach: bool = False
    """파일을 붙이거나 뗄 수 있나 — 낸 사람과 관리자."""
    allowed: list[str]
    """**이 사람이 지금 옮길 수 있는 상태.** 관리자와 낸 사람이 다르고 지금 상태에 따라
    다르다 — 화면이 규칙을 외우면 서버와 어긋나는 날이 온다."""
    allowed_labels: dict[str, str]
    """`allowed` 의 각 상태로 옮기는 단추에 적을 말(「해결」 이 아니라 「해결 처리」)."""
    note_required: list[str]
    """`allowed` 가운데 말을 반드시 적어야 하는 것."""
    can_delete_events: bool = False
    """이력 한 줄을 고치거나 지울 수 있는가 — **시스템 관리자만.** 등록 줄은 못 지운다."""


def _filled(value: str | None, what: str) -> str | None:
    """공백뿐인 제목 · 본문은 빈 것이다 — 목록에 빈 줄이 선다."""
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{what}을 입력하십시오.")
    return value.strip() if what == "제목" else value


class VocCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    page_path: str | None = Field(default=None, max_length=300)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _filled(value, "제목") or value

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        return _filled(value, "내용") or value


class VocUpdateRequest(BaseModel):
    """낸 것을 고친다. **안 보낸 칸은 안 건드린다** — 제목 · 본문은 `min_length=1` 이라
    「비웠다」 는 애초에 못 보낸다."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20000)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return _filled(value, "제목")

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return _filled(value, "내용")


class VocEventRequest(BaseModel):
    """상태를 옮기거나 말을 보탠다. **둘 중 하나는 있어야 한다.**

    `status` 를 비우면 댓글이다. 말 없이 상태만 옮기는 것은 상태에 따라 막힌다
    (`NOTE_REQUIRED`)."""

    status: str | None = None
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _something(self) -> VocEventRequest:
        if self.status is None and not (self.note or "").strip():
            raise ValueError("상태를 선택하거나 내용을 입력하십시오.")
        return self


class VocEventUpdateRequest(BaseModel):
    """이력 한 줄의 말을 고친다 — **시스템 관리자만.** 상태 이동은 안 고친다(잘못 옮겼으면 줄을
    지운다)."""

    note: str | None = Field(default=None, max_length=5000)


class VocExportRequest(BaseModel):
    """고른 건들을 zip 하나로 — 건마다 폴더, `item.json` + `attachments/`."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
