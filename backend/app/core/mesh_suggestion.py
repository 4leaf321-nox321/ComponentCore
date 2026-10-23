"""전역 요소 크기 **제안** — 사람이 메시 크기를 안 정했을 때 해석 쪽이 쓸 값(2026-10-23).

DOE 를 만들며 메시를 정하지 않고 내보내는 일이 잦다. 그러면 해석 플랫폼(SimEngBay)이 제
기준으로 전역 크기를 정해야 했고, 솔버마다 기준이 다르면 같은 설계점이 다르게 풀린다. 형상을
가진 쪽이 **늘 같은 규칙으로** 제안하고, 받는 쪽은 사람이 정한 값(조건의 국부 메시 「전체」 ·
파트별 메시)이 없을 때만 쓴다. 조건(`conditions`)에는 넣지 않는다 — 사람이 정한 값과 섞이면
누가 정했는지 모른다.

규칙(mm — 도면 단위):

- 벽: 최소 벽 두께(형상 점검 `quality.min_wall`)의 절반 — 가장 얇은 벽에 요소 두 개.
- 위 한도: 모델의 가장 긴 변(바디 경계상자를 합친 것)의 1/20 — 그 방향에 요소 스무 개
  이상.
- 아래 한도: 가장 긴 변의 1/200 — 요소 수가 터지지 않게.

벽 값을 두 한도 사이로 맞추고 **깔끔한 수로 내려** 맞춘다(1 · 1.2 · 1.5 · 2 · 2.5 · 3 · 4 ·
5 · 6 · 8 에 10 의 거듭제곱). 벽 두께를 모르면(시트만 있다 · 형상 점검을 껐다) 위 한도를
쓴다.
"""

from __future__ import annotations

import math
from typing import Any

#: 깔끔한 수 — 사람이 조건에 적을 법한 값.
NICE = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)
#: 규칙을 한 줄로 — 점 파일에 함께 싣는다(받는 쪽이 어떻게 나온 값인지 안다).
RULE = "최소 벽 두께/2 를 가장 긴 변/200 ~ 1/20 사이로 맞추고 깔끔한 수로 내림(mm)"


def nice_floor(value: float) -> float:
    """`value` 이하의 가장 큰 깔끔한 수."""
    if value <= 0:
        raise ValueError(f"양수여야 합니다: {value}")
    exponent = math.floor(math.log10(value))
    scale = 10.0**exponent
    mantissa = value / scale
    picked = max(one for one in NICE if one <= mantissa + 1e-9)
    return round(picked * scale, 6)


def _longest(bodies: list[dict[str, Any]] | None) -> float | None:
    """바디 경계상자를 합친 상자의 가장 긴 변(mm)."""
    boxes = [one["bbox"] for one in bodies or [] if isinstance(one, dict) and one.get("bbox")]
    if not boxes:
        return None
    low = [min(float(box[0][axis]) for box in boxes) for axis in range(3)]
    high = [max(float(box[1][axis]) for box in boxes) for axis in range(3)]
    return max(top - bottom for top, bottom in zip(high, low, strict=True))


def _thinnest(
    quality: dict[str, Any] | None, skip: frozenset[str]
) -> tuple[float | None, str | None]:
    """솔리드로 푸는 파트의 최소 벽 두께와 그 파트 — 파트별 벽(`min_wall_by_body`)이 없는 옛
    점검이면 전체의 값."""
    walls = (quality or {}).get("min_wall_by_body")
    if not isinstance(walls, dict):
        whole = (quality or {}).get("min_wall")
        return (
            (float(whole), None)
            if isinstance(whole, int | float) and whole > 0
            else (None, None)
        )
    kept = {
        str(name): float(value)
        for name, value in walls.items()
        if name not in skip and isinstance(value, int | float) and value > 0
    }
    if not kept:
        return None, None
    name = min(kept, key=kept.__getitem__)
    return kept[name], name


def suggest(
    bodies: list[dict[str, Any]] | None,
    quality: dict[str, Any] | None,
    *,
    in_conditions: bool,
    skip_wall: frozenset[str] = frozenset(),
    skip_size: frozenset[str] = frozenset(),
) -> dict[str, Any] | None:
    """설계점 하나의 제안값 — 크기를 모르면(바디가 없다) None.

    `in_conditions` 는 사람이 조건에 전역 크기(국부 메시 「전체」 의 요소 크기)를 적었나 —
    적었으면 받는 쪽은 그 값을 쓴다(제안값은 참고로만). `skip_wall` 은 벽 두께에서 뺄 파트(해석
    제외 · 쉘 · 강체), `skip_size` 는 크기에서 뺄 파트(해석 제외) — `conditions.mesh_skips`."""
    sized = [one for one in bodies or [] if one.get("name") not in skip_size] or bodies
    longest = _longest(sized)
    if longest is None or longest <= 0:
        return None
    upper, lower = longest / 20, longest / 200
    wall, thinnest = _thinnest(quality, skip_wall)
    where = f", 「{thinnest}」" if thinnest and thinnest != "전체" else ""
    if isinstance(wall, int | float) and wall > 0:
        half = float(wall) / 2
        if half > upper:
            value = upper
            basis = (
                f"가장 긴 변({longest:g} mm)의 1/20 — 벽({wall:g} mm)의 절반보다 작게, "
                "그 방향에 요소 스무 개 이상"
            )
        elif half < lower:
            value = lower
            basis = (
                f"가장 긴 변({longest:g} mm)의 1/200 — 벽({wall:g} mm)의 절반은 더 작지만 "
                "요소 수가 터지지 않게(얇은 벽은 국부 메시로)"
            )
        else:
            value = half
            basis = f"최소 벽 두께({wall:g} mm{where})의 절반 — 가장 얇은 벽에 요소 두 개"
    else:
        value = upper
        why = (
            "솔리드로 푸는 파트의 벽이 없다(쉘 · 강체 · 해석 제외만 있다)"
            if skip_wall & set((quality or {}).get("min_wall_by_body") or {})
            else "벽 두께를 모른다(시트만 있거나 형상 점검을 껐다)"
        )
        basis = f"가장 긴 변({longest:g} mm)의 1/20 — {why}"
    return {
        "element_size": nice_floor(value),
        "basis": basis,
        "rule": RULE,
        "in_conditions": in_conditions,
        "inputs": {
            "min_wall": wall,
            "wall_body": thinnest,
            "longest": round(longest, 3),
            "skipped": sorted(skip_wall),
        },
    }
