"""해석 조건 — **솔버를 모르는 중립 표현.**

경계조건 · 하중 · 접촉 · 초기조건 · 해석 설정 · 물성을 한 벌로 적는다. 이 플랫폼은 메시도
솔브도 하지 않고 결과도 받지 않는다 — 조건을 **파일로 넘기는 데까지**가 일이다. 받는 쪽이
하나가 아니므로(Ansys · 그 밖) 여기 적힌 말은 어느 솔버의 것도 아니어야 하고, 솔버별 매핑은
받는 쪽이 들고 있다. 설계는 `docs/해석-조건-설계.md`.

## 조건은 면을 직접 가리키지 않는다

모든 조건은 **선택 그룹(named_selections)** 만 가리킨다. 선택 그룹은 좌표가 아니라
**셀렉터**(`query.find_features` 의 말)로 적혀 있어서, 실험계획이 치수를 바꿔도 설계점마다 다시
풀린다. (화면의 말은 「선택 그룹」 이다 — 예전 문서 · 주석의 「이름표」 와 같은 것이다.)
「(30, 15, 5) 의 면」 은 두께를 바꾸는 순간 그 자리에 없지만 「아래쪽 면」 은 남는다.

그리고 같은 면에 하중과 메시 힌트를 따로 걸어도 **고칠 자리가 하나**다.

## 숫자 칸에는 식을 쓸 수 있다

레시피와 **같은 자리, 같은 문법**이다 — `"=압력"` · `"=두께 * 120"`. 변수는 레시피의
`params` 를 그대로 쓰므로, 실험계획이 그 변수를 훑으면 **형상과 조건이 함께 움직인다.**
푸는 것은 `core/recipe/params.resolve()` — dict 를 훑는 함수라 조건에도 그대로 듣는다.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core import units as unit_systems
from app.core.recipe.params import ExpressionError, names_in, resolve_params
from app.core.recipe.params import evaluate_expression as _expr

#: 숫자 칸 — 수 또는 `"=식"`.
Number = float | int | str


class ConditionError(ValueError):
    """조건이 말이 안 된다 — 어느 줄의 무엇이 문제인지 말한다."""


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 선택 그룹 ─────────────────────────────────────────────────────────────────


class NamedSelection(Base):
    """선택 그룹 — 조건이 붙는 **유일한 창구**. 셀렉터로 적고 설계점마다 다시 푼다."""

    name: str = Field(min_length=1, max_length=60)
    entity: Literal["face", "edge", "vertex", "body"] = "face"
    select: dict[str, Any] = Field(default_factory=dict)
    """`query.find_features` 의 질의. `body` 면 `topology.bodies` 의 이름을 가리킨다.

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
            raise ValueError("select.any 는 셀렉터를 하나 이상 담은 목록이어야 합니다")
        if not all(isinstance(one, dict) for one in members):
            raise ValueError("select.any 의 항목은 셀렉터(객체)여야 합니다")
        # **한 그룹은 한 종류다** — 면과 엣지를 섞으면 받는 쪽이 지문을 어느 쪽으로 짝지을지
        # 모른다. 바디(`body`)는 `what` 이 없다.
        kinds = {str(one.get("what", "body" if "body" in one else "faces")) for one in members}
        if len(kinds) > 1:
            raise ValueError(
                f"select.any 의 셀렉터는 한 종류여야 합니다(지금: {', '.join(sorted(kinds))})"
            )
        return value


# ── 물성 ──────────────────────────────────────────────────────────────────────


class MaterialRef(Base):
    source: str = "matnexus"
    code: str = ""
    """MatNexus 의 불변 번호(`M-000123`). 손입력이면 비어 있다."""
    material_id: str = ""
    """그쪽의 UUID. **덱을 뽑을 때 이것이 필요하다** — 번호로는 카드를 못 찾는다.
    문헌 재료는 번호가 없는 것이 많아 이 칸이 유일한 손잡이일 때도 있다."""
    name: str = ""
    fetched_at: str = ""


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


