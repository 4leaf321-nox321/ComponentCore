"""공통 — 숫자 칸 · 오류 · 바탕 모델 · 선택 그룹 · 단위 · 좌표계 · 「전체」 바디.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core import units as unit_systems


def _extra(values: dict[str, Any]) -> dict[str, Any]:
    """칸에 붙이는 사양표 표시(`json_schema_extra`). 라벨표 · 종류 목록을 dict 리터럴로 바로
    넣으면 mypy 가 Pydantic 의 `JsonDict`(값이 JsonValue)와 dict 불변성으로 막는다 — `Any` 로
    한 번 거친다. 모양은 같다."""
    return values


#: 숫자 칸 — 수 또는 `"=식"`.
Number = float | int | str
#: 정수 칸(모드 수 · 단계 수 …) — 정수 또는 `"=식"`. 식은 설계점마다 풀려 정수여야 한다
#: (`_integerized`). 식이 아닌 글자(`"6"`)는 정수로 읽는다.
Integer = int | str


def _integer_or_expr(value: Any) -> Any:
    if isinstance(value, str) and not value.startswith("="):
        try:
            return int(value)
        except ValueError as failure:
            raise ValueError(f"정수 또는 ‘=식’이어야 합니다: {value!r}") from failure
    return value


class ConditionError(ValueError):
    """조건이 말이 안 된다 — 어느 줄의 무엇이 문제인지 말한다."""


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 선택 그룹 ─────────────────────────────────────────────────────────────────

#: 선택 그룹의 종류 → 질의(`query.select_features`)가 고르는 것. 바디 그룹은 면으로 풀지
#: 않는다.
ENTITY_WHAT: dict[str, str] = {"face": "faces", "edge": "edges", "vertex": "vertices"}


def selection_query(entity: str, select: dict[str, Any]) -> dict[str, Any]:
    """선택 그룹의 규칙을 **선언한 종류대로** 푸는 질의 — 규칙에 `what` 이 없으면 `entity`
    로 채운다(`{"any": [...]}` 면 항목마다).

    질의의 기본은 **엣지**다. 그래서 면으로 선언한 그룹(`entity: face`, `{"role": "bottom"}`)
    이 내보낼 때 엣지 지문으로 나가 해석 쪽이 면 조건을 못 걸었다(SimEngBay 보고,
    2026-10-05). 화면은 늘 `what` 을 적지만 MCP · API 로 쓴 규칙은 빠질 수 있다. 빈 규칙은
    그대로 둔다 — 「아직 안 골랐다」 를 「전부」 로 바꾸지 않는다."""
    what = ENTITY_WHAT.get(entity)
    if what is None or not select:
        return dict(select)

    def filled(rule: Any) -> Any:
        return (
            {**rule, "what": what} if isinstance(rule, dict) and "what" not in rule else rule
        )

    members = select.get("any")
    if isinstance(members, list):
        return {**select, "any": [filled(one) for one in members]}
    return dict(filled(select))


class NamedSelection(Base):
    """선택 그룹 — 조건이 붙는 **유일한 창구**. 셀렉터로 적고 설계점마다 다시 푼다."""

    name: str = Field(min_length=1, max_length=60)
    entity: Literal["face", "edge", "vertex", "body"] = "face"
    select: dict[str, Any] = Field(default_factory=dict)
    """`query.find_features` 의 질의. `body` 면 `topology.bodies` 의 이름을 가리킨다 — 면 ·
    엣지 · 점 그룹에서는 **그 바디의 것만** 거른다(조립에서 좌표 없이 「블록의 아랫면」).
    `near` 는 가장 가까운 하나, `near` 가 없으면 맞는 것 전부다.

    **여럿을 묶으면 `{"any": [셀렉터, …]}`** — 3D 에서 Ctrl · Shift 로 하나씩 고른 것들의
    합이다(`query.select_features`). 고른 것마다 제 규칙을 두므로 치수를 바꿔도 같은 것들을
    가리킨다."""

    @field_validator("select")
    @classmethod
    def _members(cls, value: dict[str, Any]) -> dict[str, Any]:
        members = value.get("any")
        if members is None:
            return value
        if not isinstance(members, list) or not members:
            raise ValueError("select.any는 셀렉터를 하나 이상 포함한 목록이어야 합니다.")
        if not all(isinstance(one, dict) for one in members):
            raise ValueError("select.any의 항목은 셀렉터(객체)여야 합니다.")
        # **한 그룹은 한 종류다** — 면과 엣지를 섞으면 받는 쪽이 지문을 어느 쪽으로 짝지을지
        # 모른다. 바디(`body`)는 `what` 이 없다.
        kinds = {str(one.get("what", "body" if "body" in one else "faces")) for one in members}
        if len(kinds) > 1:
            raise ValueError(
                f"select.any의 셀렉터는 한 종류여야 합니다(현재: {', '.join(sorted(kinds))})."
            )
        return value

    @model_validator(mode="after")
    def _same_kind(self) -> NamedSelection:
        """선언한 종류와 규칙이 고르는 것이 어긋나면 막는다 — 면 그룹인데 `what: edges` 면
        해석 쪽이 면 조건을 엣지에 걸려다 실패한다. `what` 이 없으면 종류에서 채운다
        (`selection_query`)."""
        want = ENTITY_WHAT.get(self.entity)
        if want is None:
            return self
        members = self.select.get("any")
        rules = members if isinstance(members, list) else [self.select]
        given = {str(one["what"]) for one in rules if isinstance(one, dict) and "what" in one}
        if given - {want}:
            raise ValueError(
                f"선택 그룹 ‘{self.name}’은(는) {self.entity} 그룹인데 규칙이 "
                f"{', '.join(sorted(given))}을(를) 고릅니다. entity와 select.what을 "
                "맞추십시오."
            )
        return self


#: 바디 이름 대신 쓰는 말 — **모든 바디.** 단품은 바디가 이것 하나다(`topology.bodies`).
ALL_BODIES = "전체"


def applied_bodies(value: Any) -> list[str]:
    """`apply_to` 를 **목록으로** — 옛 값(문자열 하나)도 읽는다. 같은 이름은 한 번만.

    2026-09-24 까지는 문자열 하나였다. 저장된 조건 · DOE 스냅샷에는 그 모양이 남아 있으므로
    읽는 곳마다 이것을 거친다."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list) and all(isinstance(one, str) for one in value):
        return list(dict.fromkeys(one for one in value if one.strip()))
    return []


