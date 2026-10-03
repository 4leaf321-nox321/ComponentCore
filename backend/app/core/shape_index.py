"""형상 색인 — 이름이 아니라 **형상으로** 찾을 수 있게, 만든 김에 한 번 뽑아 두는 값.

「M6 구멍이 있는 판」 · 「100 x 60 안에 드는 것」 · 「Ø6.6 구멍 4 개 이상」 · 「판금으로 굽힌
부품」 을 찾으려고 형상을 다시 만들 수는 없다(수백 개면 몇 분). 버전을 평가하는 작업(CAD ·
지그)이 끝날 때 여기 값을 작업 요약(`summary.shape`)에 적어 두고, 목록은 **최신 버전의 것**만
본다 — 찾는 것은 보통 지금 모양이다.

- 레시피에서(①): 쓴 연산(`ops`), 나사 호칭(`threads` — 구멍 · 볼트 · 너트의 `thread`), 변수
  이름(`params`). 가져온 STEP 만 있는 버전은 비어 있다.
- 형상에서(②): 경계상자(`size`)와 **작은 것부터 늘어놓은 세 변**(`dims` — 놓인 방향과 상관없이
  「이 상자 안에 드나」), 부피 · 겉넓이 · 솔리드 수, 구멍(지름으로 묶어 개수 · 그중 관통).
"""

from __future__ import annotations

import math
from typing import Any

#: 색인의 모양이 바뀌면 올린다 — 채우기(backfill)가 옛 색인을 알아본다.
VERSION = 1

#: 화면 · MCP 가 쓰는 「무엇이 들어 있나」 의 말 — 여러 연산을 한 낱말로 묶는다.
FEATURES: dict[str, tuple[str, ...]] = {
    "hole": ("hole",),
    "sheet_metal": ("sheet_metal", "bend", "unfold"),
    "frame": ("frame",),
    "fillet": ("fillet",),
    "chamfer": ("chamfer",),
    "pattern": ("pattern", "mirror"),
    "fastener": ("bolt", "nut", "washer", "pin", "fasten", "standoff"),
    "shell": ("shell",),
    "sweep": ("sweep", "loft", "helix"),
    "revolve": ("revolve",),
    "assembly": ("component",),
    "step": ("import_step",),
}


def from_recipe(recipe: dict[str, Any] | None) -> dict[str, list[str]]:
    """레시피에서 — 연산 · 나사 호칭 · 변수 이름(가나다순, 겹침 없이)."""
    nodes = (recipe or {}).get("nodes") or []
    ops = sorted({str(node.get("op")) for node in nodes if isinstance(node, dict)})
    threads = sorted(
        {
            str(node["thread"])
            for node in nodes
            if isinstance(node, dict) and isinstance(node.get("thread"), str)
        }
    )
    params = sorted(str(name) for name in ((recipe or {}).get("params") or {}))
    return {"ops": ops, "threads": threads, "params": params}


def _holes(shape: Any) -> list[dict[str, Any]]:
    """구멍을 지름으로 묶어 — 개수(`n`)와 그중 관통(`through`). 솔리드마다 따로 본다(관통은 그
    솔리드 기준)."""
    from app.core.drawing import holes

    counts: dict[float, list[int]] = {}
    for solid in shape.solids() or [shape]:
        for one in holes(solid):
            row = counts.setdefault(round(float(one["diameter"]), 2), [0, 0])
            row[0] += 1
            row[1] += one["depth"] is None
    return [
        {"d": diameter, "n": count, "through": through}
        for diameter, (count, through) in sorted(counts.items())
    ]


def index(shape: Any, recipe: dict[str, Any] | None = None) -> dict[str, Any]:
    """형상 색인 한 벌 — JSON 그대로 DB 에 들어간다."""
    box = shape.bounding_box()
    size = [
        round(float(box.size.X), 3),
        round(float(box.size.Y), 3),
        round(float(box.size.Z), 3),
    ]
    found = _holes(shape)
    return {
        "version": VERSION,
        "size": size,
        "dims": sorted(size),
        "volume": round(float(shape.volume), 1),
        "area": round(float(shape.area), 1),
        "solids": len(shape.solids()),
        "holes": found,
        "hole_count": sum(one["n"] for one in found),
        **from_recipe(recipe),
    }


