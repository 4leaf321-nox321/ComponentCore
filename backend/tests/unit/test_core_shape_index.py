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


def _index(
    dims: list[float], volume: float, holes: list[dict[str, float]], **extra: object
) -> dict[str, object]:
    return {"dims": dims, "volume": volume, "holes": holes, "solids": 1, **extra}


def test_닮음은_자기_자신이_1_이고_구멍_지름은_틈_안이면_같다() -> None:
    plate = _index(
        [10, 60, 100], 60000, [{"d": 6.6, "n": 4, "through": 4}], ops=["box", "hole"]
    )
    assert shape_index.similarity(plate, plate) == (1.0, {k: 1.0 for k in shape_index.WEIGHTS})
    # M6 틈새 구멍 6.4 · 6.6 은 같은 구멍, 5.5(M5)는 다른 구멍.
    close = {**plate, "holes": [{"d": 6.4, "n": 4, "through": 4}]}
    far = {**plate, "holes": [{"d": 5.5, "n": 4, "through": 4}]}
    assert shape_index.similarity(plate, close)[1]["holes"] == 1.0
    assert shape_index.similarity(plate, far)[1]["holes"] == 0.0
    # 넷 중 둘만 같으면 겹침 2 / 합 4.
    half = {**plate, "holes": [{"d": 6.6, "n": 2, "through": 2}]}
    assert shape_index.similarity(plate, half)[1]["holes"] == 0.5


def test_레시피가_없으면_연산은_빼고_남은_무게로() -> None:
    plate = _index([10, 60, 100], 60000, [], ops=["box"])
    step = _index([10, 60, 100], 60000, [])  # 가져온 STEP — 연산을 모른다
    score, parts = shape_index.similarity(plate, step)
    assert "ops" not in parts and score == 1.0
    assert shape_index.reasons(parts, plate, step) == ["크기 유사"]
    # 두 배 큰 같은 모양 — 크기는 멀고 비율은 같다.
    big = _index([20, 120, 200], 480000, [])
    score, parts = shape_index.similarity(plate, big)
    assert parts["proportion"] == 1.0 and parts["size"] < 0.3
    assert "형상 비율 동일(크기 다름)" in shape_index.reasons(parts, plate, big)
