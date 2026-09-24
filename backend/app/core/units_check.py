"""우리 단위 환산이 **MatNexus 와 같은 말을 하는가.**

그쪽은 지금도 고쳐지고 있다(이 대화 중에 `density_si` 칸이 생겼다). 사람이 눈으로 맞춰 보는
것은 오래 못 간다 — 어긋나면 **검사가 말하게** 둔다.

우리는 그쪽 등록부를 런타임에 의존하지 않는다(꺼져 있어도 내보내기는 돼야 하고, 올려 둔
사본으로 골라도 마찬가지다). 이것은 **맞춰 보기**이지 가져오기가 아니다.
"""

from __future__ import annotations

from typing import Any

from app.core import units

#: 카드의 SI 단위 선언 — 우리가 그 값을 어떤 단위로 읽어야 하는가.
_CARD_SI: dict[str, str] = {
    "density": "kg/m3",
    "youngs_modulus": "Pa",
    "shear_modulus": "Pa",
    "yield_stress": "Pa",
    "equilibrium_pa": "Pa",
    "instantaneous_pa": "Pa",
    "specific_heat": "J/(kg.K)",
    "conductivity": "W/(m.K)",
    "thermal_expansion": "1/K",
}


def compare_numbers(
    si_card: dict[str, Any], their_card: dict[str, Any], system: str
) -> dict[str, Any]:
    """**숫자까지 맞춰 본다** — 같은 카드를 SI 와 그 계로 각각 받아, SI 값을 우리가 환산한
    것이 그쪽 값과 같은가.

    기호 이름만 맞추면 **배수가 틀려도 모른다.** 그쪽이 환산해 준 것이 정답지다.
    """
    problems: list[str] = []
    checked = 0
    for name, block in (si_card.get("blocks") or {}).items():
        theirs_block = (their_card.get("blocks") or {}).get(name) or {}
        si_values = (block or {}).get("values") or {}
        their_values = theirs_block.get("values") or {}
        for field, si_value in si_values.items():
            unit = _CARD_SI.get(field)
            if unit is None or not isinstance(si_value, int | float):
                continue
            expected = their_values.get(field)
            if not isinstance(expected, int | float):
                continue
            made, _, ok = units.convert(float(si_value), unit, system)
            checked += 1
            if not ok:
                problems.append(f"{name}.{field}: 우리가 {unit} 를 못 읽는다")
            elif expected == 0:
                if made != 0:
                    problems.append(f"{name}.{field}: 그쪽 0 · 우리 {made}")
            elif abs(made - expected) / abs(expected) > 1e-9:
                problems.append(f"{name}.{field}: 그쪽 {expected!r} · 우리 {made!r}")
    return {"ok": not problems, "problems": problems, "checked": checked}


def compare(theirs: list[dict[str, Any]]) -> dict[str, Any]:
    """그쪽 등록부와 우리 표를 맞춰 본다 — **다른 것만** 돌려준다.

    보는 것 셋:

    - **계 이름**: 우리가 아는 계를 그쪽도 아는가(열쇠를 맞춰 뒀다).
    - **기호표**: 같은 SI 단위를 그 계에서 같은 이름으로 부르는가. 표가 아니라 **실제로
      환산해 보고** 그 답을 비교한다 — 표만 맞춰 보면 「값이 안 바뀌면 들어온 기호를 그대로
      둔다」 같은 규칙을 놓친다.
    - **모르는 단위**: 그쪽 기호표에 있는데 우리 표에 없는 것 — 그것이 오는 날 우리는
      환산을 포기하고 `unconverted` 에 적는다(조용히 틀리지는 않지만, 알고는 있어야 한다).
    """
    problems: list[str] = []
    seen: set[str] = set()
    for one in theirs:
        key = str(one.get("key") or "")
        seen.add(key)
        ours = units.SYSTEMS.get(key)
        if ours is None:
            problems.append(f"그쪽에만 있는 계: {key} ({one.get('label')})")
            continue
        for si_name, their_name in (one.get("symbols") or {}).items():
            if si_name not in units.KNOWN:
                problems.append(f"우리가 못 읽는 SI 기호: {si_name} ({key} 에서 {their_name})")
                continue
            # **표가 아니라 행동을 본다.** 표를 맞춰 보면 「값은 안 바뀌니 들어온 기호를
            # 그대로 둔다」 같은 규칙을 놓친다 — 실제로 환산해 보고 그 답을 비교한다.
            _, our_name, ok = units.convert(1.0, si_name, key)
            if not ok:
                problems.append(f"{key}.{si_name}: 우리가 환산을 포기한다")
            elif our_name != their_name:
                problems.append(
                    f"{key}.{si_name}: 그쪽 「{their_name}」 · 우리 「{our_name}」"
                )
    for key in units.SYSTEMS:
        if key not in seen:
            problems.append(f"우리에게만 있는 계: {key}")
    return {"ok": not problems, "problems": problems, "compared": sorted(seen)}
