"""치수표 — AI 가 형상을 「읽는」 길. 사람의 측정 창에 해당한다."""

from __future__ import annotations

from app.core.recipe import evaluate, parse
from app.core.recipe.digest import digest

PLATE = {
    "params": {"L": 80},
    "nodes": [
        {
            "id": "b",
            "op": "box",
            "length": "=L",
            "width": 50,
            "height": 10,
            "align": ["min", "center", "min"],
        },
        {"id": "h", "op": "hole", "target": "b", "at": [[15, 0], [65, 0]], "diameter": 6},
        {
            "id": "p",
            "op": "cylinder",
            "radius": 4,
            "height": 20,
            "at": [40, 0, 10],
            "align": ["center", "center", "min"],
        },
        {"id": "u", "op": "union", "targets": ["h", "p"]},
    ],
}


def test_구멍을_지름과_자리와_깊이로_말한다() -> None:
    got = digest(evaluate(parse(PLATE)).shape)
    assert got["bbox"]["size"] == [80.0, 50.0, 30.0]
    holes = {(h["diameter"], tuple(h["at"][:2])): h for h in got["holes"]}
    # ⌀6 구멍 둘 — 판 두께만큼 뚫렸다. 나란한 두 구멍이 한 구멍으로 묶이면 안 된다.
    assert (6.0, (15.0, 0.0)) in holes and (6.0, (65.0, 0.0)) in holes
    assert holes[(6.0, (15.0, 0.0))]["depth"] == 10.0
    assert holes[(6.0, (15.0, 0.0))]["axis"] == [0.0, 0.0, 1.0]
    # 핀은 ⌀8 · 높이 20 으로 잡힌다(원 둘이 같은 축에 있다).
    assert (8.0, (40.0, 0.0)) in holes
    assert holes[(8.0, (40.0, 0.0))]["depth"] == 20.0


def test_면을_법선과_넓이로_말한다() -> None:
    got = digest(evaluate(parse(PLATE)).shape)
    planes = got["faces"]["planes"]
    assert planes[0]["area"] >= planes[-1]["area"]  # 큰 것부터
    bottom = next(one for one in planes if one["normal"] == [0.0, 0.0, -1.0])
    assert bottom["center"][2] == 0.0  # align min 이라 바닥이 z=0
    assert got["faces"]["curved"][0]["radius"] == 4.0  # 핀 옆면
    assert "*_total" in got["note"] or "전체는" in got["note"]
