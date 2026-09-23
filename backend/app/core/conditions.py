"""해석 조건 — **솔버를 모르는 중립 표현.**

경계조건 · 하중 · 접촉 · 초기조건 · 해석 설정 · 물성을 한 벌로 적는다. 이 플랫폼은 메시도
솔브도 하지 않고 결과도 받지 않는다 — 조건을 **파일로 넘기는 데까지**가 일이다. 받는 쪽이
하나가 아니므로(Ansys · 그 밖) 여기 적힌 말은 어느 솔버의 것도 아니어야 하고, 솔버별 매핑은
받는 쪽이 들고 있다. 설계는 `docs/해석-조건-설계.md`.

## 조건은 면을 직접 가리키지 않는다

모든 조건은 **이름표(named_selections)** 만 가리킨다. 이름표는 좌표가 아니라 **셀렉터**
(`query.find_features` 의 말)로 적혀 있어서, 실험계획이 치수를 바꿔도 설계점마다 다시 풀린다.
「(30, 15, 5) 의 면」 은 두께를 바꾸는 순간 그 자리에 없지만 「아래쪽 면」 은 남는다.

그리고 같은 면에 하중과 메시 힌트를 따로 걸어도 **고칠 자리가 하나**다.

## 숫자 칸에는 식을 쓸 수 있다

레시피와 **같은 자리, 같은 문법**이다 — `"=압력"` · `"=두께 * 120"`. 변수는 레시피의
`params` 를 그대로 쓰므로, 실험계획이 그 변수를 훑으면 **형상과 조건이 함께 움직인다.**
푸는 것은 `core/recipe/params.resolve()` — dict 를 훑는 함수라 조건에도 그대로 듣는다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.recipe.params import ExpressionError, resolve_params
from app.core.recipe.params import evaluate_expression as _expr

#: 숫자 칸 — 수 또는 `"=식"`.
Number = float | int | str


class ConditionError(ValueError):
    """조건이 말이 안 된다 — 어느 줄의 무엇이 문제인지 말한다."""


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 이름표 ────────────────────────────────────────────────────────────────────


class NamedSelection(Base):
    """조건이 붙는 **유일한 창구**. 셀렉터로 적고 설계점마다 다시 푼다."""

    name: str = Field(min_length=1, max_length=60)
    entity: Literal["face", "edge", "vertex", "body"] = "face"
    select: dict[str, Any] = Field(default_factory=dict)
    """`query.find_features` 의 질의. `body` 면 `topology.bodies` 의 이름을 가리킨다."""


# ── 물성 ──────────────────────────────────────────────────────────────────────


class MaterialRef(Base):
    source: str = "matnexus"
    code: str = ""
    """MatNexus 의 불변 번호(`M-000123`). 손입력이면 비어 있다."""
    name: str = ""
    fetched_at: str = ""


class Material(Base):
    """**값을 해석하지 않는다.** 물성 플랫폼이 준 것을 통째로 나른다 — 「어느 것이 영률인가」
    는 솔버를 아는 쪽의 일이다(설계 문서 6장)."""

    apply_to: str = "전체"
    """`topology.bodies` 의 이름. 「전체」 면 모든 바디."""
    ref: MaterialRef = Field(default_factory=MaterialRef)
    payload: dict[str, Any] = Field(default_factory=dict)


# ── 조건들 ────────────────────────────────────────────────────────────────────


class Constraint(Base):
    """구속 — 움직이지 못하게 한다."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal[
        "fixed_support", "displacement", "frictionless", "cylindrical", "compression_only"
    ]
    on: str
    cs: str = "global"
    x: Number | None = None
    y: Number | None = None
    z: Number | None = None
    """`displacement` 의 성분. **`null` 은 자유다** — 0 과 다르다."""


class Load(Base):
    """하중 — 밀거나 당기거나 조인다."""

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
    ]
    on: str = ""
    """중력처럼 온 몸에 걸리는 것은 비어 있다."""
    magnitude: Number | None = None
    unit: str = ""
    """`MPa` · `N` · `N*mm` … **단위를 값에서 떼지 않는다** — 물성에서 그것이 10¹² 배로
    틀린 적이 있다(MatNexus 의 실측)."""
    direction: list[Number] | Literal["normal"] | None = None
    preload: Number | None = None
    """`bolt_pretension` — 예압(N) 또는 조임량(mm), `unit` 이 가른다."""


class Contact(Base):
    """접촉 — 두 이름표가 만나는 자리."""

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
    length: str = "mm"
    mass: str = "kg"
    time: str = "s"
    force: str = "N"
    temperature: str = "C"


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


EMPTY: dict[str, Any] = Conditions().model_dump()


# ── 검증 ──────────────────────────────────────────────────────────────────────


def _known_names(conditions: Conditions) -> set[str]:
    return {one.name for one in conditions.named_selections}


def parse(raw: dict[str, Any] | None) -> Conditions:
    """읽어서 검증한다. **틀린 자리를 짚어 말한다** — 「조건이 잘못됐습니다」 로는
    못 고친다."""
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
            "이름표 이름이 겹칩니다 — 조건이 어느 것을 가리킬지 알 수 없습니다"
        )

    # **가리키는 이름표가 없으면 지금 말한다.** 안 그러면 내보낸 뒤 해석 쪽에서 0 개를 집고,
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
                        f"{group}[{index}]: 「{target}」 라는 이름표가 없습니다 "
                        f"(있는 것: {', '.join(sorted(names)) or '없음'})"
                    )
    return conditions


def resolve(raw: dict[str, Any] | None, params: dict[str, Any]) -> dict[str, Any]:
    """`"=식"` 을 그 설계점의 값으로 바꾼 **새 사본**. 레시피와 같은 문법이다.

    받는 쪽은 식을 풀 수 없다 — 설계점마다 **풀린 값**을 내보내야 한다.
    """
    conditions = parse(raw).model_dump()
    values = resolve_params({"params": params})

    def walk(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("="):
            return _expr(value, values)
        if isinstance(value, list):
            return [walk(one) for one in value]
        if isinstance(value, dict):
            return {key: walk(one) for key, one in value.items()}
        return value

    try:
        return {key: walk(one) for key, one in conditions.items()}
    except ExpressionError as failure:
        raise ConditionError(f"조건의 식을 풀지 못했습니다: {failure}") from failure


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
        "constraints": {"label": "구속", "model": Constraint},
        "loads": {"label": "하중", "model": Load},
        "contacts": {"label": "접촉", "model": Contact},
        "initial": {"label": "초기조건", "model": Initial},
        "mesh_hints": {"label": "메시 힌트", "model": MeshHint},
    }
    out: dict[str, Any] = {
        "schema_version": 1,
        "units": Units().model_dump(),
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
        }
    out["entities"] = ["face", "edge", "vertex", "body"]
    return out
