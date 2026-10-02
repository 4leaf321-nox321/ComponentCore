"""폴더 — 항목이 들고 있는 **경로**(`고객A/2026/검사지그`)로 나무를 세운다.

내 작업 · 부품 · 지그 · 템플릿이 같이 쓴다. 폴더 표는 따로 없다 — 폴더는 그 안에 항목이 있을
때 있다(docs/adr/0004). 그래서 여기 있는 것은 경로를 다듬고, 「이 폴더와 그 아래」 를
거르고, 경로들에서 나무를 세고, 폴더째 옮기는 규칙뿐이다.
누가 무엇을 옮길 수 있는지는 모듈이 정한다(내 작업은 내 것만, 카탈로그는 주인 · 관리자).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.shared.errors import AppError, Forbidden, NotFound

#: 폴더 깊이 · 이름 길이의 상한 — 경로가 칸(255)을 넘지 않게, 사람이 읽을 수 있게.
DEPTH = 8
NAME = 60
LENGTH = 255


class FolderOut(BaseModel):
    path: str
    """`고객A/2026` — 빈 것이 맨 위."""
    count: int
    """**바로 이 폴더에** 있는 항목 수(하위 폴더는 빼고)."""


class FolderRenameRequest(BaseModel):
    path: str = Field(min_length=1, max_length=LENGTH)
    """바꿀 폴더(그 아래 하위 폴더까지 함께 옮긴다)."""
    to: str = Field(default="", max_length=LENGTH)
    """새 경로 — 빈 문자열이면 맨 위로 합친다. 폴더 지우기는 위 폴더로 합치는 것이다."""


class FolderMoveRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    folder: str = Field(default="", max_length=LENGTH)


class MovedOut(BaseModel):
    moved: int


def normalize(raw: str, error_code: str) -> str:
    """사람이 적은 경로를 한 모양으로 — `/고객A//2026/ ` → `고객A/2026`. 역슬래시도 나눈다.
    빈 것은 맨 위다. 틀리면 `error_code` 로 말한다(모듈마다 제 코드가 있다)."""
    parts = [one.strip() for one in raw.replace("\\", "/").split("/")]
    parts = [one for one in parts if one]
    if len(parts) > DEPTH:
        raise AppError(error_code, f"폴더는 {DEPTH} 단계까지입니다")
    for one in parts:
        if len(one) > NAME:
            raise AppError(error_code, f"폴더 이름은 {NAME} 자까지입니다: {one[:20]}…")
    path = "/".join(parts)
    if len(path) > LENGTH:
        raise AppError(error_code, "폴더 경로가 너무 깁니다")
    return path


def under(column: Any, path: str) -> ColumnElement[bool]:
    """이 폴더와 그 아래 — `LIKE` 의 `%` · `_` 는 글자 그대로 읽게 막는다(`고객A_비슷` 이
    `고객A` 아래로 잡히지 않게)."""
    escaped = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return or_(column == path, column.like(f"{escaped}/%", escape="\\"))


def narrowed(
    query: Any, column: Any, folder: str | None, subfolders: bool, error_code: str
) -> Any:
    """목록 질의를 폴더로 거른다 — `folder` 가 None 이면 그대로, 빈 것이면 맨 위(하위까지면
    전부), 아니면 그 폴더(`subfolders` 면 그 아래까지)."""
    if folder is None:
        return query
    path = normalize(folder, error_code)
    if subfolders and path:
        return query.where(under(column, path))
    if not subfolders:
        return query.where(column == path)
    return query


def tree(db: Session, column: Any, *where: Any) -> list[FolderOut]:
    """보이는 항목이 놓인 폴더들과 **바로 그 폴더에** 있는 수. 위 폴더도 빠짐없이 —
    `고객A/2026` 만 있어도 `고객A` 가 나온다(0 개로). 맨 위(빈 경로)는 늘 있다."""
    rows = db.execute(select(column, func.count()).where(*where).group_by(column)).all()
    counts: dict[str, int] = {}
    for path, count in rows:
        counts[path] = counts.get(path, 0) + int(count)
        parts = path.split("/") if path else []
        for depth in range(1, len(parts)):
            counts.setdefault("/".join(parts[:depth]), 0)
    counts.setdefault("", 0)
    return [FolderOut(path=path, count=counts[path]) for path in sorted(counts)]


def checked_rename(path: str, to: str, error_code: str) -> tuple[str, str]:
    """폴더째 옮기기의 두 경로 — 맨 위는 못 옮기고, 제 하위로도 못 옮긴다."""
    old = normalize(path, error_code)
    new = normalize(to, error_code)
    if not old:
        raise AppError(error_code, "맨 위는 옮길 수 없습니다 — 폴더를 고르세요")
    if new.startswith(old + "/"):
        raise AppError(error_code, "폴더를 제 하위 폴더 안으로 옮길 수 없습니다")
    return old, new


def renamed(current: str, old: str, new: str, error_code: str) -> str:
    """`old` 를 `new` 로 옮길 때 `current` 에 있던 항목이 갈 곳 — 하위 경로는 그대로
    따라간다."""
    rest = current[len(old) :].lstrip("/")
    return normalize(f"{new}/{rest}" if rest else new, error_code)


def _josa(noun: str, consonant: str, vowel: str) -> str:
    """받침이 있으면 `consonant`(이 · 을), 없으면 `vowel`(가 · 를)."""
    last = noun[-1:] or " "
    has_final = "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 != 0
    return noun + (consonant if has_final else vowel)


def _may_touch(rows: list[Any], user: Any) -> bool:
    """주인이거나 관리자 — 카탈로그 항목을 고치는 규칙(`require_owner`)과 같다."""
    return bool(getattr(user, "is_system_admin", False)) or all(
        row.owner_id == user.id for row in rows
    )


def rename_shared(
    db: Session,
    model: Any,
    *visible: Any,
    path: str,
    to: str,
    user: Any,
    noun: str,
    error_code: str,
    forbidden_code: str,
) -> int:
    """**여럿이 함께 쓰는** 공간(부품 · 지그 · 템플릿)의 폴더째 옮기기. 그 폴더(하위 포함)에
    남의 것이 섞여 있으면 관리자만 — 내가 고친 이름이 남의 항목을 옮긴다.
    옮긴 수를 돌려준다."""
    old, new = checked_rename(path, to, error_code)
    if new == old:
        return 0
    rows = list(db.scalars(select(model).where(*visible, under(model.folder, old))))
    if not _may_touch(rows, user):
        raise Forbidden(
            forbidden_code,
            f"다른 사람의 {_josa(noun, '이', '가')} 든 폴더는 관리자만 옮기거나 "
            "이름을 바꿀 수 있습니다",
        )
    for row in rows:
        row.folder = renamed(row.folder, old, new, error_code)
    db.commit()
    return len(rows)


def move_shared(
    db: Session,
    model: Any,
    *visible: Any,
    ids: list[uuid.UUID],
    folder: str,
    user: Any,
    noun: str,
    error_code: str,
    forbidden_code: str,
    missing_code: str,
) -> int:
    """여럿이 함께 쓰는 공간의 항목들을 한 폴더로 — 주인 · 관리자만. 하나라도 안 되면 아무것도
    옮기지 않는다."""
    path = normalize(folder, error_code)
    rows = list(db.scalars(select(model).where(model.id.in_(ids), *visible)))
    if len(rows) != len(set(ids)):
        raise NotFound(missing_code, f"{_josa(noun, '을', '를')} 찾을 수 없습니다")
    if not _may_touch(rows, user):
        raise Forbidden(forbidden_code, f"남의 {_josa(noun, '은', '는')} 옮길 수 없습니다")
    for row in rows:
        row.folder = path
    db.commit()
    return len(rows)