class Material(Base):
    """**값을 해석하지 않는다.** 물성 플랫폼이 준 것을 통째로 나른다 — 「어느 것이 영률인가」
    는 솔버를 아는 쪽의 일이다(설계 문서 6장)."""

    apply_to: list[str] = Field(default_factory=lambda: [ALL_BODIES])
    """이 물성이 붙은 **바디들**(`topology.bodies` 의 이름). 「전체」 면 모든 바디.

    **비어 있으면 아직 아무 데도 안 붙은 것이다.** 조건 화면은 재료를 먼저 몇 개 담아 두고
    파트마다 고르게 하므로, 담았지만 아직 안 고른 재료가 있다 — 그 재료로는 덱을 안 뽑는다.

    예전에는 문자열 하나였다. 파트 셋에 같은 재료를 주려면 같은 재료를 세 번 담아야 했고,
    그러면 덱의 재료 번호(`mid`)도 셋이 되어 받는 쪽이 같은 재료인지 알 수 없었다."""
    ref: MaterialRef = Field(default_factory=MaterialRef)
    payload: dict[str, Any] = Field(default_factory=dict)
    """물성 플랫폼이 준 것 **그대로.** 저장할 때도 내보낼 때도 우리가 손대지 않는다 —
    이것이 감사의 정본이다."""
    deck_formats: list[str] = Field(default_factory=list)
    """**함께 내보낼 솔버 덱**(`ansys` · `nastran` · `dyna_elastic` …). 비면 안 만든다.

    중립 payload 를 **대신하지 않고 덤으로** 간다. 받는 쪽이 제 솔버 덱을 손으로 짜는 대신
    그대로 쓸 수 있고, 우리 계약은 여전히 솔버를 모른다 — 어느 형식을 담을지는 **사람이나
    오케스트레이터가 고른다.**

    글월은 여기 안 담는다. **내보낼 때 그때 뽑는다** — 재료가 여럿이면 덱 안의 재료 번호
    (`mid`)가 서로 달라야 하는데, 그 번호는 한 벌이 다 모여야 정해진다."""

    @field_validator("apply_to", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        # 목록이 아닌 이상한 값은 그대로 넘겨 Pydantic 이 「무엇이 틀렸나」 를 말하게 한다.
        if isinstance(value, str) or (
            isinstance(value, list) and all(isinstance(one, str) for one in value)
        ):
            return applied_bodies(value)
        return value


# ── 조건들 ────────────────────────────────────────────────────────────────────


#: 화면에 주는 표시 — **성분 칸**(방향마다 자유 · 고정(· 변위량) 중 고른다), 그리고 그 칸을
#: 쓰는 종류(`only_for`). 다른 종류면 화면이 그리지 않고, 종류를 바꾸면 기본값으로 되돌린다.
#: `dimension` — 값의 단위가 단위계의 어느 이름인가(화면이 「변위량 (m)」 로 붙인다), `unit` —
#: 계와 상관없는 단위.
_DISPLACEMENT: dict[str, Any] = {
    "component": True,
    "only_for": ["displacement", "remote_displacement"],
    "dimension": "length",
}
_ROTATION: dict[str, Any] = {
    "component": True,
    "only_for": ["remote_displacement"],
    "unit": "도",
}
_CYLINDER: dict[str, Any] = {"component": True, "only_for": ["cylindrical"]}

Hold = Literal["fixed", "free"]

#: 종류가 **스스로 정하는** 방향 — 고칠 수 없지만 화면이 잠긴 칸으로 보여 준다. 어느 방향이
#: 어떻게 잡히는지 모르고 고르면, 풀리지 않는 모델(강체 운동)이나 과구속을 만든다.
IMPLIED_HOLDS: dict[str, list[dict[str, str]]] = {
    "fixed_support": [
        {"label": "X", "hold": "fixed", "hint": "모든 이동을 막는다 — 좌표계와 상관없다"},
        {"label": "Y", "hold": "fixed", "hint": ""},
        {"label": "Z", "hold": "fixed", "hint": ""},
        {
            "label": "회전",
            "hold": "fixed",
            "hint": "셸 · 빔이면 회전도 막는다(솔리드는 회전이 없다)",
        },
    ],
    "frictionless": [
        {
            "label": "법선",
            "hold": "fixed",
            "hint": "면에 수직 — 뚫고 들어가지도, 떨어지지도 못한다",
        },
        {"label": "접선", "hold": "free", "hint": "면을 따라 두 방향 — 마찰 없이 미끄러진다"},
    ],
    "compression_only": [
        {"label": "누르는 쪽", "hold": "fixed", "hint": "법선 방향으로 면을 파고들지 못한다"},
        {
            "label": "떨어지는 쪽",
            "hold": "free",
            "hint": "면에서 들뜰 수 있다(비선형 — 반복해 푼다)",
        },
        {"label": "접선", "hold": "free", "hint": "면을 따라 마찰 없이 미끄러진다"},
    ],
    "elastic_support": [
        {"label": "법선", "hold": "spring", "hint": "면에 수직 — 기초 강성만큼 버티며 눌린다"},
        {"label": "접선", "hold": "free", "hint": "면을 따라서는 받치지 않는다"},
    ],
}


CONSTRAINT_LABELS: dict[str, str] = {
    "fixed_support": "고정 지지",
    "displacement": "변위",
    "remote_displacement": "원격 변위",
    "frictionless": "마찰 없는 지지",
    "cylindrical": "원통 지지",
    "compression_only": "압축 전용 지지",
    "elastic_support": "탄성 지지",
}

#: 종류마다 한 줄 — 화면이 종류 아래에 보인다.
CONSTRAINT_NOTES: dict[str, str] = {
    "fixed_support": "완전히 붙박습니다 — 볼트로 꽉 조인 바닥, 용접된 끝.",
    "displacement": (
        "방향마다 자유 · 고정 · 변위량을 정합니다 — 한쪽만 받치거나 정해진 만큼 밉니다."
    ),
    "remote_displacement": (
        "면을 한 점에 묶고 그 점의 이동 · 회전을 잡습니다 — 축 둘레로 돌게 둘 때."
    ),
    "frictionless": "면에 수직으로만 막고 미끄러짐은 풉니다 — 대칭면, 매끈한 바닥.",
    "cylindrical": "구멍 · 축을 반지름 · 축 · 접선마다 막거나 풉니다 — 핀에 끼운 구멍.",
    "compression_only": "누르는 쪽만 받치고 들뜨는 것은 둡니다 — 그냥 올려 둔 부품(비선형).",
    "elastic_support": "면을 스프링으로 받칩니다 — 고무 패드, 지반.",
}


class Constraint(Base):
    """구속 — 움직이지 못하게 한다.

    방향을 누가 정하나: `displacement` 는 좌표계(`cs`)의 X · Y · Z 마다, `remote_displacement`
    는 거기에 회전 X · Y · Z 까지, `cylindrical` 은 원통의 반지름 · 축 · 접선마다 사람이
    고른다. 나머지는 종류가 정한다(`IMPLIED_HOLDS`)."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal[
        "fixed_support",
        "displacement",
        "remote_displacement",
        "frictionless",
        "cylindrical",
        "compression_only",
        "elastic_support",
    ] = Field(json_schema_extra={"labels": CONSTRAINT_LABELS})
    on: str
    cs: str = Field(
        "global", json_schema_extra={"only_for": ["displacement", "remote_displacement"]}
    )
    """성분의 축 — 변위 · 원격 변위만 쓴다(원통 지지는 원통의 축을, 나머지는 면을
    따른다). 원격 변위는 이 좌표계의 **원점**을 원격점으로 쓸 수도 있다(`location`)."""
    location: Literal["centroid", "cs_origin"] = Field(
        "centroid",
        title="원격점",
        description="면을 묶는 한 점 — 고른 면의 중심, 또는 좌표계의 원점",
        json_schema_extra={
            "only_for": ["remote_displacement"],
            "labels": {"centroid": "선택 그룹의 중심", "cs_origin": "좌표계의 원점"},
        },
    )
    behavior: Literal["deformable", "rigid"] = Field(
        "deformable",
        title="면의 거동",
        description=(
            "변형체: 면이 따라 휘어진다 · 강체: 면이 모양을 지킨 채 움직인다(더 뻣뻣하다)"
        ),
        json_schema_extra={
            "only_for": ["remote_displacement"],
            "labels": {"deformable": "변형체", "rigid": "강체"},
        },
    )
    x: Number | None = Field(
        None, title="X", description="좌표계의 X 축 방향", json_schema_extra=_DISPLACEMENT
    )
    y: Number | None = Field(
        None, title="Y", description="좌표계의 Y 축 방향", json_schema_extra=_DISPLACEMENT
    )
    z: Number | None = Field(
        None, title="Z", description="좌표계의 Z 축 방향", json_schema_extra=_DISPLACEMENT
    )
    """`displacement` · `remote_displacement` 의 이동 성분. **`null` 은 자유, 0 은 고정**, 그
    밖의 값은 그만큼 움직인다.

    화면은 빈칸 · 0 을 묵시적으로 읽게 두지 않고 「자유 · 고정 · 변위량」 을 고르게 한다
    (`component`) — 둘을 헷갈리면 구속이 통째로 바뀐다."""
    rx: Number | None = Field(
        None, title="회전 X", description="X 축 둘레 회전(도)", json_schema_extra=_ROTATION
    )
    ry: Number | None = Field(
        None, title="회전 Y", description="Y 축 둘레 회전(도)", json_schema_extra=_ROTATION
    )
    rz: Number | None = Field(
        None, title="회전 Z", description="Z 축 둘레 회전(도)", json_schema_extra=_ROTATION
    )
    """`remote_displacement` 의 회전 성분(도) — 뜻은 이동과 같다(`null` 자유 · 0 고정)."""
    stiffness: Number | None = Field(
        None,
        title="기초 강성",
        description=(
            "법선으로 단위 길이 눌리는 데 드는 압력 — mm · N · t 계면 N/mm³, SI 면 N/m³"
        ),
        json_schema_extra={"only_for": ["elastic_support"]},
    )
    """`elastic_support` 의 스프링 — 단위 면적 · 단위 변위당 힘(응력 / 길이)."""
    radial: Hold = Field(
        "fixed",
        title="반지름",
        description="원통 중심에서 바깥쪽 — 구멍이 커지거나 줄어드는 방향",
        json_schema_extra=_CYLINDER,
    )
    axial: Hold = Field(
        "fixed",
        title="축",
        description="원통 축을 따라 — 빠지거나 밀려 들어가는 방향",
        json_schema_extra=_CYLINDER,
    )
    tangential: Hold = Field(
        "fixed",
        title="접선",
        description="원통 축 둘레로 도는 방향 — 풀면 핀에 끼운 채 돈다",
        json_schema_extra=_CYLINDER,
    )
    """`cylindrical` 의 방향마다 고정(`fixed`) · 자유(`free`). 기본은 셋 다 고정."""


#: 하중 종류 → 크기의 차원(단위계 이름표의 열쇠). 화면은 「크기 (MPa)」 로 붙이고, 조건을 풀 때
#: `unit` 을 이것으로 채운다 — 사람이 단위를 손으로 적으면 계와 어긋나도 아무도 모른다.
LOAD_DIMENSIONS: dict[str, str] = {
    "pressure": "stress",
    "force": "force",
    "moment": "moment",
    "bearing": "force",
    "acceleration": "acceleration",
    "rotational_velocity": "angular_velocity",
}

#: 몸 전체에 걸리는 하중 — 선택 그룹이 없다.
BODY_LOADS = ("standard_earth_gravity", "acceleration", "rotational_velocity")

#: 방향이 있는 하중(벡터). 압력만 「면의 법선」 을 고를 수 있다.
DIRECTED_LOADS = [
    "pressure",
    "force",
    "moment",
    "bearing",
    "standard_earth_gravity",
    "acceleration",
    "rotational_velocity",
]

#: 종류마다 한 줄 — 화면이 종류 아래에 보인다(무엇이고, 방향이 무엇을 뜻하나).
LOAD_NOTES: dict[str, str] = {
    "pressure": "면에 고르게 누르는 힘. 면의 법선이면 양수가 면을 누르는 쪽입니다.",
    "force": "합계 힘 — 여러 면에 걸면 나눠 가집니다(면마다 이 크기가 아닙니다).",
    "moment": "비트는 힘. 방향은 회전축이고, 오른손 법칙으로 돕니다.",
    "bearing": "구멍 안쪽을 핀이 미는 힘 — 방향 쪽 반원에만 걸립니다. 원통면에 겁니다.",
    "bolt_pretension": "볼트를 조입니다 — 먼저 조이고, 그 길이를 잠근 채 다른 하중을 겁니다.",
    "standard_earth_gravity": "모든 바디의 자중(9.80665 m/s²). 밀도가 있어야 걸립니다.",
    "acceleration": "모델이 이 방향으로 가속됩니다 — 관성력은 반대쪽으로 걸립니다. 밀도 필요.",
    "rotational_velocity": "좌표계 원점을 지나는 축 둘레로 돕니다(원심력). 밀도 필요.",
}

LOAD_LABELS: dict[str, str] = {
    "pressure": "압력",
    "force": "힘",
    "moment": "모멘트",
    "bearing": "베어링 하중",
    "bolt_pretension": "볼트 예압",
    "standard_earth_gravity": "중력",
    "acceleration": "가속도",
    "rotational_velocity": "회전 속도",
}


class Load(Base):
    """하중 — 밀거나 당기거나 조인다.

    크기의 단위는 **단위계가 정한다**(`LOAD_DIMENSIONS`) — 적지 않으면 풀 때 채우고, 적었는데
    계와 다르면 막는다. 볼트만 예압(힘) · 조임량(길이)을 `unit` 으로 고른다."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal[
        "pressure",
        "force",
        "moment",
        "bearing",
        "bolt_pretension",
        "standard_earth_gravity",
        "acceleration",
        "rotational_velocity",
    ] = Field(json_schema_extra={"labels": LOAD_LABELS})
    on: str = Field(
        "",
        json_schema_extra={
            "only_for": ["pressure", "force", "moment", "bearing", "bolt_pretension"]
        },
    )
    """중력처럼 온 몸에 걸리는 것은 비어 있다."""
    cs: str = Field("global", json_schema_extra={"only_for": DIRECTED_LOADS})
    """방향 성분의 축 — 구속과 같다. 회전 속도는 이 좌표계의 원점을 지나는 축으로 돈다."""
    magnitude: Number | None = Field(
        None,
        title="크기",
        json_schema_extra={
            "only_for": [
                k
                for k in LOAD_LABELS
                if k not in ("bolt_pretension", "standard_earth_gravity")
            ],
            "unit_by_type": True,
        },
    )
    unit: str = Field("", json_schema_extra={"hidden": True})
    """`MPa` · `N` · `N*mm` … **단위를 값에서 떼지 않는다** — 물성에서 그것이 10¹² 배로
    틀린 적이 있다(MatNexus 의 실측). 비우면 단위계에서 채운다."""
    direction: list[Number] | Literal["normal"] | None = Field(
        None,
        title="방향",
        json_schema_extra={
            "direction": True,
            "only_for": DIRECTED_LOADS,
            "normal_for": ["pressure"],
        },
    )
    """좌표계(`cs`)의 X · Y · Z 성분(길이는 상관없다), 또는 `"normal"`(면의 법선 — 압력만).
    비우면 압력은 법선, 중력은 -Z 다."""
    preload: Number | None = Field(
        None, title="예압", json_schema_extra={"only_for": ["bolt_pretension"], "bolt": True}
    )
    """`bolt_pretension` — 예압(힘) 또는 조임량(길이), `unit` 이 가른다."""


