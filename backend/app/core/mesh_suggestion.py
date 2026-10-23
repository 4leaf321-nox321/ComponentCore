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

**절점 수 상한**(2026-10-23, SimEngBay 의 의견): 그 크기로 지은 메시의 절점 수를 셈해
(`estimate_nodes`) 상한(기본 10만 — `MESH_SUGGESTION_MAX_NODES`)을 넘으면 상한 안에 드는
가장 작은 깔끔한 수까지 키운다. 보드굽힘 시편에 0.6 mm 를 제안했더니 CalculiX 가 감당 못 할
크기(1 mm 에서 이미 25만 절점 · 30분 넘음)였고, 운영에서 메모리가 바닥난 적이 있다. 키운 만큼
얇은 벽은 요소가 모자라니 그 자리는 국부 메시로 촘촘히 한다(`basis` 가 그렇게 말한다).
"""

from __future__ import annotations

import math
from typing import Any

#: 깔끔한 수 — 사람이 조건에 적을 법한 값.
NICE = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0)
#: 규칙을 한 줄로 — 점 파일에 함께 싣는다(받는 쪽이 어떻게 나온 값인지 안다).
RULE = (
    "최소 벽 두께/2 를 가장 긴 변/200 ~ 1/20 사이로 맞추고 깔끔한 수로 내림(mm)"
    " · 추정 절점 수가 상한을 넘으면 그 안에 들 때까지 키움"
)
#: 솔리드 절점 수의 계수 — 보드굽힘 시편(부피 10,164 mm³ · 두께 1 mm)을 요소 1 mm 로 나누면
#: 25만 절점이었다(SimEngBay 의 CalculiX 실측, 2026-10-16 — 2차 사면체).
SOLID_NODES = 25.0
#: 쉘 절점 수의 계수 — 2차 사각 셸(넓이 h² 마다 절점 셋쯤)의 근사.
SHELL_NODES = 3.0
#: 절점 수 상한의 기본 — 2 mm(추정 6만)가 30분, 1 mm(25만)는 30분을 넘겼다(보드굽힘, CalculiX).
DEFAULT_MAX_NODES = 100_000


def _nice_next(value: float) -> float:
    """`value` 보다 큰 가장 작은 깔끔한 수."""
    exponent = math.floor(math.log10(value))
    for scale in (10.0**exponent, 10.0 ** (exponent + 1)):
        for one in NICE:
            if one * scale > value * (1 + 1e-9):
                return round(one * scale, 6)
    raise AssertionError("깔끔한 수가 없다")  # pragma: no cover - 위 두 자릿수 안에 늘 있다


def estimate_nodes(
    size: float,
    bodies: list[dict[str, Any]] | None,
    walls: dict[str, float],
    *,
    shell: frozenset[str],
    unmeshed: frozenset[str],
    shell_areas: dict[str, float],
) -> int:
    """요소 크기 `size`(mm)로 지은 메시의 **절점 수 짐작** — 상한을 거는 데 쓴다.

    솔리드: `SOLID_NODES` * 부피 / (h² * min(h, 그 파트의 최소 벽)) — 얇은 판은 두께 방향에
    한 층은 생기므로 h³ 이 아니라 h² * 두께로 센다. 쉘(시트 · 쉘로 푸는 파트): `SHELL_NODES` *
    넓이 / h²(쉘로 푸는 솔리드는 중간면 넓이, 없으면 겉넓이의 절반). 강체 · 해석 제외는 0."""
    total = 0.0
    for one in bodies or []:
        name = str(one.get("name") or "")
        if name in unmeshed:
            continue
        if one.get("kind") == "sheet" or name in shell:
            area = shell_areas.get(name)
            if area is None:
                whole = float(one.get("area") or 0.0)
                area = whole if one.get("kind") == "sheet" else whole / 2
            total += SHELL_NODES * area / size**2
            continue
        volume = float(one.get("volume") or 0.0)
        wall = walls.get(name)
        depth = min(size, wall) if wall else size
        total += SOLID_NODES * volume / (size * size * depth)
    return round(total)


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
    shell: frozenset[str] = frozenset(),
    shell_areas: dict[str, float] | None = None,
    max_nodes: int | None = DEFAULT_MAX_NODES,
) -> dict[str, Any] | None:
    """설계점 하나의 제안값 — 크기를 모르면(바디가 없다) None.

    `in_conditions` 는 사람이 조건에 전역 크기(국부 메시 「전체」 의 요소 크기)를 적었나 —
    적었으면 받는 쪽은 그 값을 쓴다(제안값은 참고로만). `skip_wall` 은 벽 두께에서 뺄 파트(해석
    제외 · 쉘 · 강체), `skip_size` 는 크기에서 뺄 파트(해석 제외) — `conditions.mesh_skips`.
    `shell` 은 쉘로 푸는 파트(절점 수를 넓이로 센다), `shell_areas` 는 그 중간면 넓이,
    `max_nodes` 는 절점 수 상한(None 이면 걸지 않는다)."""
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
    size = nice_floor(value)
    walls = {
        str(name): float(one)
        for name, one in ((quality or {}).get("min_wall_by_body") or {}).items()
        if isinstance(one, int | float) and one > 0
    }
    if not walls and isinstance(wall, int | float) and len(bodies or []) == 1:
        walls = {str((bodies or [{}])[0].get("name") or "전체"): float(wall)}  # 옛 점검 · 단품

    def nodes(at: float) -> int:
        return estimate_nodes(
            at,
            bodies,
            walls,
            shell=shell,
            unmeshed=skip_wall - shell,
            shell_areas=shell_areas or {},
        )

    estimated = nodes(size)
    capped_from: float | None = None
    if max_nodes and estimated > max_nodes:
        capped_from, before = size, estimated
        for _ in range(60):  # 깔끔한 수로 한 칸씩 — 열 칸이면 10 배다
            size = _nice_next(size)
            estimated = nodes(size)
            if estimated <= max_nodes:
                break
        basis += (
            f" · 그 크기({capped_from:g} mm)는 절점이 {before:,}개쯤이라 "
            f"상한({max_nodes:,})을 넘어 {size:g} mm 로 키웠다 — 얇은 벽은 국부 메시로 촘촘히"
        )
    return {
        "element_size": size,
        "basis": basis,
        "rule": RULE,
        "in_conditions": in_conditions,
        "inputs": {
            "min_wall": wall,
            "wall_body": thinnest,
            "longest": round(longest, 3),
            "skipped": sorted(skip_wall),
            "nodes_estimate": estimated,
            "max_nodes": max_nodes,
            "capped_from": capped_from,
        },
    }
