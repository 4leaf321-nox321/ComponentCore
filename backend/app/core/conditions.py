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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core import units as unit_systems
from app.core.recipe.params import ExpressionError, resolve_params
from app.core.recipe.params import evaluate_expression as _expr


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
            raise ValueError(f"정수 또는 「=식」 이어야 합니다: {value!r}") from failure
    return value


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
    ] = Field(json_schema_extra=_extra({"labels": CONSTRAINT_LABELS}))
    on: str = Field(title="선택 그룹")
    cs: str = Field(
        "global",
        json_schema_extra=_extra({"only_for": ["displacement", "remote_displacement"]}),
    )
    """성분의 축 — 변위 · 원격 변위만 쓴다(원통 지지는 원통의 축을, 나머지는 면을
    따른다). 원격 변위는 이 좌표계의 **원점**을 원격점으로 쓸 수도 있다(`location`)."""
    location: Literal["centroid", "cs_origin"] = Field(
        "centroid",
        title="원격점",
        description="면을 묶는 한 점 — 고른 면의 중심, 또는 좌표계의 원점",
        json_schema_extra=_extra(
            {
                "only_for": ["remote_displacement"],
                "labels": {"centroid": "선택 그룹의 중심", "cs_origin": "좌표계의 원점"},
            }
        ),
    )
    behavior: Literal["deformable", "rigid"] = Field(
        "deformable",
        title="면의 거동",
        description=(
            "변형체: 면이 따라 휘어진다 · 강체: 면이 모양을 지킨 채 움직인다(더 뻣뻣하다)"
        ),
        json_schema_extra=_extra(
            {
                "only_for": ["remote_displacement"],
                "labels": {"deformable": "변형체", "rigid": "강체"},
            }
        ),
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
        description=("법선으로 1 mm 눌리는 데 드는 압력(N/mm³ = MPa/mm)"),
        json_schema_extra=_extra({"only_for": ["elastic_support"]}),
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
    ] = Field(json_schema_extra=_extra({"labels": LOAD_LABELS}))
    on: str = Field(
        "",
        title="선택 그룹",
        json_schema_extra=_extra(
            {"only_for": ["pressure", "force", "moment", "bearing", "bolt_pretension"]}
        ),
    )
    """중력처럼 온 몸에 걸리는 것은 비어 있다."""
    cs: str = Field("global", json_schema_extra=_extra({"only_for": DIRECTED_LOADS}))
    """방향 성분의 축 — 구속과 같다. 회전 속도는 이 좌표계의 원점을 지나는 축으로 돈다."""
    magnitude: Number | None = Field(
        None,
        title="크기",
        json_schema_extra=_extra(
            {
                "only_for": [
                    k
                    for k in LOAD_LABELS
                    if k not in ("bolt_pretension", "standard_earth_gravity")
                ],
                "unit_by_type": True,
            }
        ),
    )
    unit: str = Field("", json_schema_extra=_extra({"hidden": True}))
    """`MPa` · `N` · `N*mm` … **단위를 값에서 떼지 않는다** — 물성에서 그것이 10¹² 배로
    틀린 적이 있다(MatNexus 의 실측). 비우면 단위계에서 채운다."""
    direction: list[Number] | Literal["normal"] | None = Field(
        None,
        title="방향",
        json_schema_extra=_extra(
            {
                "direction": True,
                "only_for": DIRECTED_LOADS,
                "normal_for": ["pressure"],
            }
        ),
    )
    """좌표계(`cs`)의 X · Y · Z 성분(길이는 상관없다), 또는 `"normal"`(면의 법선 — 압력만).
    비우면 압력은 법선, 중력은 -Z 다."""
    preload: Number | None = Field(
        None,
        title="예압",
        json_schema_extra=_extra({"only_for": ["bolt_pretension"], "bolt": True}),
    )
    """`bolt_pretension` — 예압(힘) 또는 조임량(길이), `unit` 이 가른다."""


CONTACT_LABELS: dict[str, str] = {
    "bonded": "본딩(붙음)",
    "no_separation": "분리 없음",
    "frictional": "마찰",
    "frictionless": "마찰 없음",
    "rough": "거친 접촉",
}

CONTACT_NOTES: dict[str, str] = {
    "bonded": "두 면이 붙어 한 몸처럼 움직입니다 — 미끄러지지도 떨어지지도 않습니다(선형). "
    "볼트 · 용접 · 접착을 단순화할 때.",
    "no_separation": "떨어지지 않고, 면을 따라 조금 미끄러질 수 있습니다"
    "(마찰 없음 · 거의 선형).",
    "frictional": "눌리면 마찰계수만큼 버티다 미끄러지고, 떨어질 수도 있습니다(비선형). "
    "실제 맞닿음에 가장 가깝습니다.",
    "frictionless": "마찰 없이 미끄러지고, 떨어질 수도 있습니다(비선형).",
    "rough": "미끄러지지 않지만 떨어질 수는 있습니다(마찰 무한대 · 비선형).",
}

#: 틈 · 겹침을 다루는 방법 — 떨어질 수 있는(비선형) 접촉만 쓴다.
_NONLINEAR_CONTACTS = ["no_separation", "frictional", "frictionless", "rough"]


