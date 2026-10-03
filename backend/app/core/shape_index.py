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
