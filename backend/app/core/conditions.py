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


def parse(raw: dict[str, Any] | None, bodies: list[str] | None = None) -> Conditions:
    """읽어서 검증한다. **틀린 자리를 짚어 말한다** — 「조건이 잘못됐습니다」 로는 못 고친다.

    `bodies` 를 주면 **물성이 붙은 바디가 진짜 있는지**도 본다(`topology.bodies` 의 이름).
    없는 이름에 물성을 붙이면 해석 쪽이 그 바디에 아무 물성도 못 얹고, 그 사실은 푸는
    날에야 드러난다 — 이름표를 가리킬 때와 같은 까닭이다.
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

    여기서 **단위계도 함께 푼다**: `units` 를 닫힌 선언으로 펼치고, 물성마다 그 계로 옮긴
    값(`converted`)을 **원본 옆에** 놓는다. 원본은 안 건드린다 — 감사할 때는 원본, 풀 때는
    변환값이다. MatNexus 가 밀도만 `tonne/mm3` 로 주고 나머지는 SI 로 주므로, 이것이 없으면
    받는 쪽이 밀도는 맞고 탄성계수는 10⁶ 배 틀린 채로 푼다.
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
        out = {key: walk(one) for key, one in conditions.items()}
    except ExpressionError as failure:
        raise ConditionError(f"조건의 식을 풀지 못했습니다: {failure}") from failure
    system = str((out.get("units") or {}).get("system") or unit_systems.DEFAULT_SYSTEM)
    out["units"] = unit_systems.declaration(system)
    out["materials"] = [
        _with_converted(one, system, keys or {}) for one in out.get("materials", [])
    ]
    return out


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
        }
    out["entities"] = ["face", "edge", "vertex", "body"]
    return out