class Contact(Base):
    """접촉 — 두 선택 그룹이 만나는 자리."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal["bonded", "no_separation", "frictional", "frictionless", "rough"]
    source: str
    target: str
    friction: Number | None = None
    formulation: str = ""
    behavior: str = ""
    pinball: Number | None = None
    interface_treatment: str = ""


class Initial(Base):
    """초기조건 — 풀기 전의 상태."""

    type: Literal["environment_temperature", "velocity", "temperature", "prestress"]
    on: str = ""
    value: Number | None = None
    vector: list[Number] | None = None
    unit: str = ""
    from_step: str = ""


class Analysis(Base):
    """무엇을 풀 것인가."""

    type: Literal["modal", "static", "harmonic", "explicit", "thermal"] = "modal"
    prestressed: bool = False
    modes: int | None = None
    frequency_range: list[Number] | None = None
    large_deflection: bool = False


class MeshHint(Base):
    """메시는 받는 쪽이 만든다 — 여기 적는 것은 **바람**이다."""

    on: str = "전체"
    element_size: Number | None = None
    method: str = ""
    order: str = ""
    inflation_layers: int | None = None
    defeature_size: Number | None = None


class Units(Base):
    """**계 하나만 고른다.** 나머지 단위는 거기서 계산한다(`core/units.py`).

    낱낱이 적게 두면 **닫히지 않는 계**를 적을 수 있다 — 예전 기본값이 `mm · kg · s · N` 이
    었는데, mm·kg·s 에서 힘은 N 이 아니라 **mN** 이고 응력은 kPa 다. 아무도 안 볼 때까지
    아무 일도 안 일어나다가 어느 날 10³ 배 틀린다. 그래서 고를 수 있는 것은 **계 이름뿐**이다.
    """

    system: Literal["mm_n_tonne", "si"] = unit_systems.DEFAULT_SYSTEM  # type: ignore[assignment]
    """`mm_n_tonne`(기본 — CAD 가 mm 라 해석도 mm) 또는 `si`."""


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


class Conditions(Base):
    """한 벌. 작업 버전에 붙고, 실험계획이 스냅샷을 뜬다."""

    schema_version: Literal[1] = 1
    units: Units = Field(default_factory=Units)
    named_selections: list[NamedSelection] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    loads: list[Load] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    initial: list[Initial] = Field(default_factory=list)
    analysis: Analysis = Field(default_factory=Analysis)
    mesh_hints: list[MeshHint] = Field(default_factory=list)
    coordinate_systems: list[Frame] = Field(default_factory=list)
    """해석 조건에서 정한 좌표계. 도면(레시피)의 좌표계와 **이름이 겹치면 안 된다** — 둘 다
    `cs` 가 이름으로 가리킨다."""


EMPTY: dict[str, Any] = Conditions().model_dump()


# ── 검증 ──────────────────────────────────────────────────────────────────────


def _known_names(conditions: Conditions) -> set[str]:
    return {one.name for one in conditions.named_selections}


def parse(
    raw: dict[str, Any] | None,
    bodies: list[str] | None = None,
    frames: list[str] | None = None,
) -> Conditions:
    """읽어서 검증한다. **틀린 자리를 짚어 말한다** — 「조건이 잘못됐습니다」 로는 못 고친다.

    `bodies` 를 주면 **물성이 붙은 바디가 진짜 있는지**도 본다(`topology.bodies` 의 이름).
    없는 이름에 물성을 붙이면 해석 쪽이 그 바디에 아무 물성도 못 얹고, 그 사실은 푸는
    날에야 드러난다 — 이름표를 가리킬 때와 같은 까닭이다.

    `frames` 는 도면(레시피)의 좌표계 이름들 — 주면 조건의 `cs` 가 **있는 좌표계**를
    가리키는지 본다. 안 주면 조건 안의 좌표계만 알고, 모르는 이름은 넘어간다(도면을 못 보는
    자리에서 저장을 막지 않으려고).
    """
    if not raw:
        return Conditions()
    try:
        conditions = Conditions.model_validate(raw)
    except ValidationError as failure:
        first = failure.errors()[0]
        where = ".".join(str(one) for one in first["loc"])
        raise ConditionError(f"{where}: {first['msg']}") from failure

    names = _known_names(conditions)
    if len(names) != len(conditions.named_selections):
        raise ConditionError(
            "선택 그룹 이름이 겹칩니다 — 조건이 어느 것을 가리킬지 알 수 없습니다"
        )

    # **가리키는 선택 그룹이 없으면 지금 말한다.** 안 그러면 내보낸 뒤 해석 쪽에서 0 개를 집고,
    # 하중 없는 해석이 끝까지 돈다.
    for group, items in (
        ("constraints", conditions.constraints),
        ("loads", conditions.loads),
        ("contacts", conditions.contacts),
        ("initial", conditions.initial),
        ("mesh_hints", conditions.mesh_hints),
    ):
        for index, item in enumerate(items):
            targets = []
            if isinstance(item, Contact):
                targets = [item.source, item.target]
            else:
                on = getattr(item, "on", "")
                targets = [on] if on and on != "전체" else []
            for target in targets:
                if target not in names:
                    raise ConditionError(
                        f"{group}[{index}]: 「{target}」 라는 선택 그룹이 없습니다 "
                        f"(있는 것: {', '.join(sorted(names)) or '없음'})"
                    )

    # **좌표계** — 이름이 겹치지 않고, 면에 붙인 것은 있는 선택 그룹을 가리키고, 조건의
    # `cs` 는 있는 좌표계를 가리킨다. 모르는 좌표계를 조용히 전역으로 읽으면 성분이 딴
    # 방향으로 걸린다.
    local = [one.name for one in conditions.coordinate_systems]
    for index, frame in enumerate(conditions.coordinate_systems):
        if frame.name in GLOBAL_FRAMES:
            raise ConditionError(
                f"coordinate_systems[{index}]: 「{frame.name}」 은 전역 좌표계의 이름입니다"
            )
        if local.count(frame.name) > 1 or frame.name in (frames or []):
            raise ConditionError(
                f"coordinate_systems[{index}]: 좌표계 「{frame.name}」 이 겹칩니다 "
                "(도면의 좌표계와도 이름이 달라야 합니다)"
            )
        if frame.on and frame.on not in names:
            raise ConditionError(
                f"coordinate_systems[{index}]: 「{frame.on}」 라는 선택 그룹이 없습니다"
            )
    known_frames = GLOBAL_FRAMES | set(local) | set(frames or [])
    for index, item in enumerate(conditions.constraints):
        if item.type == "elastic_support" and item.stiffness is None:
            raise ConditionError(
                f"constraints[{index}]: 탄성 지지 「{item.name}」 에 기초 강성이 없습니다"
            )
        if (
            item.type == "remote_displacement"
            and item.location == "cs_origin"
            and item.cs in GLOBAL_FRAMES
        ):
            raise ConditionError(
                f"constraints[{index}]: 「{item.name}」 의 원격점을 좌표계의 원점으로 두려면 "
                "좌표계를 고르세요 — 전역의 원점은 모델과 상관없는 자리입니다"
            )
        if frames is not None and item.cs not in known_frames:
            raise ConditionError(
                f"constraints[{index}]: 「{item.cs}」 라는 좌표계가 없습니다 "
                f"(있는 것: {', '.join(sorted(known_frames - GLOBAL_FRAMES)) or '없음'})"
            )

    for index, load in enumerate(conditions.loads):
        _check_load(f"loads[{index}]", load, conditions.units.system)
        if frames is not None and load.cs not in known_frames:
            raise ConditionError(
                f"loads[{index}]: 「{load.cs}」 라는 좌표계가 없습니다 "
                f"(있는 것: {', '.join(sorted(known_frames - GLOBAL_FRAMES)) or '없음'})"
            )

    # **물성이 붙은 바디가 진짜 있나.** 「전체」 는 늘 된다(모든 바디).
    known = set(bodies) if bodies is not None else None
    owner: dict[str, int] = {}
    for index, material in enumerate(conditions.materials):
        for where in material.apply_to:
            if known is not None and where != ALL_BODIES and where not in known:
                raise ConditionError(
                    f"materials[{index}]: 「{where}」 라는 바디가 없습니다 "
                    f"(있는 것: {', '.join(sorted(known)) or '없음'})"
                )
            # **바디 하나에 물성 하나.** 둘이면 해석 쪽이 어느 것으로 풀지 모른다 — 먼저 온
            # 것을 쓰든 나중 것을 쓰든, 사람이 고른 것과 다를 수 있다.
            if where in owner:
                raise ConditionError(
                    f"materials[{index}]: 「{where}」 에 물성이 둘 붙었습니다 — "
                    f"materials[{owner[where]}] 와 겹칩니다. "
                    "바디 하나에는 물성 하나만 붙습니다."
                )
            owner[where] = index
    if ALL_BODIES in owner and len(owner) > 1:
        other = next(name for name in owner if name != ALL_BODIES)
        raise ConditionError(
            f"materials[{owner[ALL_BODIES]}] 이 「{ALL_BODIES}」 에 붙어 있는데 "
            f"materials[{owner[other]}] 이 「{other}」 에 또 붙었습니다 — "
            f"「{other}」 에 물성이 둘이 됩니다."
        )
    return conditions


def _points_of(one: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (one.get("points") or []) if isinstance(p, dict)]


#: **선형 탄성 해석이 필요로 하는 것.** 이 셋이 없으면 해석은 기본값(구조용 강)으로 풀고,
#: 그 사실은 고유진동수가 틀린 뒤에야 드러난다 — 고를 때 말해 주는 편이 낫다.
STRUCTURAL_KEYS: dict[str, str] = {
    "mechanical.youngs_modulus": "탄성계수",
    "mechanical.poisson_ratio": "푸아송비",
    "physical.density": "밀도",
}


def missing_structural(converted: dict[str, Any]) -> list[str]:
    """**선형 탄성으로 풀려면 빠진 것** — 사람이 읽을 이름으로. 다 있으면 빈 목록.

    문헌 카탈로그는 2663건 중 탄성계수를 가진 것이 1025건이다 — 고른 재료에 그것이
    없을 수 있다는 뜻이다."""
    있음 = {one.get("key") for one in converted.get("properties") or []}
    if converted.get("density") is not None:
        있음.add(converted.get("density_key"))
    if converted.get("poisson_ratio") is not None:
        있음.add(converted.get("poisson_key"))
    return [label for key, label in STRUCTURAL_KEYS.items() if key not in 있음]


#: 밀도 · 푸아송비의 표준 열쇠 — 등록 재료는 이 둘을 **컬럼**으로 주므로 줄에 열쇠가 없다.
#: 받는 쪽이 한 규칙으로 찾게 여기서도 같은 이름을 붙인다.
DENSITY_KEY = "physical.density"
POISSON_KEY = "mechanical.poisson_ratio"


def converted_material(
    payload: dict[str, Any], system: str, keys: dict[str, str] | None = None
) -> dict[str, Any]:
    """물성 값을 그 계로 옮긴 **나란한 한 벌.** 원본(`payload`)은 그대로 둔다.

    받는 쪽은 둘을 다 받는다: 감사할 때는 원본, 풀 때는 이것. 한쪽만 주면 「이 값이 어디서
    나왔나」 와 「그래서 무슨 단위인가」 중 하나를 잃는다.

    **못 바꾼 것은 못 바꿨다고 적는다**(`unconverted`) — 조용히 원래 값을 남기면 그것이
    새 단위인 줄 알고 그대로 푼다.

    `keys` 는 `{사람이 쓰는 이름: 표준 열쇠}`(MatNexus 물성 사전). 등록 재료의 물성 줄에는
    **기계가 읽을 이름이 없어서**(한글 라벨뿐) 이것으로 붙여 준다 — 그러면 받는 쪽이 출처를
    가리지 않고 `key` 하나로 「어느 것이 영률인가」 를 푼다. 못 붙이면 그냥 없다(덤이다).
    """
    named = keys or {}
    made: dict[str, Any] = {"system": system}
    missed: list[str] = []
    # **재료 응답의 모양이 둘이다**(MatNexus b64cd5c, 2026-09-25). 그 전: `density` 는 그쪽
    # 화면 표시값(`density_unit` = tonne/mm3)이고 SI 는 곁의 `density_si`. 그 뒤: `density`
    # 가 SI(kg/m³)이고 `density_unit` = kg/m3, `density_si` 는 없다. 저장된 조건 · DOE
    # 스냅샷에는 옛 모양이 남아 있으므로 **둘 다 읽는다** — `density_si` 가 있으면 그것,
    # 없으면 `density` 를 **`density_unit` 으로** 환산한다. `density` 의 단위를 가정하지
    # 않는 것이 두 모양을 다 푸는 유일한 길이다.
    si_density = payload.get("density_si")
    if isinstance(si_density, int | float):
        value, name, ok = unit_systems.convert(float(si_density), "kg/m3", system)
        made["density"] = value
        made["density_unit"] = name
        made["density_key"] = DENSITY_KEY
    elif isinstance(payload.get("density"), int | float):
        value, name, ok = unit_systems.convert(
            float(payload["density"]), str(payload.get("density_unit") or ""), system
        )
        made["density"] = value
        made["density_unit"] = name
        made["density_key"] = DENSITY_KEY
        if not ok:
            missed.append(f"밀도({payload.get('density_unit')})")
    if isinstance(payload.get("poisson_ratio"), int | float):
        # 무차원이라 바뀌지 않는다 — 그래도 실어 준다. 받는 쪽이 한 곳만 보면 되게.
        made["poisson_ratio"] = payload["poisson_ratio"]
        made["poisson_key"] = POISSON_KEY

    rows: list[dict[str, Any]] = []
    # **문헌 카탈로그는 값의 모양이 다르다**(`values[]` 에 `property_key` · `value_num` ·
    # `unit`). 우리가 payload 를 한 모양으로 고치지 않기로 했으므로(감사의 정본이다) 여기서
    # 둘을 받아 **한 모양으로 내놓는다** — 받는 쪽은 `converted` 하나만 보면 된다.
    for one in payload.get("values") or []:
        if not isinstance(one, dict) or not isinstance(one.get("value_num"), int | float):
            continue
        unit = str(one.get("unit") or "")
        value, unit_name, ok = unit_systems.convert(float(one["value_num"]), unit, system)
        rows.append(
            {
                "item": one.get("property_name") or one.get("property_key"),
                # 열쇠도 싣는다 — 문헌 쪽은 `mechanical.youngs_modulus` 처럼 **기계가 읽을
                # 이름**이 있다. 「어느 것이 영률인가」 를 받는 쪽이 이름으로 풀 수 있다.
                "key": one.get("property_key"),
                "unit": unit_name,
                "points": [{"temperature_C": None, "value": value}],
                # 문헌 값은 **조건과 출처가 값의 일부**다 — 「85°C/85%RH 168hr」 인 흡습률을
                # 상온 값으로 쓰면 틀린다. 등급(tier)도 그대로 나른다.
                **({"conditions": one["conditions"]} if one.get("conditions") else {}),
                **({"tier": one["quality_tier"]} if one.get("quality_tier") else {}),
                **({"representative": True} if one.get("representative") else {}),
            }
        )
        if not ok:
            missed.append(f"{one.get('property_name') or one.get('property_key')}({unit})")

    for one in payload.get("declared_properties") or []:
        if not isinstance(one, dict):
            continue
        unit = str(one.get("si_unit") or "")
        # 단위는 항목마다 하나다 — 점마다 다시 묻지 않고 한 번만 푼다.
        _, unit_name, ok = unit_systems.convert(1.0, unit, system)
        points = [
            {
                "temperature_C": point.get("temperature_C"),
                "value": unit_systems.convert(float(point["value_si"]), unit, system)[0],
            }
            for point in _points_of(one)
            if isinstance(point.get("value_si"), int | float)
        ]
        if not points:
            continue
        # **등록 재료에는 기계가 읽을 이름이 없다** — 사전으로 붙여 준다(문헌은 이미 있다).
        item = one.get("item")
        key = named.get(str(item).strip()) if item else None
        rows.append(
            {
                "item": item,
                **({"key": key} if key else {}),
                "unit": unit_name,
                "points": points,
            }
        )
        if not ok:
            missed.append(f"{one.get('item')}({unit})")
    if rows:
        made["properties"] = rows
    # **`converted` 는 한 모양이어야 한다.** 등록 재료는 밀도 · 푸아송비가 payload 의 칸으로
    # 오고 문헌은 `values[]` 안에 줄로 온다 — 그대로 두면 받는 쪽이 출처에 따라 두 군데를
    # 봐야 한다. 위에서 못 채웠으면 목록에서 끌어올린다.
    LIFT = (("density", "physical.density"), ("poisson_ratio", "mechanical.poisson_ratio"))
    for field, key in LIFT:
        if field in made:
            continue
        found = next((one for one in rows if one.get("key") == key), None)
        if found is None:
            continue
        made[field] = found["points"][0]["value"]
        made["density_key" if field == "density" else "poisson_key"] = key
        if field == "density":
            made["density_unit"] = found["unit"]
    if missed:
        made["unconverted"] = missed
    # **선형 탄성으로 풀 수 있나.** 빠진 것이 있으면 고를 때 말해 준다 — 없으면 해석이
    # 기본값(구조용 강)으로 풀고, 그 사실은 고유진동수가 틀린 뒤에야 드러난다.
    #
    # 다만 **모르는 것과 없는 것을 가른다**: 목록 한 줄에는 값이 아예 안 딸려 온다(문헌은
    # 2663건을 값째로 끌 수 없다). 그때 「다 빠졌다」 고 하면 거짓말이다 — 아직 안 봤을 뿐이다.
    if payload.get("values") is not None or payload.get("declared_properties") is not None:
        빠진것 = missing_structural(made)
        if 빠진것:
            made["missing_structural"] = 빠진것
    return made


def _with_converted(
    material: dict[str, Any], system: str, keys: dict[str, str]
) -> dict[str, Any]:
    payload = material.get("payload")
    if not isinstance(payload, dict) or not payload:
        return material
    return {**material, "converted": converted_material(payload, system, keys)}


#: 조건의 **값**이 든 곳 — 조건의 단위계로 적힌다. 선택 그룹 · 좌표계는 도면(mm)이다.
VALUE_SECTIONS = ("constraints", "loads", "contacts", "initial", "mesh_hints")


def _length_ratio(system: str) -> float:
    """mm → 이 계의 길이. mm 계면 1, SI 면 0.001."""
    return 1e-3 / unit_systems.system_of(system).length


def resolve(
    raw: dict[str, Any] | None,
    params: dict[str, Any],
    keys: dict[str, str] | None = None,
    lengths: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """`"=식"` 을 그 설계점의 값으로 바꾼 **새 사본**. 레시피와 같은 문법이다.

    받는 쪽은 식을 풀 수 없다 — 설계점마다 **풀린 값**을 내보내야 한다.

    `keys` 는 물성 이름 사전(`{사람이 쓰는 이름: 표준 열쇠}`)이다. **코어는 그것을 가져오지
    않는다** — 네트워크는 바깥 층의 일이고(아키텍처 시험이 지킨다), 여기는 받은 것으로 풀기만
    한다. 안 주면 표준 열쇠만 안 붙는다(값은 그대로 나간다).

    여기서 **단위계도 함께 푼다**: `units` 를 닫힌 선언으로 펼치고, 물성마다 그 계로 옮긴
    값(`converted`)을 **원본 옆에** 놓는다. 원본은 안 건드린다 — 감사할 때는 원본, 풀 때는
    변환값이다. MatNexus 가 밀도만 `tonne/mm3` 로 주고 나머지는 SI 로 주므로, 이것이 없으면
    받는 쪽이 밀도는 맞고 탄성계수는 10⁶ 배 틀린 채로 푼다.

    `lengths` 는 **길이인 도면 치수**의 이름들(`recipe.params.length_params`)이다. 조건의 값은
    조건의 단위계로 적으므로, 값 칸(`VALUE_SECTIONS`)의 식에서는 그 치수를 **이 계의 길이로
    옮겨** 넣는다 — SI 에서 `=두께*0.1` 의 두께 5 mm 는 0.005 m 다. 사람이 `*0.001` 을 붙이지
    않아도 된다. 선택 그룹 · 좌표계의 식은 도면 쪽이라 mm 그대로 푼다.
    """
    conditions = parse(raw).model_dump()
    values = resolve_params({"params": params})
    system = str((conditions.get("units") or {}).get("system") or unit_systems.DEFAULT_SYSTEM)
    ratio = _length_ratio(system)
    in_system = {
        name: value * ratio if name in lengths else value for name, value in values.items()
    }

    def walk(value: Any, known: dict[str, float]) -> Any:
        if isinstance(value, str) and value.startswith("="):
            return _expr(value, known)
        # 좌표계 원점 같은 세 성분은 모델에서 **튜플**로 나온다 — 목록만 훑으면 그 안의 식이
        # 안 풀린 채 나갔다(2026-09-28 에 잡았다).
        if isinstance(value, list | tuple):
            return [walk(one, known) for one in value]
        if isinstance(value, dict):
            return {key: walk(one, known) for key, one in value.items()}
        return value

    try:
        out = {
            key: walk(one, in_system if key in VALUE_SECTIONS else values)
            for key, one in conditions.items()
        }
    except ExpressionError as failure:
        raise ConditionError(f"조건의 식을 풀지 못했습니다: {failure}") from failure
    out["units"] = unit_systems.declaration(system)
    out["loads"] = [_filled_load(one, system) for one in out.get("loads", [])]
    out["materials"] = [
        _with_converted(one, system, keys or {}) for one in out.get("materials", [])
    ]
    return out


def _load_units(load_type: str, system: str) -> list[str]:
    """이 하중이 받을 수 있는 크기 단위 — 계가 정한다. 볼트는 예압(힘) · 조임량(길이) 둘."""
    names = unit_systems.system_of(system).names
    if load_type == "bolt_pretension":
        return [names["force"], names["length"]]
    dimension = LOAD_DIMENSIONS.get(load_type)
    return [names[dimension]] if dimension else []


def _check_load(where: str, load: Load, system: str) -> None:
    """하중 하나 — 빠진 값 · 계와 다른 단위 · 쓸 수 없는 방향을 **저장할 때** 말한다.

    안 그러면 크기 없는 하중이나 0 벡터가 내보내져, 받는 쪽이 하중 없는 해석을 끝까지 돌린다.
    """
    label = f"{LOAD_LABELS[load.type]} 「{load.name}」"
    if load.type not in BODY_LOADS and not load.on:
        raise ConditionError(f"{where}: {label} 에 선택 그룹이 없습니다")
    if load.type in LOAD_DIMENSIONS and load.magnitude is None:
        raise ConditionError(f"{where}: {label} 에 크기가 없습니다")
    if load.type == "bolt_pretension" and load.preload is None:
        raise ConditionError(f"{where}: {label} 에 예압(또는 조임량)이 없습니다")
    allowed = _load_units(load.type, system)
    if load.unit and load.unit not in allowed:
        raise ConditionError(
            f"{where}: {label} 의 단위 「{load.unit}」 가 단위계와 다릅니다 "
            f"(이 계에서는 {' 또는 '.join(allowed) or '단위 없음'})"
        )
    direction = load.direction
    if direction == "normal" and load.type != "pressure":
        raise ConditionError(f"{where}: 면의 법선 방향은 압력만 쓸 수 있습니다")
    if isinstance(direction, list):
        if len(direction) != 3:
            raise ConditionError(f"{where}: 방향은 X · Y · Z 세 성분입니다")
        numbers = [one for one in direction if not isinstance(one, str)]
        if len(numbers) == 3 and all(one == 0 for one in numbers):
            raise ConditionError(f"{where}: {label} 의 방향이 0 벡터입니다")
    elif (
        direction is None
        and load.type in DIRECTED_LOADS
        and load.type
        not in (
            "pressure",
            "standard_earth_gravity",
        )
    ):
        raise ConditionError(f"{where}: {label} 에 방향이 없습니다")


def _filled_load(load: dict[str, Any], system: str) -> dict[str, Any]:
    """내보낼 하중 — 비운 단위 · 방향을 **뜻대로 채운다.** 받는 쪽이 기본값을 짐작하지 않게."""
    out = dict(load)
    units = _load_units(str(out.get("type")), system)
    if not out.get("unit") and units:
        out["unit"] = units[0]
    if out.get("direction") is None:
        if out.get("type") == "pressure":
            out["direction"] = "normal"
        elif out.get("type") == "standard_earth_gravity":
            out["direction"] = [0, 0, -1]
    return out


# ── 단위계 바꾸기 — 적어 둔 값도 같이 ────────────────────────────────────────

#: 조건의 칸 → 차원(`core/units.py`). 여기 없는 칸은 계와 상관없다(도 · 온도 · 마찰계수 ·
#: 진동수 · 방향 벡터).
_LENGTH = unit_systems.LENGTH
_VELOCITY: unit_systems.Dimension = (0, 1, -1, 0)
_STIFFNESS: unit_systems.Dimension = (1, -2, -2, 0)  # 응력 / 길이 — 기초 강성
_LOAD_DIMENSION: dict[str, unit_systems.Dimension] = {
    "stress": unit_systems.STRESS,
    "force": unit_systems.FORCE,
    "moment": unit_systems.ENERGY,  # N·mm 과 mJ 는 같은 차원
    "acceleration": (0, 1, -2, 0),
    "angular_velocity": (0, 0, -1, 0),
}


def _decimal(factor: float) -> str:
    """배수를 식에 넣을 글자로 — `1e-3` 대신 `0.001`(사람이 읽는다)."""
    from decimal import Decimal

    text = format(Decimal(repr(factor)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _degree(text: str, values: dict[str, float], lengths: set[str]) -> int | None:
    """식이 길이 치수에 대해 **몇 차인가** — 길이 치수를 2 배 · 3 배 해 보고 값이 2ᵏ · 3ᵏ 배면
    k. `=두께*0.1` 은 1, `=압력` 은 0, `=두께+1` 처럼 섞였거나 값이 0 이면 모른다(None)."""
    used = names_in(text) & lengths
    if not used:
        return 0
    try:
        base = _expr(text, values)
        twice = _expr(text, {k: v * 2 if k in used else v for k, v in values.items()})
        thrice = _expr(text, {k: v * 3 if k in used else v for k, v in values.items()})
    except ExpressionError:
        return None
    if base == 0:
        return None
    k = round(math.log2(abs(twice / base))) if twice else None
    if k is None or not math.isclose(twice / base, 2.0**k, rel_tol=1e-9):
        return None
    return k if math.isclose(thrice / base, 3.0**k, rel_tol=1e-9) else None


def _scaled(
    value: Any,
    factor: float,
    ratio: float = 1.0,
    values: dict[str, float] | None = None,
    lengths: set[str] | frozenset[str] = frozenset(),
) -> Any:
    """값 하나를 새 계로 — 수는 배수를 곱한다. **식은 뜻이 그대로 남게** 고친다.

    식 안의 길이 치수는 풀 때 이미 그 계의 길이로 들어간다(`resolve` 의 `lengths`). 그래서
    `=두께*0.1`(길이 1 차)은 mm → m 에서 **그대로 두면 맞고**, `=압력`(0 차)은 배수를 곱해야
    맞다: 붙일 배수 = factor / ratioᵏ. 차수를 모르는 식(`=두께+1`)은 치수를 옛 계로 되돌려
    넣고(`두께/0.001`) 배수를 곱한다 — 길어도 값은 정확하다."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return float(f"{value * factor:.12g}")
    if isinstance(value, str) and value.startswith("="):
        body = value[1:]
        used = names_in(value) & set(lengths)
        degree = _degree(value, values, set(lengths)) if values is not None else 0
        if not used or degree is not None:
            wrap = factor / ratio ** (degree or 0) if used else factor
            if math.isclose(wrap, 1.0, rel_tol=1e-12):
                return value
            return f"=({body})*{_decimal(float(f'{wrap:.12g}'))}"
        for name in sorted(used, key=len, reverse=True):
            body = re.sub(
                rf"(?<![\w]){re.escape(name)}(?![\w])", f"({name}/{_decimal(ratio)})", body
            )
        return f"=({body})*{_decimal(factor)}"
    if isinstance(value, list):
        return [_scaled(one, factor, ratio, values, lengths) for one in value]
    return value


