"""영역과 바디의 좌표 지문 — 해석이 STEP 에서 같은 자리를 다시 집을 수 있게."""

from __future__ import annotations

from typing import Any

from build123d import Box, Compound, Location, Shape

from app.core.recipe import evaluate, parse
from app.core.recipe.topology import bodies, document, slug

#: 볼트 고정 지그의 모양 — 판 + 수직 관통 구멍 넷. 두께는 변수다(설계점마다 바뀐다).
PLATE: dict[str, Any] = {
    "params": {"두께": 10},
    "nodes": [
        {
            "id": "b",
            "op": "box",
            "length": 80,
            "width": 50,
            "height": "=두께",
            "align": ["center", "center", "min"],
        },
        {
            "id": "h",
            "op": "hole",
            "target": "b",
            "at": [[-30, -15], [30, -15], [-30, 15], [30, 15]],
            "diameter": 8.5,
        },
    ],
}


def _shape(params: dict[str, float] | None = None) -> Shape:
    recipe = {**PLATE, "params": {**PLATE["params"], **(params or {})}}
    return evaluate(parse(recipe)).shape


def test_영역은_이름으로_나오고_바닥과_구멍을_안다() -> None:
    """바닥 고정 모달 한 줄기에 필요한 것 — 고정할 면과 볼트 구멍."""
    doc = document(_shape())

    assert doc["units"] == "mm"
    assert doc["unresolved"] == []
    assert set(doc["regions"]) == {"fixed_base", "bolt_holes"}

    바닥 = doc["regions"]["fixed_base"]
    assert len(바닥) == 1
    assert 바닥[0]["centroid"][2] == 0.0  # 판이 z=0 에 앉아 있다
    assert 바닥[0]["normal"] == [0.0, 0.0, -1.0]
    # 넓이는 판 넓이(80x50=4000)에서 구멍 넷(4 x pi x 4.25^2 = 227)을 뺀 값이다
    # — 「면을 집었다」 는 증거.
    assert abs(바닥[0]["area"] - 3773.0) < 1.0

    구멍 = doc["regions"]["bolt_holes"]
    assert len(구멍) == 4
    assert all(abs(one["radius"] - 4.25) < 0.01 for one in 구멍)
    assert all(one["axis"] == [0.0, 0.0, 1.0] for one in 구멍)
    # **구멍의 중심은 축 위에 있어야 한다.** `face.center()` 는 표면 위의 점을 주고(실측),
    # 그것으로 적어 보내면 해석 쪽이 내는 축 위의 점과 반지름만큼 어긋나 짝이 안 맞는다.
    assert sorted(tuple(one["centroid"]) for one in 구멍) == [
        (-30.0, -15.0, 5.0),
        (-30.0, 15.0, 5.0),
        (30.0, -15.0, 5.0),
        (30.0, 15.0, 5.0),
    ]


def test_치수를_훑어도_같은_개수로_풀린다() -> None:
    """**이것이 이 모듈의 존재 이유다.** DOE 는 치수를 바꿔 형상을 여러 벌 만드는데,
    면 번호로 적어 두면 두께를 바꾸는 순간 다른 면을 가리킨다."""
    for 두께 in (3, 6, 10, 14, 20):
        doc = document(_shape({"두께": 두께}))
        assert doc["unresolved"] == [], f"두께 {두께} 에서 못 푼 영역: {doc['unresolved']}"
        assert len(doc["regions"]["bolt_holes"]) == 4, f"두께 {두께}"
        바닥 = doc["regions"]["fixed_base"]
        assert len(바닥) == 1 and 바닥[0]["centroid"][2] == 0.0, f"두께 {두께}"
        # 바디의 부피는 두께를 따라간다 — 지문이 형상을 실제로 재고 있다는 뜻.
        assert doc["bodies"][0]["volume"] > 0


def test_한글_이름표는_JSON_이_들고_STEP_은_아스키로() -> None:
    """STEP 은 한글 PRODUCT 이름을 못 나른다(실측). 뜻은 JSON 의 `name` 이 들고,
    STEP 에는 손잡이만 나간다."""
    부품 = Box(40, 30, 6)
    부품.label = "부품"
    지그 = Box(60, 50, 10)
    지그.label = "지그판"
    지그.locate(Location((0, 0, -8)))
    조립 = Compound(children=[부품, 지그])

    rows = bodies(조립)
    assert [r["name"] for r in rows] == ["부품", "지그판"]
    products = [r["step_product"] for r in rows]
    assert products == ["body_1", "body_2"]  # 아스키가 남지 않으면 순번이 손잡이다
    assert len(set(products)) == len(products)  # 겹치면 짝짓기가 무너진다
    assert all(p.isascii() for p in products)

    # 부피 · 무게중심이 실제 형상과 맞는다 — 받는 쪽은 이것으로 바디를 짝짓는다.
    부품_행 = rows[0]
    assert 부품_행["volume"] == 40 * 30 * 6
    assert 부품_행["centroid"] == [0.0, 0.0, 0.0]
    assert 부품_행["bbox"] == [[-20.0, -15.0, -3.0], [20.0, 15.0, 3.0]]


def test_이름표가_없으면_통째로_한_바디() -> None:
    rows = bodies(_shape())
    assert len(rows) == 1
    assert rows[0]["name"] == "전체" and rows[0]["step_product"] == "body_1"


def test_아스키_이름은_그대로_손잡이가_된다() -> None:
    assert slug("Jig Plate", fallback="body_1") == "jig_plate"
    assert slug("부품", fallback="body_7") == "body_7"
    assert slug("볼트-M8", fallback="body_2") == "m8"


def test_못_푼_영역은_조용히_빠지지_않는다() -> None:
    """0개를 집고 넘어가면 **하중 없는 해석**이 끝까지 돈다 — 이름을 남겨야 한다."""
    doc = document(
        _shape(),
        [
            {"name": "있는것", "select": {"what": "faces", "role": "bottom"}},
            {"name": "없는것", "select": {"what": "faces", "kind": "cylinder", "radius": 99}},
        ],
    )
    assert doc["unresolved"] == ["없는것"]
    assert "없는것" not in doc["regions"]