class Contact(Base):
    """접촉 — 두 선택 그룹이 만나는 자리. 접촉면(`source`)이 대상면(`target`)을 검사한다."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal["bonded", "no_separation", "frictional", "frictionless", "rough"] = Field(
        json_schema_extra=_extra({"labels": CONTACT_LABELS})
    )
    source: str = Field(
        title="접촉면 (contact)", description="보통 작거나 볼록하거나 부드러운 쪽"
    )
    target: str = Field(
        title="대상면 (target)", description="보통 크거나 오목하거나 단단한 쪽"
    )
    friction: Number | None = Field(
        None,
        title="마찰계수",
        description="0 ~ 1 — 강과 강(마른 면)은 대략 0.15 ~ 0.2",
        json_schema_extra=_extra({"only_for": ["frictional"]}),
    )
    formulation: Literal[
        "program_controlled", "pure_penalty", "augmented_lagrange", "normal_lagrange", "mpc"
    ] = Field(
        "program_controlled",
        title="정식화",
        description="모르면 「프로그램이 정함」. MPC 는 본딩 · 분리 없음에만 씁니다",
        json_schema_extra=_extra(
            {
                "labels": {
                    "program_controlled": "프로그램이 정함",
                    "pure_penalty": "페널티",
                    "augmented_lagrange": "증강 라그랑주",
                    "normal_lagrange": "라그랑주(법선)",
                    "mpc": "MPC(구속식)",
                }
            }
        ),
    )
    behavior: Literal["program_controlled", "symmetric", "asymmetric", "auto_asymmetric"] = (
        Field(
            "program_controlled",
            title="검사 방향",
            description="대칭: 두 면이 서로를 검사 · 비대칭: 접촉면만 대상면을 검사",
            json_schema_extra=_extra(
                {
                    "labels": {
                        "program_controlled": "프로그램이 정함",
                        "symmetric": "대칭",
                        "asymmetric": "비대칭",
                        "auto_asymmetric": "자동 비대칭",
                    }
                }
            ),
        )
    )
    pinball: Number | None = Field(
        None,
        title="pinball 반경",
        description="이 거리 안의 면끼리만 접촉으로 봅니다 — 비우면 프로그램이 정함. "
        "틈이 있는 본딩이면 틈보다 크게",
        json_schema_extra=_extra({"unit": "mm"}),
    )
    interface_treatment: Literal[
        "add_offset_ramped", "add_offset_no_ramp", "adjust_to_touch"
    ] = Field(
        "add_offset_ramped",
        title="처음의 틈 · 겹침",
        description="형상에 작은 틈이나 겹침이 있을 때 — 「맞붙여 시작」 은 그것을 없앤 것으로"
        " "
        "칩니다",
        json_schema_extra=_extra(
            {
                "only_for": _NONLINEAR_CONTACTS,
                "labels": {
                    "add_offset_ramped": "형상 그대로(서서히)",
                    "add_offset_no_ramp": "형상 그대로(바로)",
                    "adjust_to_touch": "맞붙여 시작",
                },
            }
        ),
    )

    @field_validator("formulation", "behavior", "interface_treatment", mode="before")
    @classmethod
    def _blank(cls, value: Any, info: Any) -> Any:
        """예전에 비워 둔 칸(`""`)은 기본값으로 — 고를 것을 정한 뒤로 빈 글자는 뜻이 없다."""
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return value


INITIAL_LABELS: dict[str, str] = {
    "environment_temperature": "환경 온도",
    "temperature": "초기 온도",
    "velocity": "초기 속도",
    "prestress": "선응력(프리스트레스)",
}

INITIAL_NOTES: dict[str, str] = {
    "environment_temperature": "모델 전체의 기준 온도 — 열팽창이 0 인 온도입니다(보통 22 °C).",
    "temperature": "고른 바디가 이 온도에서 시작합니다 — 열 해석(과도)의 출발점.",
    "velocity": "고른 바디가 이 속도로 움직이며 시작합니다 — 낙하 · 충돌(explicit) 해석용.",
    "prestress": "앞선 정적 해석의 응력을 안고 시작합니다 — 볼트 조임 · 원심력이 고유진동수를 "
    "바꿀 때(모달).",
}


class Initial(Base):
    """초기조건 — 풀기 전의 상태."""

    type: Literal["environment_temperature", "velocity", "temperature", "prestress"] = Field(
        json_schema_extra=_extra({"labels": INITIAL_LABELS})
    )
    on: str = Field(
        "",
        title="바디 선택 그룹",
        json_schema_extra=_extra({"only_for": ["temperature", "velocity"]}),
    )
    value: Number | None = Field(
        None,
        title="온도",
        json_schema_extra=_extra(
            {
                "only_for": ["environment_temperature", "temperature"],
                "unit": "°C",
            }
        ),
    )
    vector: list[Number] | None = Field(
        None,
        title="속도",
        description="전역 X · Y · Z 성분",
        json_schema_extra=_extra(
            {"only_for": ["velocity"], "unit": "mm/s", "components": True}
        ),
    )
    unit: str = Field("", json_schema_extra=_extra({"hidden": True}))
    """내보낼 때 채운다(온도 `C`, 속도 `<길이>/s`)."""
    from_step: str = Field(
        "",
        title="선행 정적 해석",
        description="응력을 가져올 해석의 이름 — 비우면 받는 쪽이 이 모델의 정적 해석을 "
        "씁니다",
        json_schema_extra=_extra({"only_for": ["prestress"]}),
    )


ANALYSIS_LABELS: dict[str, str] = {
    "modal": "모달(고유진동)",
    "static": "정적 구조",
    "harmonic": "조화 응답(주파수 응답)",
    "explicit": "명시적 동해석(충돌 · 낙하)",
    "thermal": "열",
}

ANALYSIS_NOTES: dict[str, str] = {
    "modal": "구조가 스스로 떠는 진동수와 모양을 찾습니다 — 하중은 쓰지 않고 "
    "구속 · 물성(밀도)만 씁니다.",
    "static": "하중이 천천히 걸려 멈춘 상태의 변형 · 응력을 봅니다. "
    "접촉 · 대변형이면 비선형으로 풉니다.",
    "harmonic": "정해진 주파수로 흔드는 하중에 대한 응답(진폭 · 응력)을 주파수마다 "
    "봅니다 — 공진을 찾을 때.",
    "explicit": "아주 짧은 시간(수 ms)의 충돌 · 낙하 · 파손을 시간에 따라 풉니다 — "
    "초기 속도가 흔히 필요합니다.",
    "thermal": "열이 어떻게 퍼지는지(온도 분포) 봅니다 — 정상 상태 또는 시간에 따라(과도).",
}

#: 종류 안에서 **다른 칸의 값에 따라** 보이는 칸 — `{종류: {칸: 값}}`. 열 해석의 시간 칸은
#: 과도일 때만 뜻이 있다. 화면이 감추고, 내보낼 때도 뺀다.
_TRANSIENT: dict[str, dict[str, str]] = {"thermal": {"thermal_mode": "transient"}}

#: 해석 설정 창 맨 위의 한두 줄.
_ANALYSIS_INTRO = (
    "무엇을 풀지 고릅니다. 종류마다 필요한 칸만 보이고, 내보낼 때도 그 칸만 실립니다. "
    "모르는 칸은 비우거나 「프로그램이 정함」 으로 둡니다."
)


class Analysis(Base):
    """무엇을 풀 것인가 — **종류마다 칸이 다르다**(`only_for`). 내보낼 때는 그 종류의 칸만
    기본값을 채워 싣는다(`_filled_analysis`) — 받는 쪽이 「이 칸이 없으면 무엇인가」 를
    짐작하지 않게."""

    type: Literal["modal", "static", "harmonic", "explicit", "thermal"] = Field(
        default="modal", json_schema_extra=_extra({"labels": ANALYSIS_LABELS})
    )
    # ── 모달 · 조화 ────────────────────────────────────────────────────────
    modes: Integer | None = Field(
        default=6,
        title="모드 수",
        description="찾을(조화 응답이면 쓸) 고유진동 모드의 개수 — 보통 6 ~ 20",
        json_schema_extra=_extra({"only_for": ["modal", "harmonic"], "integer": True}),
    )
    frequency_range: list[Number] | None = Field(
        default=None,
        title="주파수 범위",
        description=(
            "모달: 이 범위 안에서 찾습니다(비우면 낮은 것부터) · 조화 응답: 훑을 범위(필수)"
        ),
        json_schema_extra=_extra(
            {"only_for": ["modal", "harmonic"], "unit": "Hz", "range": True}
        ),
    )
    prestressed: bool = Field(
        default=False,
        title="선응력 반영",
        description="앞선 정적 해석의 응력(볼트 조임 · 원심력)을 안고 풉니다 — 초기조건의 "
        "「선응력」 과 함께 씁니다",
        json_schema_extra=_extra({"only_for": ["modal", "harmonic"]}),
    )
    # ── 조화 응답 ──────────────────────────────────────────────────────────
    solution_intervals: Integer = Field(
        default=10,
        title="주파수 점 수",
        description="범위를 몇 점으로 나눠 풀지 — 공진 근처를 자세히 보려면 늘립니다",
        json_schema_extra=_extra({"only_for": ["harmonic"], "integer": True}),
    )
    method: Literal["mode_superposition", "full"] = Field(
        default="mode_superposition",
        title="풀이 방법",
        description="모드 중첩: 모달 결과로 빨리 풉니다(모드 수 필요) · 완전법: 느리지만 정확",
        json_schema_extra=_extra(
            {
                "only_for": ["harmonic"],
                "labels": {"mode_superposition": "모드 중첩(빠름)", "full": "완전법(정확)"},
            }
        ),
    )
    damping_ratio: Number | None = Field(
        default=None,
        title="감쇠비",
        description="임계 감쇠에 대한 비 — 강 구조는 0.01 ~ 0.03. 비우면 감쇠가 없어 공진에서 "
        "응답이 끝없이 커집니다",
        json_schema_extra=_extra({"only_for": ["harmonic"]}),
    )
    # ── 정적 구조 ──────────────────────────────────────────────────────────
    large_deflection: bool = Field(
        default=False,
        title="대변형",
        description=(
            "변형이 커서 모양이 바뀌면 켭니다(비선형 · 느림) — 얇은 판 · 고무 · 큰 처짐"
        ),
        json_schema_extra=_extra({"only_for": ["static"]}),
    )
    steps: Integer = Field(
        default=1,
        title="하중 단계 수",
        description="하중을 나눠 거는 단계 — 볼트를 먼저 조이고 하중을 걸면 2",
        json_schema_extra=_extra({"only_for": ["static"], "integer": True}),
    )
    substeps: Integer | None = Field(
        default=None,
        title="처음 부단계 수",
        description=(
            "한 단계를 몇 번에 나눠 풀지 — 접촉 · 대변형이 안 풀리면 늘립니다. 비우면 자동"
        ),
        json_schema_extra=_extra({"only_for": ["static"], "integer": True}),
    )
    solver: Literal["program_controlled", "direct", "iterative"] = Field(
        default="program_controlled",
        title="솔버",
        description=(
            "모르면 「프로그램이 정함」 — 직접법은 메모리를 많이 쓰고, "
            "반복법은 큰 솔리드에 빠릅니다"
        ),
        json_schema_extra=_extra(
            {
                "only_for": ["static", "modal", "harmonic", "thermal"],
                "labels": {
                    "program_controlled": "프로그램이 정함",
                    "direct": "직접법",
                    "iterative": "반복법",
                },
            }
        ),
    )
    # ── 열 ────────────────────────────────────────────────────────────────
    thermal_mode: Literal["steady", "transient"] = Field(
        default="steady",
        title="열 해석",
        description="정상 상태: 오래 지나 변하지 않는 온도 · 과도: 시간에 따라(끝 시간 필요)",
        json_schema_extra=_extra(
            {
                "only_for": ["thermal"],
                "labels": {"steady": "정상 상태", "transient": "과도(시간에 따라)"},
            }
        ),
    )
    time_step: Number | None = Field(
        default=None,
        title="처음 시간 간격",
        description="열 과도: 첫 시간 간격 — 비우면 자동",
        json_schema_extra=_extra({"only_for": ["thermal"], "unit": "s", "when": _TRANSIENT}),
    )
    # ── 명시적 · 열 과도 ─────────────────────────────────────────────────
    end_time: Number | None = Field(
        default=None,
        title="끝 시간",
        description="명시적: 충돌 · 낙하가 끝날 만큼(보통 수 ms) · 열 과도: 지켜볼 시간",
        json_schema_extra=_extra(
            {
                "only_for": ["explicit", "thermal"],
                "unit": "s",
                "when": _TRANSIENT,
            }
        ),
    )
    output_count: Integer = Field(
        default=20,
        title="결과 저장 횟수",
        description="끝 시간 동안 결과를 몇 번 남길지 — 많을수록 파일이 커집니다",
        json_schema_extra=_extra(
            {
                "only_for": ["explicit", "thermal"],
                "integer": True,
                "when": _TRANSIENT,
            }
        ),
    )
    mass_scaling_dt: Number | None = Field(
        default=None,
        title="질량 스케일링 시간 간격",
        description="이보다 작은 시간 간격이 필요한 작은 요소에 질량을 더해 빨리 "
        "풉니다 — 비우면 쓰지 않습니다(정확)",
        json_schema_extra=_extra({"only_for": ["explicit"], "unit": "s"}),
    )

    @field_validator(
        "modes",
        "solution_intervals",
        "steps",
        "output_count",
        "method",
        "solver",
        "thermal_mode",
        mode="before",
    )
    @classmethod
    def _blank(cls, value: Any, info: Any) -> Any:
        """비운 칸(`None` · `""`)은 기본값 — 화면이 「기본 6」 이라고 보여 준 그대로. 정수 칸의
        글자는 정수로, 식(`=모드수`)은 그대로 둔다."""
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return _integer_or_expr(value) if info.field_name in _INTEGER_FIELDS else value

    @field_validator("substeps", mode="before")
    @classmethod
    def _integer(cls, value: Any) -> Any:
        return _integer_or_expr(value)


class MeshHint(Base):
    """메시는 받는 쪽이 만든다 — 여기 적는 것은 **바람**이다. 비운 칸은 받는 쪽이 정한다."""

    on: str = Field(
        "전체",
        title="적용 대상",
        description="「전체」 또는 선택 그룹 — 선택 그룹이면 그 자리만 이 크기로",
        json_schema_extra=_extra({"whole": "전체"}),
    )
    element_size: Number | None = Field(
        None,
        title="요소 크기",
        description="요소 한 변의 평균 — 작을수록 정확하고 느립니다. "
        "판이면 두께의 1/2 ~ 1/3 쯤",
        json_schema_extra=_extra({"unit": "mm"}),
    )
    method: Literal["automatic", "tetrahedrons", "hex_dominant", "sweep", "multizone"] = Field(
        "automatic",
        title="요소 모양",
        description="모르면 「자동」. 스윕 · 멀티존은 쓸어 만든 모양(판 · 축)을 "
        "육면체로 채웁니다",
        json_schema_extra=_extra(
            {
                "labels": {
                    "automatic": "자동",
                    "tetrahedrons": "사면체",
                    "hex_dominant": "육면체 우세",
                    "sweep": "스윕(육면체)",
                    "multizone": "멀티존(육면체)",
                }
            }
        ),
    )
    order: Literal["program_controlled", "linear", "quadratic"] = Field(
        "program_controlled",
        title="요소 차수",
        description="2 차가 응력 · 굽힘에 정확합니다(권장). "
        "1 차는 빠르지만 사면체면 뻣뻣하게 나옵니다",
        json_schema_extra=_extra(
            {
                "labels": {
                    "program_controlled": "프로그램이 정함",
                    "linear": "1 차(빠름)",
                    "quadratic": "2 차(정확)",
                }
            }
        ),
    )
    inflation_layers: Integer | None = Field(
        None,
        title="경계층 수",
        description="벽 가까이를 얇은 층으로 — 유동 · 열 경계층용. 구조 해석에서는 비웁니다",
        json_schema_extra=_extra({"integer": True}),
    )
    defeature_size: Number | None = Field(
        None,
        title="무시할 형상 크기",
        description="이보다 작은 모서리 · 구멍 · 필렛은 메시에서 무시합니다",
        json_schema_extra=_extra({"unit": "mm"}),
    )

    @field_validator("method", "order", mode="before")
    @classmethod
    def _blank(cls, value: Any, info: Any) -> Any:
        """예전에 비워 둔 칸(`""`)은 기본값으로."""
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return value

    @field_validator("inflation_layers", mode="before")
    @classmethod
    def _integer(cls, value: Any) -> Any:
        return _integer_or_expr(value)


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


# ── 무엇에 거는가 — 종류마다 받는 선택 그룹 ─────────────────────────────────

_FACE: dict[str, str] = {"entity": "face"}
_EDGE: dict[str, str] = {"entity": "edge"}
_VERTEX: dict[str, str] = {"entity": "vertex"}
_BODY: dict[str, str] = {"entity": "body"}
_CYLINDER_FACE: dict[str, str] = {"entity": "face", "kind": "cylinder"}
_SPOTS = [_FACE, _EDGE, _VERTEX]
_FACE_EDGE = [_FACE, _EDGE]

#: 종류 → **받는 선택 그룹**(종류 · 면의 모양). 화면은 이것으로 고를 수 있는 그룹과 3D 에서
#: 누를 수 있는 것을 좁히고, AI 는 사양표(`accepts`)에서 읽는다. 없는 종류는 대상이 없다
#: (중력처럼 몸 전체). `kind` 가 있으면 **선택 규칙에 그 모양이 적혀 있어야** 한다 — 「이
#: 자리에 가까운 면」 만으로는 치수가 바뀐 설계점에서 다른 모양의 면을 집을 수 있다.
CONSTRAINT_ACCEPTS: dict[str, list[dict[str, str]]] = {
    "fixed_support": _SPOTS,
    "displacement": _SPOTS,
    # 원격 변위는 면 · 엣지를 한 점에 묶는다 — 점 하나를 묶는 것은 뜻이 없다(Mechanical).
    "remote_displacement": _FACE_EDGE,
    "frictionless": [_FACE],
    "cylindrical": [_CYLINDER_FACE],
    "compression_only": [_FACE],
    "elastic_support": [_FACE],
}
LOAD_ACCEPTS: dict[str, list[dict[str, str]]] = {
    "pressure": [_FACE],
    "force": _SPOTS,
    "moment": _FACE_EDGE,
    "bearing": [_CYLINDER_FACE],
    "bolt_pretension": [_CYLINDER_FACE, _BODY],
}
CONTACT_ACCEPTS: dict[str, list[dict[str, str]]] = {kind: [_FACE] for kind in CONTACT_LABELS}
#: 메시 힌트는 종류가 없다 — `*` 가 모든 경우. 「전체」 는 그룹이 아니라 늘 된다.
MESH_ACCEPTS: dict[str, list[dict[str, str]]] = {"*": [_FACE, _EDGE, _BODY]}
INITIAL_ACCEPTS: dict[str, list[dict[str, str]]] = {
    "temperature": [_BODY],
    "velocity": [_BODY],
}

_ENTITY_LABELS = {"face": "면", "edge": "엣지", "vertex": "점", "body": "바디"}
_KIND_LABELS = {"cylinder": "원통면"}


def _accepts_label(options: list[dict[str, str]]) -> str:
    """「원통면 · 바디」 처럼 — 받는 것을 사람 말로."""
    return " · ".join(
        _KIND_LABELS.get(one.get("kind", ""), "") or _ENTITY_LABELS[one["entity"]]
        for one in options
    )


def _check_target(
    where: str, label: str, accepts: list[dict[str, str]], selection: NamedSelection
) -> None:
    """선택 그룹이 이 조건이 받는 종류 · 모양인가. 아니면 **어떻게 고칠지까지** 말한다 — 화면을
    쓰는 사람과 MCP 로 조건을 짓는 AI 가 같은 말을 듣는다."""
    fits = [one for one in accepts if one["entity"] == selection.entity]
    if not fits:
        raise ConditionError(
            f"{where}: {label} 는 {_accepts_label(accepts)} 선택 그룹에만 겁니다 — "
            f"「{selection.name}」 은 {_ENTITY_LABELS[selection.entity]} 선택 그룹입니다"
        )
    if not all(one.get("kind") for one in fits):
        return
    kinds = {one["kind"] for one in fits}
    members = selection.select.get("any") or [selection.select]
    if any(str(one.get("kind", "")) not in kinds for one in members):
        wanted = " · ".join(_KIND_LABELS.get(kind, kind) for kind in sorted(kinds))
        raise ConditionError(
            f"{where}: {label} 는 {wanted} 에만 겁니다 — 선택 그룹 「{selection.name}」 의 "
            f"규칙에 kind: {' · '.join(sorted(kinds))} 가 없어, 치수가 바뀐 설계점에서 다른 "
            "모양의 면을 집을 수 있습니다. 3D 에서 고를 때 원통면 규칙을 고르세요"
            '(셀렉터라면 {"what": "faces", "kind": "cylinder", …})'
        )


def _check_targets(conditions: Conditions) -> None:
    """조건마다 가리키는 선택 그룹이 **받을 수 있는 것**인가."""
    selections = {one.name: one for one in conditions.named_selections}

    def check(where: str, label: str, accepts: list[dict[str, str]] | None, name: str) -> None:
        if accepts and name in selections:
            _check_target(where, label, accepts, selections[name])

    for index, one in enumerate(conditions.constraints):
        label = f"{CONSTRAINT_LABELS[one.type]} 「{one.name}」"
        check(f"constraints[{index}]", label, CONSTRAINT_ACCEPTS.get(one.type), one.on)
    for index, load in enumerate(conditions.loads):
        label = f"{LOAD_LABELS[load.type]} 「{load.name}」"
        check(f"loads[{index}]", label, LOAD_ACCEPTS.get(load.type), load.on)
    for index, contact in enumerate(conditions.contacts):
        accepts = CONTACT_ACCEPTS.get(contact.type)
        label = f"접촉 「{contact.name}」"
        check(f"contacts[{index}]", f"{label} 의 접촉면", accepts, contact.source)
        check(f"contacts[{index}]", f"{label} 의 대상면", accepts, contact.target)
    for index, initial in enumerate(conditions.initial):
        label = INITIAL_LABELS[initial.type]
        check(f"initial[{index}]", label, INITIAL_ACCEPTS.get(initial.type), initial.on)
    for index, hint in enumerate(conditions.mesh_hints):
        check(f"mesh_hints[{index}]", f"메시 힌트 「{hint.on}」", MESH_ACCEPTS["*"], hint.on)


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

    # **받을 수 있는 것인가** — 압력을 엣지에, 베어링을 평면에 걸면 받는 쪽이 거절하거나
    # 엉뚱하게 푼다. 저장할 때 말한다.
    _check_targets(conditions)

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

    _check_analysis(conditions.analysis)
    for index, contact in enumerate(conditions.contacts):
        _check_contact(f"contacts[{index}]", contact)
    for index, initial in enumerate(conditions.initial):
        _check_initial(f"initial[{index}]", initial)
    for index, load in enumerate(conditions.loads):
        _check_load(f"loads[{index}]", load)
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


#: **입력 단위계** — 조건의 값은 늘 이 계로 적는다(도면과 같은 mm). 조건의 `units.system` 은
#: **내보내기 단위계**다: 점 파일을 만들 때만 그 계로 옮긴다. 화면 · 식 · 도면 치수가 한 계라
#: 섞일 일이 없다(「SI 를 골랐는데 왜 mm 가 보이지」 — 2026-09-28 에 이렇게 바꿨다).
INPUT_SYSTEM = "mm_n_tonne"


def resolve(
    raw: dict[str, Any] | None,
    params: dict[str, Any],
    keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    """`"=식"` 을 그 설계점의 값으로 바꾼 **새 사본**. 레시피와 같은 문법이다.

    받는 쪽은 식을 풀 수 없다 — 설계점마다 **풀린 값**을 내보내야 한다.

    `keys` 는 물성 이름 사전(`{사람이 쓰는 이름: 표준 열쇠}`)이다. **코어는 그것을 가져오지
    않는다** — 네트워크는 바깥 층의 일이고(아키텍처 시험이 지킨다), 여기는 받은 것으로 풀기만
    한다. 안 주면 표준 열쇠만 안 붙는다(값은 그대로 나간다).

    여기서 **내보내기 단위계로 옮긴다**: 값은 입력 계(`INPUT_SYSTEM`, mm · N · t)로 적혔고 식도
    도면 치수(mm)로 그 계에서 푼다. 풀린 수를 칸마다 차원대로 내보내기 계로 옮기고, `units` 를
    닫힌 선언으로 펼친다. 물성은 그 계로 옮긴 값(`converted`)을 **원본 옆에** 놓는다 — MatNexus
    가 밀도만 `tonne/mm3` 로 주고 나머지는 SI 로 주므로, 이것이 없으면 받는 쪽이 밀도는 맞고
    탄성계수는 10⁶ 배 틀린 채로 푼다.
    """
    conditions = parse(raw).model_dump()
    values = resolve_params({"params": params})

    def walk(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("="):
            return _expr(value, values)
        # 좌표계 원점 같은 세 성분은 모델에서 **튜플**로 나온다 — 목록만 훑으면 그 안의 식이
        # 안 풀린 채 나갔다(2026-09-28 에 잡았다).
        if isinstance(value, list | tuple):
            return [walk(one) for one in value]
        if isinstance(value, dict):
            return {key: walk(one) for key, one in value.items()}
        return value

    try:
        out = {key: walk(one) for key, one in conditions.items()}
    except ExpressionError as failure:
        raise ConditionError(f"조건의 식을 풀지 못했습니다: {failure}") from failure
    system = str((out.get("units") or {}).get("system") or unit_systems.DEFAULT_SYSTEM)
    target = unit_systems.system_of(system)
    source = unit_systems.system_of(INPUT_SYSTEM)
    for item, key, dimension, _ in _value_fields(out, source):
        factor = source.factor(dimension) / target.factor(dimension)
        item[key] = _times(item.get(key), factor)
    out["units"] = unit_systems.declaration(target.key)
    out["loads"] = [_filled_load(one, target.key) for one in out.get("loads", [])]
    out["initial"] = [_filled_initial(one, target.key) for one in out.get("initial", [])]
    out["analysis"] = _filled_analysis(_integerized(out.get("analysis") or {}, "analysis"))
    out["mesh_hints"] = [
        _integerized(one, f"mesh_hints[{i}]")
        for i, one in enumerate(out.get("mesh_hints", []))
    ]
    out["materials"] = [
        _with_converted(one, target.key, keys or {}) for one in out.get("materials", [])
    ]
    return out


def _times(value: Any, factor: float) -> Any:
    """풀린 값을 배수만큼 — 수 · 수의 목록만. 비었으면 그대로(자유는 자유)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return float(f"{value * factor:.12g}")
    if isinstance(value, list):
        return [_times(one, factor) for one in value]
    return value