def convert_system(
    raw: dict[str, Any],
    to: str,
    params: dict[str, Any] | None = None,
    lengths: set[str] | frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """조건 한 벌을 **다른 단위계로** — 적어 둔 값까지 옮긴다. `(새 한 벌, 바뀐 것들)`.

    계만 바꾸고 숫자를 두면 뜻이 바뀐다: 변위량 0.1 mm 가 0.1 m 가 되고 압력 1 MPa 가 1 Pa 가
    된다. 그래서 계를 바꾸는 순간 칸마다 차원대로 옮긴다. 식(`=힘`)은 `=(힘)*0.001` 처럼 배수를
    곱해 둔다 — 식의 변수는 도면 쪽이라 계를 모른다.

    물성은 건드리지 않는다(원본을 두고 내보낼 때 옮긴다). 좌표계 원점은 늘 mm 라 그대로다.
    고치는 중인 한 벌이라 검증하지 않고 읽는다 — 모르는 칸은 그대로 둔다.

    `params` · `lengths` 는 도면의 치수와 그중 길이인 것 — 주면 식 안의 길이 치수를 헤아려
    뜻을 지킨다(`_scaled`). 안 주면 식은 배수만 곱한다(길이 치수를 안 쓰는 식이면 그것이 맞다).
    """
    from copy import deepcopy

    if to not in unit_systems.SYSTEMS:
        raise ConditionError(f"모르는 단위계입니다: {to} ({', '.join(unit_systems.SYSTEMS)})")
    out = deepcopy(raw or {})
    source = unit_systems.system_of(str((out.get("units") or {}).get("system") or ""))
    target = unit_systems.system_of(to)
    out["units"] = {**(out.get("units") or {}), "system": target.key}
    changes: list[dict[str, Any]] = []
    if source.key == target.key:
        return out, changes
    ratio = _length_ratio(target.key) / _length_ratio(source.key)
    try:
        # 식을 헤아릴 때의 치수 값 — 옛 계로 적힌 식이므로 옛 계의 길이로.
        base = resolve_params({"params": params or {}})
        values: dict[str, float] | None = {
            k: v * _length_ratio(source.key) if k in lengths else v for k, v in base.items()
        }
    except ExpressionError:
        values = None

    for item, key, dimension, label in _value_fields(out, source):
        before = item.get(key)
        if before is None or before == "" or before == []:
            continue
        factor = source.factor(dimension) / target.factor(dimension)
        after = _scaled(before, factor, ratio, values, lengths)
        if after == before:
            continue
        item[key] = after
        changes.append(
            {
                "where": label,
                "before": before,
                "after": after,
                "unit_before": _unit_name(source, dimension),
                "unit_after": _unit_name(target, dimension),
            }
        )
    # 단위 이름도 새 계로 — 볼트는 예압(힘) · 조임량(길이)을 가르는 칸이고, 하중은 적혀
    # 있었을 때만(비우면 풀 때 계에서 채운다).
    for one in out.get("loads") or []:
        kind = str(one.get("type", ""))
        if kind == "bolt_pretension":
            by_length = one.get("unit") == source.names["length"]
            one["unit"] = target.names["length" if by_length else "force"]
        elif one.get("unit") and kind in LOAD_DIMENSIONS:
            one["unit"] = target.names[LOAD_DIMENSIONS[kind]]
    return out, changes


def _unit_name(system: unit_systems.System, dimension: Any) -> str:
    """차원의 이름 — 「1 MPa → 1000000 Pa」 로 읽게."""
    names = system.names
    by_dimension = {
        _LENGTH: names["length"],
        _VELOCITY: f"{names['length']}/s",
        _STIFFNESS: f"{names['stress']}/{names['length']}",
        unit_systems.FORCE: names["force"],
        **{dim: names[key] for key, dim in _LOAD_DIMENSION.items()},
    }
    return by_dimension.get(dimension, "")


def _value_fields(
    conditions: dict[str, Any], system: unit_systems.System
) -> list[tuple[dict[str, Any], str, Any, str]]:
    """**계를 따르는 값 칸**들 — `(항목, 칸, 차원, 사람이 읽는 이름)`. 단위계를 바꿀 때 옮기고,
    식을 헤아려 알릴 때 훑는 목록이 하나다(둘이 어긋나면 옮기지 않은 칸이 생긴다)."""
    out: list[tuple[dict[str, Any], str, Any, str]] = []
    for one in conditions.get("constraints") or []:
        name = f"구속 「{one.get('name', '')}」"
        for axis in ("x", "y", "z"):
            out.append((one, axis, _LENGTH, f"{name} {axis.upper()} 변위량"))
        out.append((one, "stiffness", _STIFFNESS, f"{name} 기초 강성"))
    for one in conditions.get("loads") or []:
        name = f"하중 「{one.get('name', '')}」"
        kind = str(one.get("type", ""))
        if kind == "bolt_pretension":
            by_length = one.get("unit") == system.names["length"]
            dimension = _LENGTH if by_length else unit_systems.FORCE
            out.append(
                (one, "preload", dimension, f"{name} {'조임량' if by_length else '예압'}")
            )
        elif kind in LOAD_DIMENSIONS:
            out.append(
                (one, "magnitude", _LOAD_DIMENSION[LOAD_DIMENSIONS[kind]], f"{name} 크기")
            )
    for one in conditions.get("contacts") or []:
        out.append((one, "pinball", _LENGTH, f"접촉 「{one.get('name', '')}」 pinball 반경"))
    for index, one in enumerate(conditions.get("initial") or []):
        if one.get("type") == "velocity":
            out.append((one, "value", _VELOCITY, f"초기조건 {index + 1} 속도"))
            out.append((one, "vector", _VELOCITY, f"초기조건 {index + 1} 속도"))
    for one in conditions.get("mesh_hints") or []:
        name = f"메시 힌트 「{one.get('on', '')}」"
        out.append((one, "element_size", _LENGTH, f"{name} 요소 크기"))
        out.append((one, "defeature_size", _LENGTH, f"{name} 무시할 크기"))
    return out


def expression_notes(
    raw: dict[str, Any],
    params: dict[str, Any],
    lengths: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
    """값 칸의 식을 **지금 단위계로 헤아려** 사람에게 알릴 것들 — `{where, level, text}`.

    - 식이 도면의 길이 치수를 쓰고 계가 mm 가 아니면: 그 치수가 이 계의 길이로 들어간다는
      것과 풀린 값(`info`). 사람이 `*0.001` 을 붙이지 않아도 되지만, 무엇이 되는지 보여야 한다.
    - 길이 치수와 상수를 더하거나 뺀 식(`=두께+1`)이면: 상수도 이 계의 길이로 읽힌다(`warn`).
    - 풀리지 않는 식이면 그 까닭(`warn`).
    """
    system = unit_systems.system_of(str((raw.get("units") or {}).get("system") or ""))
    ratio = _length_ratio(system.key)
    try:
        base = resolve_params({"params": params or {}})
    except ExpressionError:
        return []
    values = {k: v * ratio if k in lengths else v for k, v in base.items()}
    length_name = system.names["length"]
    notes: list[dict[str, str]] = []
    for item, key, dimension, label in _value_fields(raw, system):
        texts = item.get(key)
        for text in texts if isinstance(texts, list) else [texts]:
            if not (isinstance(text, str) and text.startswith("=")):
                continue
            try:
                value = _expr(text, values)
            except ExpressionError as failure:
                notes.append({"where": label, "level": "warn", "text": str(failure)})
                continue
            used = sorted(names_in(text) & set(lengths))
            if not used or math.isclose(ratio, 1.0):
                continue
            shown = ", ".join(
                f"{name} {base[name]:g} mm → {values[name]:g} {length_name}" for name in used
            )
            unit = _unit_name(system, dimension)
            notes.append(
                {
                    "where": label,
                    "level": "info",
                    "text": f"{text} — 도면 치수를 {length_name} 로 넣어 풉니다({shown}) "
                    f"= {value:g} {unit}".rstrip(),
                }
            )
            if _degree(text, values, set(lengths)) is None:
                notes.append(
                    {
                        "where": label,
                        "level": "warn",
                        "text": f"{text} — 도면 치수와 상수를 더하거나 뺐습니다. 상수도 "
                        f"{length_name} 로 읽힙니다(mm 로 적었다면 고치세요).",
                    }
                )
    return notes


# ── 사양표 — 화면과 AI 가 같은 것을 본다 ─────────────────────────────────────


def spec() -> dict[str, Any]:
    """조건마다 **어떤 칸이 있는가**. 화면은 이것으로 폼을 그리고, AI 는 이것을 읽고 쓴다.

    종류가 열 몇이고 칸이 제각각이다(고정 지지에는 값이 없고, 압력에는 크기와 방향이,
    볼트에는 N 또는 mm 가 있다). 화면에 `if` 를 늘어놓으면 종류를 더할 때마다 화면을 고쳐야
    한다 — CAD 리본이 `OP_SPECS` 로 푸는 것과 같은 방식이다. **정본은 이 서버**다.

    JSON Schema 를 그대로 주는 것은 Pydantic 이 이미 만든다(`model_json_schema`). 사람이
    읽을 이름과 묶음(어느 탭에 놓을 것인가)만 여기서 더한다.
    """
    groups: dict[str, Any] = {
        "constraints": {
            "label": "구속",
            "model": Constraint,
            "implied": IMPLIED_HOLDS,
            "notes": CONSTRAINT_NOTES,
        },
        "loads": {
            "label": "하중",
            "model": Load,
            "notes": LOAD_NOTES,
            "dimensions": LOAD_DIMENSIONS,
        },
        "contacts": {"label": "접촉", "model": Contact},
        "initial": {"label": "초기조건", "model": Initial},
        "mesh_hints": {"label": "메시 힌트", "model": MeshHint},
    }
    out: dict[str, Any] = {
        "schema_version": 1,
        "units": Units().model_dump(),
        # **고를 수 있는 단위계.** 화면에 목록을 박으면 계를 더할 때마다 화면을 고쳐야
        # 한다 — 조건 종류와 같은 까닭으로 정본은 서버다.
        "unit_systems": [
            {"key": one.key, "label": one.label, **one.names}
            for one in unit_systems.SYSTEMS.values()
        ],
        "analysis": Analysis.model_json_schema(),
        "groups": {},
    }
    for key, one in groups.items():
        model = one["model"]
        schema = model.model_json_schema()
        kinds = schema.get("properties", {}).get("type", {})
        out["groups"][key] = {
            "label": one["label"],
            # 이 묶음에 무엇을 더할 수 있나 — 화면의 「+ 조건」 목록이 이것이다.
            "types": kinds.get("enum", kinds.get("const", [])),
            "fields": schema.get("properties", {}),
            "required": schema.get("required", []),
            # 종류가 스스로 정하는 방향 — 화면이 잠긴 칸으로 보여 준다.
            "implied": one.get("implied", {}),
            # 종류마다 한 줄 설명, 그리고 크기의 차원(단위계 이름표의 열쇠 — 화면이 단위를
            # 붙인다).
            "notes": one.get("notes", {}),
            "dimensions": one.get("dimensions", {}),
        }
    out["entities"] = ["face", "edge", "vertex", "body"]
    return out
