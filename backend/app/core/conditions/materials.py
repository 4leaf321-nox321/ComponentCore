"""재료 — 물성 참조 · 단위 옮기기 · 구조 물성 점검 · 실험계획의 재료 인자 · 물성 배율.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from app.core import units as unit_systems
from app.core.conditions import registry
from app.core.conditions.cases import raw_views
from app.core.conditions.common import ALL_BODIES, Base, ConditionError, applied_bodies

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


def unmaterialed(raw: dict[str, Any] | None, bodies: list[str]) -> list[str]:
    """**해석 제외가 아닌데 재료가 없는 파트** — 바디 이름 순서대로.

    받는 쪽(SimEngBay)은 이런 설계점을 걸지 않는다: 강체도 요소로 메시하면 재료 단면이 있어야
    하고, 질량 · 관성이 고유진동수를 바꾼다(2026-10-23). 「전체」 에 붙은 재료는 모든 파트를
    덮는다."""
    if not isinstance(raw, dict):
        return list(bodies)
    taken: set[str] = set()
    for one in raw.get("materials") or []:
        if isinstance(one, dict):
            taken.update(applied_bodies(one.get("apply_to")))
    if ALL_BODIES in taken:
        return []
    off = {
        str(one.get("name"))
        for one in raw.get("body_settings") or []
        if isinstance(one, dict) and one.get("suppressed")
    }
    return [one for one in bodies if one not in taken and one not in off]


def body_density(resolved: dict[str, Any] | None, body: str) -> float | None:
    """그 파트의 밀도 — **내보내기 계의 값**(`resolve` 가 채운
    `materials[].converted.density`).

    바디 하나에 물성은 하나다(`parse` 가 막는다). 「전체」 에 붙은 물성은 모든 파트를 덮는다.
    밀도가 없으면 None — 질량을 짐작하지 않는다(밀도 없는 강체는 기본값으로 풀려 그럴듯한 답이
    난다, 설계 문서 동역학 3장)."""
    if not isinstance(resolved, dict):
        return None
    for one in resolved.get("materials") or []:
        if not isinstance(one, dict):
            continue
        where = applied_bodies(one.get("apply_to"))
        if body in where or ALL_BODIES in where:
            density = (one.get("converted") or {}).get("density")
            return float(density) if isinstance(density, int | float) else None
    return None


def _points_of(one: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (one.get("points") or []) if isinstance(p, dict)]


def _celsius(point: dict[str, Any]) -> float | None:
    """물성 점의 온도(°C). **MatNexus 는 켈빈으로 준다**(`temperature_k`) — 그것을 안 읽어
    온도별 값이 모두 「온도 없음」 으로 나가, 받는 쪽이 여러 값 중 아무것이나 고를 수 있었다
    (2026-11-17). `temperature_C` 가 있으면 그것."""
    celsius = point.get("temperature_C")
    if isinstance(celsius, int | float):
        return float(celsius)
    kelvin = point.get("temperature_k")
    if isinstance(kelvin, int | float):
        return round(float(kelvin) - 273.15, 6)
    return None


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
                "temperature_C": _celsius(point),
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


def material_warnings(resolved: dict[str, Any] | None) -> list[str]:
    """풀린 조건의 재료 중 **그대로 풀면 틀리는 것** — 내보낸 점의 경고(manifest `warnings`).

    - 구조 해석인데 탄성계수 · 푸아송비 · 밀도가 빠졌다(`missing_structural`). 받는 쪽이
      재료를 거절하거나 기본값(구조용 강)으로 풀고, 그것은 고유진동수가 틀린 뒤에야 드러난다.
      고를 때만 말하고 그 뒤에는 조용했다(2026-11-17).
    - 단위를 못 바꾼 물성(`unconverted`) — 값이 원래 단위 그대로라 계가 섞인다.

    파트에 붙지 않은 재료는 내보내도 쓰이지 않으므로 뺀다. 열 해석은 탄성계수가 필요 없다."""
    if not isinstance(resolved, dict):
        return []
    # 해석 케이스가 여럿이면(v2) 그중 하나라도 구조 해석이면 구조 물성이 필요하다.
    structural = any(
        registry.structural((view.get("analysis") or {}).get("type"))
        for _, view in raw_views(resolved)
    )
    out: list[str] = []
    for one in resolved.get("materials") or []:
        if not isinstance(one, dict) or not one.get("apply_to"):
            continue
        converted = one.get("converted") or {}
        ref = one.get("ref") or {}
        name = str(ref.get("name") or ref.get("code") or "이름 없음")
        missing = converted.get("missing_structural") or []
        if structural and missing:
            out.append(f"재료 ‘{name}’: {', '.join(missing)} 없음 — 구조 해석에 필요합니다")
        if converted.get("unconverted"):
            out.append(
                f"재료 ‘{name}’: 단위를 바꾸지 못한 물성 {', '.join(converted['unconverted'])}"
            )
    return out


def _with_converted(
    material: dict[str, Any], system: str, keys: dict[str, str]
) -> dict[str, Any]:
    payload = material.get("payload")
    if not isinstance(payload, dict) or not payload:
        return material
    return {**material, "converted": converted_material(payload, system, keys)}


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
            f"재료 ‘{choice}’이(가) 조건에 없습니다. 후보 재료를 먼저 조건에 "
            f"추가하십시오(추가된 재료: {have or '없음'})."
        )
    if len(found) > 1:
        raise ConditionError(
            f"‘{choice}’에 해당하는 재료가 {len(found)}개입니다. 재료 번호(M-…)로 "
            "지정하십시오."
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
                f"재료 ‘{(one.get('ref') or {}).get('name', '?')}’이(가) ‘전체’에 "
                f"지정되어 있어 {', '.join(bodies)}의 재료만 교체할 수 없습니다. 파트별로 "
                "재료를 지정하십시오."
            )
        kept = [body for body in where if body not in targets]
        if i == index:
            kept += [body for body in bodies if body not in kept]
        one["apply_to"] = kept
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
        raise ConditionError(f"재료에 ‘{prop}’ 물성이 없어 배율을 적용할 수 없습니다.")
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
                f"재료가 ‘전체’에 지정되어 있어 {', '.join(bodies)}에만 배율을 적용할 수 "
                "없습니다. 파트별로 재료를 지정하십시오."
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