def _load_units(load_type: str, system: str = INPUT_SYSTEM) -> list[str]:
    """이 하중이 받을 수 있는 크기 단위 — 계가 정한다. 볼트는 예압(힘) · 조임량(길이) 둘."""
    names = unit_systems.system_of(system).names
    if load_type == "bolt_pretension":
        return [names["force"], names["length"]]
    dimension = LOAD_DIMENSIONS.get(load_type)
    return [names[dimension]] if dimension else []


def _check_load(where: str, load: Load) -> None:
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
    allowed = _load_units(load.type)
    if load.unit and load.unit not in allowed:
        raise ConditionError(
            f"{where}: {label} 의 단위 「{load.unit}」 는 쓸 수 없습니다 — 조건은 "
            f"mm · N · t 로 적습니다({' 또는 '.join(allowed) or '단위 없음'})"
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


def _check_analysis(analysis: Analysis) -> None:
    """해석 설정 — 그 종류가 꼭 필요로 하는 값이 있는가. 없으면 받는 쪽이 짐작하거나 멈춘다."""
    label = ANALYSIS_LABELS[analysis.type]

    def positive(value: Any) -> bool:
        return isinstance(value, str) or (value is not None and value > 0)

    span = analysis.frequency_range
    if span is not None:
        if len(span) != 2:
            raise ConditionError("analysis: 주파수 범위는 최소 · 최대 두 값입니다")
        low, high = span
        if not isinstance(low, str) and not isinstance(high, str) and not 0 <= low < high:
            raise ConditionError("analysis: 주파수 범위는 0 ≤ 최소 < 최대 여야 합니다")
    if analysis.type == "modal" and not positive(analysis.modes):
        raise ConditionError(f"analysis: {label} 의 모드 수는 1 이상입니다")
    if analysis.type == "harmonic":
        if span is None:
            raise ConditionError(f"analysis: {label} 에 주파수 범위가 없습니다")
        if analysis.method == "mode_superposition" and not positive(analysis.modes):
            raise ConditionError(
                f"analysis: {label} 을 모드 중첩으로 풀려면 모드 수가 1 이상이어야 합니다"
            )
        if isinstance(analysis.solution_intervals, int) and analysis.solution_intervals < 1:
            raise ConditionError(f"analysis: {label} 의 주파수 점 수는 1 이상입니다")
    if analysis.type == "static" and isinstance(analysis.steps, int) and analysis.steps < 1:
        raise ConditionError(f"analysis: {label} 의 하중 단계 수는 1 이상입니다")
    needs_end = analysis.type == "explicit" or (
        analysis.type == "thermal" and analysis.thermal_mode == "transient"
    )
    if needs_end and not positive(analysis.end_time):
        kind = label if analysis.type == "explicit" else "열 과도 해석"
        raise ConditionError(f"analysis: {kind} 에 끝 시간이 없습니다")
    if (
        analysis.type in ("explicit", "thermal")
        and isinstance(analysis.output_count, int)
        and analysis.output_count < 1
    ):
        raise ConditionError("analysis: 결과 저장 횟수는 1 이상입니다")


#: 정수 칸 — 식이 풀린 뒤 정수여야 하고, 수 · 단계는 1 이상이어야 한다.
_INTEGER_FIELDS = (
    "modes",
    "solution_intervals",
    "steps",
    "substeps",
    "output_count",
    "inflation_layers",
)


def _integerized(values: dict[str, Any], where: str) -> dict[str, Any]:
    """식이 풀린 정수 칸을 **정수로** — 7.0 은 7, 7.5 는 설계점을 실패로 돌린다(모드 7.5 개는
    없다). 조용히 반올림하면 사람이 준 값과 다른 해석이 돈다."""
    out = dict(values)
    for key in _INTEGER_FIELDS:
        value = out.get(key)
        if isinstance(value, float):
            if not value.is_integer():
                raise ConditionError(f"{where}.{key}: {value} 는 정수가 아닙니다")
            out[key] = int(value)
        if isinstance(out.get(key), int) and key != "inflation_layers" and out[key] < 1:
            raise ConditionError(f"{where}.{key}: 1 이상이어야 합니다(지금 {out[key]})")
    return out


def _filled_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """내보낼 해석 설정 — **그 종류가 쓰는 칸만**, 비운 것은 기본값으로 채워서. 모달에
    `end_time` 이 실려 가면 받는 쪽은 그것이 무슨 뜻인지 짐작해야 한다."""
    kind = str(analysis.get("type") or "modal")
    out: dict[str, Any] = {"type": kind}
    for key, field in Analysis.model_fields.items():
        if key == "type":
            continue
        extra: dict[str, Any] = (
            dict(field.json_schema_extra) if isinstance(field.json_schema_extra, dict) else {}
        )
        only = extra.get("only_for")
        if only is not None and kind not in only:
            continue
        # 다른 칸의 값에 따라 뜻이 있는 칸(열 과도의 시간) — 조건이 안 맞으면 뺀다.
        when = (extra.get("when") or {}).get(kind) or {}
        if any(
            (analysis.get(other) or Analysis.model_fields[other].default) != wanted
            for other, wanted in when.items()
        ):
            continue
        value = analysis.get(key)
        out[key] = field.default if value is None and field.default is not None else value
    return out


def _check_contact(where: str, contact: Contact) -> None:
    """접촉 하나 — 종류에 빠진 값 · 맞지 않는 선택을 **저장할 때** 말한다."""
    label = f"{CONTACT_LABELS[contact.type]} 접촉 「{contact.name}」"
    if contact.type == "frictional" and contact.friction is None:
        raise ConditionError(f"{where}: {label} 에 마찰계수가 없습니다")
    if contact.formulation == "mpc" and contact.type not in ("bonded", "no_separation"):
        raise ConditionError(f"{where}: {label} — MPC 정식화는 본딩 · 분리 없음에만 씁니다")
    if contact.source and contact.source == contact.target:
        raise ConditionError(f"{where}: {label} 의 접촉면과 대상면이 같습니다")


def _check_initial(where: str, initial: Initial) -> None:
    """초기조건 하나 — 종류에 빠진 값을 **저장할 때** 말한다."""
    label = INITIAL_LABELS[initial.type]
    if initial.type in ("environment_temperature", "temperature") and initial.value is None:
        raise ConditionError(f"{where}: {label} 에 온도가 없습니다")
    if initial.type in ("temperature", "velocity") and not initial.on:
        raise ConditionError(f"{where}: {label} 에 바디 선택 그룹이 없습니다")
    if initial.type == "velocity" and (not initial.vector or len(initial.vector) != 3):
        raise ConditionError(f"{where}: {label} 에 속도(X · Y · Z)가 없습니다")


def _filled_initial(initial: dict[str, Any], system: str) -> dict[str, Any]:
    """내보낼 초기조건 — 단위를 내보내기 계의 이름으로(온도는 어느 계든 °C)."""
    out = dict(initial)
    names = unit_systems.system_of(system).names
    if out.get("type") in ("environment_temperature", "temperature"):
        out["unit"] = names["temperature"]
    elif out.get("type") == "velocity":
        out["unit"] = f"{names['length']}/s"
    return out


def _filled_load(load: dict[str, Any], system: str) -> dict[str, Any]:
    """내보낼 하중 — 단위는 **내보내기 계의 이름**으로, 비운 방향은 **뜻대로 채운다.** 받는
    쪽이 기본값을 짐작하지 않게. 볼트는 적힌 단위(입력 계의 N · mm)로 예압 · 조임량을
    가른다."""
    out = dict(load)
    kind = str(out.get("type"))
    target = _load_units(kind, system)
    if kind == "bolt_pretension":
        by_length = out.get("unit") == unit_systems.system_of(INPUT_SYSTEM).names["length"]
        out["unit"] = target[1 if by_length else 0]
    elif target:
        out["unit"] = target[0]
    if out.get("direction") is None:
        if out.get("type") == "pressure":
            out["direction"] = "normal"
        elif out.get("type") == "standard_earth_gravity":
            out["direction"] = [0, 0, -1]
    return out


# ── 재료 바꿔 끼우기 — 실험계획의 재료 인자 ─────────────────────────────────


def _material_keys(one: dict[str, Any]) -> set[str]:
    """재료를 부르는 이름들 — 이름 · 번호(M-…) · MatNexus id. 사람도 AI 도 셋 중 아무것으로."""
    ref = one.get("ref") or {}
    return {str(ref[key]) for key in ("name", "code", "material_id") if ref.get(key)}


def material_index(raw: dict[str, Any], choice: str) -> int:
    """조건에 **담아 둔 재료** 중 `choice` 인 것의 자리. 없거나 여럿이면 지금 말한다."""
    materials = raw.get("materials") or []
    found = [i for i, one in enumerate(materials) if choice in _material_keys(one)]
    if not found:
        have = ", ".join(str((one.get("ref") or {}).get("name", "?")) for one in materials)
        raise ConditionError(
            f"「{choice}」 라는 재료가 조건에 없습니다 — 후보는 먼저 조건에 담아 둡니다"
            f"(담아 둔 재료: {have or '없음'})"
        )
    if len(found) > 1:
        raise ConditionError(
            f"「{choice}」 가 담아 둔 재료 {len(found)} 개에 맞습니다 — 번호(M-…)로 적으세요"
        )
    return found[0]


def with_material(raw: dict[str, Any], bodies: list[str], choice: str) -> dict[str, Any]:
    """설계점 하나의 조건 — `bodies` 에 붙은 재료를 `choice` 로 **바꿔 끼운 사본**.

    다른 재료에서 그 바디를 떼고 고른 재료에 붙인다. 후보로만 담아 둔 재료(`apply_to` 가 빈
    것)도 고를 수 있다 — 재료 훑기는 보통 「담아 두고 하나씩 붙여 본다」 이다. 원본은 그대로.
    """
    from copy import deepcopy

    out = deepcopy(raw)
    index = material_index(out, choice)
    targets = set(bodies)
    for i, one in enumerate(out.get("materials") or []):
        where = applied_bodies(one.get("apply_to", ALL_BODIES))
        if ALL_BODIES in where and ALL_BODIES not in targets and i != index:
            raise ConditionError(
                f"재료 「{(one.get('ref') or {}).get('name', '?')}」 가 「전체」 에 붙어 있어 "
                f"{', '.join(bodies)} 만 바꿔 끼울 수 없습니다 — 파트마다 재료를 지정하세요"
            )
        kept = [body for body in where if body not in targets]
        if i == index:
            kept += [body for body in bodies if body not in kept]
        one["apply_to"] = kept
    return out


# ── 칸 하나 바꾸기 · 물성 배율 — 실험계획의 고르기 · 배율 인자 ──────────────────

#: 항목을 이름으로 찾을 칸 — 이름이 없는 묶음은 다른 칸으로(초기조건은 종류, 메시 힌트는 대상).
_ITEM_KEY = {"initial": "type", "mesh_hints": "on"}


def _target_item(out: dict[str, Any], group: str, item: Any) -> dict[str, Any]:
    if group == "analysis":
        analysis = out.get("analysis")
        if not isinstance(analysis, dict):
            analysis = {"type": "modal"}
            out["analysis"] = analysis
        return analysis
    rows = out.get(group) or []
    if isinstance(item, int) and not isinstance(item, bool):
        if not 1 <= item <= len(rows):
            raise ConditionError(
                f"{group} 에 {item} 번째 항목이 없습니다(있는 것 {len(rows)} 개)"
            )
        found: dict[str, Any] = rows[item - 1]
        return found
    key = _ITEM_KEY.get(group, "name")
    hits = [one for one in rows if str(one.get(key, "")) == str(item)]
    if not hits:
        have = ", ".join(str(one.get(key, "?")) for one in rows) or "없음"
        raise ConditionError(f"{group} 에 「{item}」 이 없습니다(있는 것: {have})")
    if len(hits) > 1:
        raise ConditionError(
            f"{group} 에 「{item}」 이 여럿입니다 — 번호(1 부터)로 가리키세요"
        )
    return hits[0]


def with_choice(raw: dict[str, Any], target: Any, value: Any) -> dict[str, Any]:
    """설계점 하나의 조건 — `target`(묶음 · 항목 · 칸)의 값을 `value` 로 바꾼 **사본**.

    접촉 종류(본딩 ↔ 마찰), 구속 종류, 해석 종류, 선택 그룹, 정식화 … 고르는 칸이면 무엇이든.
    바꾼 한 벌이 조건으로서 온전한지는 부르는 쪽이 `parse` 로 본다(마찰로 바꾸면 마찰계수가
    있어야 한다 — 그것은 미리 적어 둔다)."""
    from copy import deepcopy

    group, item, field = (
        (target["group"], target.get("item"), target["field"])
        if isinstance(target, dict)
        else target
    )
    out = deepcopy(raw or {})
    _target_item(out, str(group), item)[str(field)] = value
    return out


#: 배율 인자가 부르는 물성 — 밀도 · 푸아송비는 `converted` 의 칸이고, 나머지는
#: 줄(`properties`)의 이름(`item`) 또는 표준 열쇠(`key`)로 찾는다.
_TOP_PROPERTIES = {
    "밀도": "density",
    "density": "density",
    "physical.density": "density",
    "푸아송비": "poisson_ratio",
    "poisson_ratio": "poisson_ratio",
    "mechanical.poisson_ratio": "poisson_ratio",
}


def has_property(converted: dict[str, Any], prop: str) -> bool:
    """옮긴 물성 한 벌에 그 물성이 있나 — 배율 인자를 만들기 전에 본다."""
    top = _TOP_PROPERTIES.get(prop)
    if top:
        return isinstance(converted.get(top), int | float)
    return any(
        prop in (one.get("item"), one.get("key")) for one in converted.get("properties") or []
    )


def _scaled_converted(converted: dict[str, Any], prop: str, factor: float) -> dict[str, Any]:
    from copy import deepcopy

    # **없는 물성에 곱했다고 적지 않는다.** 값은 그대로인데 `scaled` 만 붙으면 받는 쪽은 배율이
    # 걸린 줄 알고 푼다(재료를 바꿔 끼운 후보에 그 물성이 없을 때 실제로 그랬다).
    if not has_property(converted, prop):
        raise ConditionError(f"재료에 「{prop}」 가 없어 배율을 곱할 수 없습니다")
    out = deepcopy(converted)
    top = _TOP_PROPERTIES.get(prop)
    if top and isinstance(out.get(top), int | float):
        out[top] = float(f"{out[top] * factor:.12g}")
    for one in out.get("properties") or []:
        if prop in (one.get("item"), one.get("key")):
            for point in one.get("points") or []:
                if isinstance(point.get("value"), int | float):
                    point["value"] = float(f"{point['value'] * factor:.12g}")
    out["scaled"] = {**(out.get("scaled") or {}), prop: factor}
    return out


def with_scale(
    resolved: dict[str, Any], bodies: list[str], prop: str, factor: float
) -> dict[str, Any]:
    """풀린 조건 — `bodies` 에 붙은 재료의 **옮긴 값**(`converted`)에서 `prop` 에 배율을 곱한
    사본. 원본(`payload`)은 그대로다(감사의 정본). 곱한 것은 `converted.scaled` 에 적는다.

    재료가 다른 바디에도 붙어 있으면 **그 바디는 원래 값**이어야 하므로, 이 바디들만 떼어 곱한
    한 벌을 끝에 더한다(덱 번호 `mid` 는 앞의 것이 그대로다)."""
    from copy import deepcopy

    out = deepcopy(resolved)
    targets = set(bodies)
    added: list[dict[str, Any]] = []
    for one in out.get("materials") or []:
        where = applied_bodies(one.get("apply_to", []))
        hit = [b for b in where if b in targets or b == ALL_BODIES]
        if not hit or not isinstance(one.get("converted"), dict):
            continue
        # 「전체」 에 붙은 재료는 바디 하나 몫만 떼어 낼 수 없다 — 곱하면 모든 바디가 바뀐다.
        if ALL_BODIES in where and ALL_BODIES not in targets:
            raise ConditionError(
                f"재료가 「전체」 에 붙어 있어 {', '.join(bodies)} 에만 배율을 걸 수 "
                "없습니다 — 파트마다 재료를 지정하세요"
            )
        if ALL_BODIES in where or set(where) <= targets:
            one["converted"] = _scaled_converted(one["converted"], prop, factor)
            continue
        one["apply_to"] = [b for b in where if b not in targets]
        added.append(
            {
                **one,
                "apply_to": hit,
                "converted": _scaled_converted(one["converted"], prop, factor),
            }
        )
    if added:
        out["materials"] = [*out.get("materials", []), *added]
    return out


# ── 값 칸 — 내보낼 때 계를 옮긴다 ────────────────────────────────────────────

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


def _value_fields(
    conditions: dict[str, Any], system: unit_systems.System
) -> list[tuple[dict[str, Any], str, Any, str]]:
    """**계를 따르는 값 칸**들 — `(항목, 칸, 차원, 사람이 읽는 이름)`. 내보낼 때 옮기는 목록이
    하나다(칸을 더하고 여기를 빠뜨리면 그 칸만 mm 로 나간다). 볼트는 적힌 단위로 가른다."""
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
            out.append((one, "vector", _VELOCITY, f"초기조건 {index + 1} 속도"))
    for one in conditions.get("mesh_hints") or []:
        name = f"메시 힌트 「{one.get('on', '')}」"
        out.append((one, "element_size", _LENGTH, f"{name} 요소 크기"))
        out.append((one, "defeature_size", _LENGTH, f"{name} 무시할 크기"))
    return out


def expression_notes(raw: dict[str, Any], params: dict[str, Any]) -> list[dict[str, str]]:
    """값 칸의 식 중 **풀리지 않는 것** — `{where, level, text}`. 고치는 중에 알린다(저장 ·
    내보내기에서 막히기 전에). 식은 입력 계(mm · N · t)에서 도면 치수 그대로 푼다."""
    try:
        values = resolve_params({"params": params or {}})
    except ExpressionError:
        return []
    notes: list[dict[str, str]] = []
    system = unit_systems.system_of(INPUT_SYSTEM)
    for item, key, _, label in _value_fields(raw, system):
        texts = item.get(key)
        for text in texts if isinstance(texts, list) else [texts]:
            if isinstance(text, str) and text.startswith("="):
                try:
                    _expr(text, values)
                except ExpressionError as failure:
                    notes.append({"where": label, "level": "warn", "text": str(failure)})
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
            "accepts": CONSTRAINT_ACCEPTS,
        },
        "loads": {
            "label": "하중",
            "model": Load,
            "notes": LOAD_NOTES,
            "dimensions": LOAD_DIMENSIONS,
            "accepts": LOAD_ACCEPTS,
        },
        "contacts": {
            "label": "접촉",
            "model": Contact,
            "notes": CONTACT_NOTES,
            "accepts": CONTACT_ACCEPTS,
            "intro": "두 선택 그룹이 맞닿는 자리입니다. 접촉면 · 대상면을 고르고, 붙어 있는지 "
            "미끄러지는지를 종류로 정합니다. 모르는 칸은 「프로그램이 정함」 그대로 둡니다.",
        },
        "initial": {
            "label": "초기조건",
            "model": Initial,
            "notes": INITIAL_NOTES,
            "accepts": INITIAL_ACCEPTS,
            "intro": "풀기 전의 상태입니다 — 기준 온도, 처음 온도 · 속도, 앞선 해석의 응력.",
        },
        "mesh_hints": {
            "label": "메시 힌트",
            "model": MeshHint,
            "accepts": MESH_ACCEPTS,
            "intro": "메시는 받는 쪽(SimEngBay)이 만듭니다 — 여기 적는 것은 바람입니다. "
            "비운 칸은 받는 쪽이 정합니다.",
        },
    }
    out: dict[str, Any] = {
        "schema_version": 1,
        "units": Units().model_dump(),
        # 조건의 값을 적는 계 — 화면이 칸마다 단위(mm · N · MPa)를 붙인다. `units.system` 은
        # 내보내기 계다.
        "input_system": INPUT_SYSTEM,
        # **고를 수 있는 단위계.** 화면에 목록을 박으면 계를 더할 때마다 화면을 고쳐야
        # 한다 — 조건 종류와 같은 까닭으로 정본은 서버다.
        "unit_systems": [
            {"key": one.key, "label": one.label, **one.names}
            for one in unit_systems.SYSTEMS.values()
        ],
        # 해석 설정은 한 벌에 하나라 묶음(`groups`)이 아니지만, 화면은 같은 폼으로 그린다 —
        # 종류마다 한 줄 설명과 창 맨 위 안내를 함께 싣는다.
        "analysis": {
            **Analysis.model_json_schema(),
            "notes": ANALYSIS_NOTES,
            "intro": _ANALYSIS_INTRO,
        },
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
            # 묶음 전체에 대한 한두 줄 — 창 맨 위에 보인다.
            "intro": one.get("intro", ""),
            "dimensions": one.get("dimensions", {}),
            # 종류마다 받는 선택 그룹 — `[{entity, kind?}]`. 없는 종류는 대상이 없다.
            "accepts": one.get("accepts", {}),
        }
    out["entities"] = ["face", "edge", "vertex", "body"]
    return out