def safe_index(shape: Any, recipe: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """색인을 못 뽑아도 작업은 성공이다 — 찾기에서 빠질 뿐(나중에 채우기가 다시 본다)."""
    try:
        return index(shape, recipe)
    except Exception:
        return None


# --- 닮음 --------------------------------------------------------------------------

#: 닮음의 성분과 무게. 없는 성분(레시피가 없는 STEP 의 `ops` 등)은 빼고 남은 무게로 나눈다.
WEIGHTS: dict[str, float] = {
    "size": 0.30,
    "proportion": 0.15,
    "fill": 0.15,
    "holes": 0.25,
    "ops": 0.10,
    "solids": 0.05,
}
#: 크기 · 비율의 어긋남(로그 비)을 닮음으로 바꾸는 눈금 — 한 변이 10 % 다르면 0.94, 세 변이
#: 다 두 배면 0.25.
_LOG_SCALE = 0.5
#: 구멍 지름을 같다고 볼 틈(mm) — M6 틈새 구멍 6.4 · 6.6 · 6.8 은 같은 구멍이다.
_HOLE_TOLERANCE = 0.5


def _dims(shape: dict[str, Any]) -> list[float] | None:
    dims = shape.get("dims")
    if not isinstance(dims, list) or len(dims) != 3:
        return None
    # 얇은 판 · 곡면처럼 한 변이 0 에 가까우면 로그 비가 터진다 — 0.1 mm 를 바닥으로.
    return [max(float(one), 0.1) for one in dims]


def _fill(shape: dict[str, Any], dims: list[float]) -> float | None:
    """경계상자를 얼마나 채우나 — 판은 1 에 가깝고, ㄱ 자 브래킷은 0.2, 프레임은 0.05."""
    volume = shape.get("volume")
    if not isinstance(volume, int | float) or volume <= 0:
        return None
    return min(1.0, float(volume) / (dims[0] * dims[1] * dims[2]))


def _holes_alike(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> float:
    """구멍 짝 맞추기 — 지름이 틈 안이면 같은 구멍으로 보고 개수의 겹침 / 합(가중 자카드).
    둘 다 구멍이 없으면 1, 한쪽만 있으면 0."""
    left = sorted((float(one["d"]), int(one["n"])) for one in first or [])
    right = [[float(one["d"]), int(one["n"])] for one in second or []]
    total_left = sum(n for _, n in left)
    total_right = sum(n for _, n in right)
    if total_left == 0 and total_right == 0:
        return 1.0
    shared = 0
    for diameter, count in left:
        # 가장 가까운 지름부터 — 남은 개수만큼만 짝짓는다.
        for slot in sorted(right, key=lambda one: abs(one[0] - diameter)):
            if count == 0 or abs(slot[0] - diameter) > _HOLE_TOLERANCE:
                break
            taken = min(count, int(slot[1]))
            slot[1] -= taken
            count -= taken
            shared += taken
    union = total_left + total_right - shared
    return shared / union if union else 1.0


def similarity(
    first: dict[str, Any], second: dict[str, Any]
) -> tuple[float, dict[str, float]]:
    """두 형상 색인이 얼마나 닮았나(0 ~ 1)와 성분별 닮음. 성분:

    - `size` — 작은 것부터 늘어놓은 세 변의 로그 비(놓인 방향과 상관없이).
    - `proportion` — 가장 긴 변에 대한 두 변의 비. 크기가 달라도 모양 비율이 같으면 높다.
    - `fill` — 부피 / 경계상자. 판 · 브래킷 · 프레임을 가른다.
    - `holes` — 지름(± 0.5 mm)과 개수가 겹치는 정도.
    - `ops` — 쓴 연산의 자카드(둘 다 레시피가 있을 때만).
    - `solids` — 덩어리 수(단품 · 조립을 가른다)."""
    parts: dict[str, float] = {}
    left, right = _dims(first), _dims(second)
    if left and right:
        ratios = [abs(math.log(a / b)) for a, b in zip(left, right, strict=True)]
        parts["size"] = math.exp(-sum(ratios) / 3 / _LOG_SCALE)
        shape_left = (math.log(left[0] / left[2]), math.log(left[1] / left[2]))
        shape_right = (math.log(right[0] / right[2]), math.log(right[1] / right[2]))
        apart = sum(abs(a - b) for a, b in zip(shape_left, shape_right, strict=True)) / 2
        parts["proportion"] = math.exp(-apart / _LOG_SCALE)
        fill_left, fill_right = _fill(first, left), _fill(second, right)
        if fill_left is not None and fill_right is not None:
            parts["fill"] = max(0.0, 1 - abs(fill_left - fill_right) / 0.5)
    parts["holes"] = _holes_alike(first.get("holes") or [], second.get("holes") or [])
    ops_left, ops_right = set(first.get("ops") or []), set(second.get("ops") or [])
    if ops_left and ops_right:
        parts["ops"] = len(ops_left & ops_right) / len(ops_left | ops_right)
    solids_left, solids_right = first.get("solids"), second.get("solids")
    if (
        isinstance(solids_left, int)
        and isinstance(solids_right, int)
        and solids_left
        and solids_right
    ):
        parts["solids"] = min(solids_left, solids_right) / max(solids_left, solids_right)
    weight = sum(WEIGHTS[key] for key in parts)
    score = (
        sum(WEIGHTS[key] * value for key, value in parts.items()) / weight if weight else 0.0
    )
    return round(score, 4), {key: round(value, 3) for key, value in parts.items()}


def reasons(
    parts: dict[str, float], first: dict[str, Any], second: dict[str, Any]
) -> list[str]:
    """왜 닮았나 · 어디가 다른가 — 사람이 점수만 보고 고르지 않게 짧은 말로."""
    out: list[str] = []
    size = parts.get("size")
    proportion = parts.get("proportion")
    if size is not None and size >= 0.85:
        out.append("크기 비슷")
    elif proportion is not None and proportion >= 0.85:
        out.append("모양 비율 같음(크기는 다름)")
    elif size is not None and size < 0.5:
        out.append("크기 많이 다름")
    holes = parts.get("holes")
    has_holes = bool(first.get("holes")) or bool(second.get("holes"))
    if has_holes and holes is not None:
        if holes >= 0.99:
            out.append("구멍 같음")
        elif holes >= 0.5:
            out.append("구멍 비슷")
        elif holes == 0:
            out.append("구멍 다름")
    fill = parts.get("fill")
    if fill is not None and fill >= 0.9 and (size is None or size < 0.85):
        out.append("꽉 찬 정도 비슷")
    ops = parts.get("ops")
    if ops is not None and ops >= 0.75:
        out.append("만든 방식 비슷")
    solids = parts.get("solids")
    if solids is not None and solids < 1:
        out.append("덩어리 수 다름")
    return out
