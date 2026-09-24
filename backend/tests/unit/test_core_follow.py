"""좌표가 든 선택 규칙이 **치수를 따라간다** — DOE 설계점마다 `near` 를 옮긴다
(core/recipe/follow.py).

「이 자리의 면」 은 그 좌표에 가장 가까운 면이라, 치수가 바뀌면 못 찾는 게 아니라 **딴 면을
말없이 집는다.** 변수마다 그 면이 움직이는 양을 한 번 재 두고 설계점마다 그만큼 옮기면 같은
면을 집는다 — 1차로 걸리는 치수면 정확하다.
"""

from __future__ import annotations

from typing import Any

from build123d import Shape

from app.core.recipe import evaluate, parse
from app.core.recipe.follow import drift, follow, measure, tolerance_for
from app.core.recipe.params import resolve_params
from app.core.recipe.topology import regions

#: 길이 · 두께 · 구멍 자리가 모두 변수인 판 — 구멍 넷은 가운데에서 ±구멍x, ±15.
PLATE: dict[str, Any] = {
    "params": {"길이": 80.0, "두께": 10.0, "구멍x": 30.0},
    "nodes": [
        {
            "id": "b",
            "op": "box",
            "length": "=길이",
            "width": 50,
            "height": "=두께",
            "align": ["center", "center", "min"],
        },
        {
            "id": "h",
            "op": "hole",
            "target": "b",
            "at": [["=-구멍x", -15], ["=구멍x", -15], ["=-구멍x", 15], ["=구멍x", 15]],
            "diameter": 8.5,
        },
    ],
}
FACTORS = ["길이", "두께", "구멍x"]
BASE = resolve_params(PLATE)


def _build(overrides: dict[str, float]) -> tuple[Shape, dict[str, list[int]] | None]:
    made = evaluate(parse({**PLATE, "params": {**PLATE["params"], **overrides}}))
    return made.shape, made.tags


#: 기준 형상(길이 80)에서 고른 둘 — +X 옆면(좌표만)과 왼쪽 아래 구멍(축으로 거름).
DEFINITIONS = [
    {"name": "옆면", "select": {"what": "faces", "near": [40, 0, 5], "limit": 1}},
    {
        "name": "구멍",
        "select": {
            "what": "faces",
            "kind": "cylinder",
            "axis": [0, 0, 1],
            "near": [-25.75, -15, 5],
            "limit": 1,
        },
    },
]


def test_변수마다_움직이는_양을_재고_설계점에서_같은_면을_집는다() -> None:
    tracks = measure(DEFINITIONS, BASE, FACTORS, _build)
    point = {"길이": 200.0, "두께": 30.0, "구멍x": 60.0}
    shape, tags = _build(point)

    # 따라가지 않으면 — 옆면 자리에 구멍 원통면이 더 가깝다(말없이 딴 면).
    plain, _ = regions(shape, DEFINITIONS, tags)
    assert "radius" in plain["옆면"][0], "좌표 그대로면 구멍을 집는다 — 이것을 막으려는 것"

    moved = follow(DEFINITIONS, tracks, BASE, point)
    found, unresolved = regions(shape, moved, tags)
    assert unresolved == []
    assert found["옆면"][0]["normal"] == [1.0, 0.0, 0.0]
    assert found["옆면"][0]["centroid"][0] == 100.0  # 길이/2
    # 구멍도 제 자리(-구멍x)로 따라간다 — 원통면의 지문은 축 위의 점이다.
    assert found["구멍"][0]["centroid"][:2] == [-60.0, -15.0]
    # 1차로 걸리는 치수라 예측이 정확하다 — 멀리 떨어진 것을 집지 않았다.
    assert drift(moved, tracks, shape, tags, tolerance_for(shape)) == {}


def test_기준_그대로의_설계점은_아무것도_옮기지_않는다() -> None:
    tracks = measure(DEFINITIONS, BASE, FACTORS, _build)
    moved = follow(DEFINITIONS, tracks, BASE, {"길이": 80.0, "두께": 10.0, "구멍x": 30.0})
    shape, tags = _build({})
    assert regions(shape, moved, tags) == regions(shape, DEFINITIONS, tags)


def test_면이_없어지면_딴_것을_집지_않고_알린다() -> None:
    """구멍x 45 면 구멍(지름 8.5)이 판(±40) 밖으로 나가 없어진다 — 따라갈 면이 없다.

    종류로 거른 규칙은 원통면이 하나도 없어 「못 풀었다」 가 되고, 좌표만 쓰는 규칙은 예측한
    자리에서 먼 딴 면(-X 옆면)을 집으므로 `drift` 가 그 거리를 알린다 — 부르는 쪽이 그 이름을
    「못 풀었다」 로 돌린다.
    """
    only_near = [
        {
            "name": "구멍(좌표만)",
            "select": {"what": "faces", "near": [-25.75, -15, 5], "limit": 1},
        }
    ]
    definitions = [*DEFINITIONS, *only_near]
    tracks = measure(definitions, BASE, FACTORS, _build)
    point = {"구멍x": 45.0}
    shape, tags = _build(point)
    moved = follow(definitions, tracks, BASE, point)

    _, unresolved = regions(shape, moved, tags)
    assert unresolved == ["구멍"]
    assert set(drift(moved, tracks, shape, tags, tolerance_for(shape))) == {"구멍(좌표만)"}


def test_좌표_규칙이_없으면_형상을_만들지도_않는다() -> None:
    calls: list[dict[str, float]] = []

    def build(overrides: dict[str, float]) -> tuple[Shape, dict[str, list[int]] | None]:
        calls.append(overrides)
        return _build(overrides)

    tracks = measure(
        [{"name": "윗면", "select": {"what": "faces", "role": "top"}}], BASE, FACTORS, build
    )
    assert tracks == {} and calls == []
