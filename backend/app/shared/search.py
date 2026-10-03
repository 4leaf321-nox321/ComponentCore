"""찾기 규칙 — **한 곳**. 내 작업 · 부품 · 지그 · 템플릿 · DOE 의 `q` 가 다 이것을 쓴다.

전에는 모듈마다 `ILIKE %q%` 를 따로 썼다 — 한쪽에 꼬리표를 더하면 다른 쪽은 빠지고, 사람은
목록마다 다른 답을 받는다. 규칙은 하나다:

- **무엇을 보나**: 이름 · 설명 · 꼬리표 · 만든 사람(표시 이름), 그리고 목록마다 덧붙이는 것
  (DOE 는 대상 작업의 이름).
- **낱말마다 나눠 AND** — 「알루미늄 5052」 는 둘을 다 든 것(MatNexus 가 그렇게 한다). 한
  낱말은 위의 어느 칸에 있어도 된다(OR).
- 글자 포함(`ILIKE %낱말%`)이다 — 한글은 형태소 사전이 없어 전문 검색이 못 쪼개지만, 글자
  포함은 상관없다. `pg_trgm` 의 GIN 색인(마이그레이션 0028)이 이 꼴을 탄다 — 색인이 없어도
  답은 같고 느릴 뿐이다.
- 사용자가 친 `%` · `_` 는 글자 그대로 찾는다(LIKE 의 와일드카드가 아니다).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import Text, and_, cast, exists, literal, or_, select
from sqlalchemy.sql import ColumnElement

from app.modules.accounts.models import User

#: 낱말은 이만큼까지 — 그 뒤는 버린다(한 줄에 스무 낱말을 치는 사람은 없고, 조건이 끝없이
#: 길어지는 것을 막는다).
MAX_WORDS = 8


def words(query: str) -> list[str]:
    """공백으로 나눈 낱말들 — 빈 것은 뺀다."""
    return [one for one in (query or "").split() if one][:MAX_WORDS]


def pattern(word: str) -> str:
    """`ILIKE` 무늬 — 와일드카드를 글자로 묶는다(Postgres 의 기본 이스케이프는 `\\`)."""
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def matches(
    query: str,
    *,
    columns: Sequence[Any],
    tags: Any | None = None,
    owner: Any | None = None,
    also: Sequence[Callable[[str], ColumnElement[bool]]] = (),
) -> ColumnElement[bool] | None:
    """`q` 를 WHERE 절로. 낱말이 없으면 None(거르지 않는다).

    `columns` 는 글자 칸(이름 · 설명), `tags` 는 JSONB 꼬리표 목록(글자로 바꿔 본다 —
    `(tags::text)` 색인과 같은 식), `owner` 는 만든 사람 id 칸(표시 이름을 본다), `also` 는
    낱말의 무늬를 받아 조건을 돌려주는 함수들(목록마다 덧붙이는 것)."""
    found = words(query)
    if not found:
        return None
    per_word: list[ColumnElement[bool]] = []
    for word in found:
        like = pattern(word)
        options: list[ColumnElement[bool]] = [column.ilike(like) for column in columns]
        if tags is not None:
            options.append(cast(tags, Text).ilike(like))
        if owner is not None:
            options.append(
                exists(
                    select(literal(1)).where(User.id == owner, User.display_name.ilike(like))
                )
            )
        options.extend(one(like) for one in also)
        per_word.append(or_(*options))
    return and_(*per_word)
