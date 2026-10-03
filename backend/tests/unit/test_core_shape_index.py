"""형상 색인 — 만든 김에 한 번 뽑아 두는 값(`core/shape_index.py`)."""

from __future__ import annotations

from app.core import shape_index
from app.core.recipe import evaluate, parse

PLATE = {
    "params": {"두께": 8.0},
    "nodes": [
        {"id": "p", "op": "box", "length": 120, "width": 40, "height": "=두께"},
        {
            "id": "h",
            "op": "hole",
            "target": "p",
            "thread": "M6",
            "kind": "counterbore",
            "at": [[-40, 0], [40, 0]],
        },
        {"id": "b", "op": "hole", "target": "h", "diameter": 5, "depth": 4, "at": [[0, 10]]},
        {
            "id": "f",
            "op": "fillet",
            "target": "b",
            "radius": 2,
            "edges": {"near": [[60, 20, 0]]},
        },
    ],
}


def test_크기_구멍_레시피를_한_벌로() -> None:
    made = evaluate(parse(PLATE))
    got = shape_index.index(made.shape, PLATE)
    assert got["size"] == [120.0, 40.0, 8.0]
    assert got["dims"] == [8.0, 40.0, 120.0]  # 놓인 방향과 상관없이 작은 변부터
    assert got["solids"] == 1
    # M6 카운터보어 둘 = Ø6.6 관통 둘 + 자리파기 Ø11 둘, 그리고 막힌 Ø5 하나.
    holes = {one["d"]: one for one in got["holes"]}
    assert holes[6.6] == {"d": 6.6, "n": 2, "through": 2}
    assert holes[11.0]["n"] == 2 and holes[11.0]["through"] == 0
    assert holes[5.0] == {"d": 5.0, "n": 1, "through": 0}
    assert got["hole_count"] == 5
    assert got["ops"] == ["box", "fillet", "hole"]
    assert got["threads"] == ["M6"]
    assert got["params"] == ["두께"]


def test_레시피가_없으면_형상만() -> None:
    made = evaluate(parse(PLATE))
    got = shape_index.index(made.shape)
    assert got["ops"] == [] and got["threads"] == [] and got["params"] == []
    assert got["volume"] > 0