class Units(Base):
    """**계 하나만 고른다.** 나머지 단위는 거기서 계산한다(`core/units.py`).

    낱낱이 적게 두면 **닫히지 않는 계**를 적을 수 있다 — 예전 기본값이 `mm · kg · s · N` 이
    었는데, mm·kg·s 에서 힘은 N 이 아니라 **mN** 이고 응력은 kPa 다. 아무도 안 볼 때까지
    아무 일도 안 일어나다가 어느 날 10³ 배 틀린다. 그래서 고를 수 있는 것은 **계 이름뿐**이다.
    """

    system: Literal["mm_n_tonne", "si"] = unit_systems.DEFAULT_SYSTEM  # type: ignore[assignment]
    """**내보내기** 단위계 — `mm_n_tonne`(기본) 또는 `si`. 점 파일의 값을 이 계로 옮긴다.
    조건의 값은 늘 mm · N · t 로 적는다(`INPUT_SYSTEM`)."""


#: 조건의 `cs` 가 **전역**을 뜻하는 이름.
GLOBAL_FRAMES = {"global", "전역"}


class Frame(Base):
    """좌표계 — 조건의 `cs` 가 가리킨다(`core/frames.py`).

    세 가지로 정한다: **원점 · X · Y 방향**, **원점 · 회전**(둘 다 수치 또는 `"=식"` —
    실험계획의 변수를 따라간다), 또는 **선택 그룹의 면에 붙이기**(`on` — 원점 = 면 중심,
    Z = 법선, 설계점마다 그 면을 따라간다). `on` 이 있으면 나머지는 쓰지 않고, `x_axis` 가
    있으면 `rotate` 는 쓰지 않는다."""

    name: str = Field(min_length=1, max_length=40)
    origin: tuple[Number, Number, Number] = (0.0, 0.0, 0.0)
    x_axis: tuple[Number, Number, Number] | None = None
    """X 방향 — 비우면 전역 X."""
    y_axis: tuple[Number, Number, Number] | None = None
    """Y 방향 — X 에 수직이 아니어도 된다(수직으로 맞춘다). Z 는 X 와 Y 의 외적."""
    rotate: tuple[Number, Number, Number] | None = None
    """회전 — X → Y → Z 고정 축 순서(도). `x_axis` 가 없을 때 쓴다."""
    on: str = ""


#: **입력 단위계** — 조건의 값은 늘 이 계로 적는다(도면과 같은 mm). 조건의 `units.system` 은
#: **내보내기 단위계**다: 점 파일을 만들 때만 그 계로 옮긴다. 화면 · 식 · 도면 치수가 한 계라
#: 섞일 일이 없다(「SI 를 골랐는데 왜 mm 가 보이지」 — 2026-09-28 에 이렇게 바꿨다).
INPUT_SYSTEM = "mm_n_tonne"
