"""영역과 바디의 좌표 지문 — 해석이 STEP 에서 같은 자리를 다시 집을 수 있게."""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Box, Compound, Location, Shape

from app.core.recipe import RecipeError, evaluate, parse
from app.core.recipe.topology import bodies, document, regions, slug

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


DIVIDED: dict[str, Any] = {
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
            "id": "패치",
            "op": "divide_face",
            "target": "b",
            "on": {"role": "top"},
            "shape": "circle",
            "radius": 8,
            "at": [20, 10, 999],
            "tag": "하중영역",
        },
    ],
}


def _divided(두께: float = 10) -> Any:
    return evaluate(parse({**DIVIDED, "params": {"두께": 두께}}))


def test_면을_나눠도_형상은_그대로다() -> None:
    """**부피가 변하면 안 된다.** 불리언으로 흉내 내면 얇은 판이 생기거나 부피가 흔들린다."""
    plain = evaluate(parse({**DIVIDED, "nodes": DIVIDED["nodes"][:1]}))
    divided = _divided()
    assert len(divided.shape.faces()) == len(plain.shape.faces()) + 1
    assert abs(divided.shape.volume - plain.shape.volume) < 1e-6


def test_패치는_치수를_바꿔도_같은_자리에_남는다() -> None:
    """**2b 의 완료 기준이다.** 면 번호로 저장하면 두께를 바꾸는 순간 다른 면을 가리킨다."""
    for 두께 in (4, 10, 20):
        got = _divided(두께)
        faces = [got.shape.faces()[i] for i in got.tags["하중영역"]]
        assert len(faces) == 1, f"두께 {두께}"
        # π·8² = 201.06 — 패치만 잡혔다(나머지 윗면은 안 잡힌다).
        assert abs(faces[0].area - 201.06) < 0.1, f"두께 {두께}"
        assert abs(faces[0].center().Z - 두께) < 1e-6, f"두께 {두께}"


def test_태그로_영역을_내보낸다() -> None:
    got = _divided()
    doc = document(
        got.shape,
        [{"name": "하중영역", "select": {"what": "faces", "tag": "하중영역"}}],
        tags=got.tags,
    )
    assert doc["unresolved"] == []
    area = doc["regions"]["하중영역"][0]
    assert abs(area["area"] - 201.06) < 0.1
    assert area["centroid"][:2] == [20.0, 10.0]

    # **태그를 안 넘기면 못 찾는다** — 번호는 이 평가 안에서만 뜻이 있다는 뜻이다.
    blind = document(
        got.shape, [{"name": "하중영역", "select": {"what": "faces", "tag": "하중영역"}}]
    )
    assert blind["unresolved"] == ["하중영역"]


def test_여럿을_묶은_선택_그룹도_영역으로_풀린다() -> None:
    """화면에서 면을 여럿 골라 만든 그룹(`{"any": [...]}`)이 내보낼 때 **각 면의 지문**으로
    나간다 — 받는 쪽은 규칙을 몰라도 면을 짝짓는다."""
    found, unresolved = regions(
        _shape(),
        [
            {
                "name": "바닥과 구멍",
                "select": {
                    "any": [
                        {"what": "faces", "role": "bottom"},
                        {"what": "faces", "near": [-30, -15, 5], "limit": 1},
                    ]
                },
            }
        ],
    )
    assert unresolved == []
    assert len(found["바닥과 구멍"]) == 2
    # 하나는 바닥(법선 -Z), 하나는 구멍(반지름이 있다) — 면 지문으로 나간다.
    assert any(one.get("normal") == [0.0, 0.0, -1.0] for one in found["바닥과 구멍"])
    assert any(abs(one.get("radius", 0) - 4.25) < 0.01 for one in found["바닥과 구멍"])


def test_점_선택_그룹의_지문은_그_자리다() -> None:
    """엣지 지문(midpoint · length)으로 보내면 점 행에는 그 칸이 없어 KeyError 가 났다
    (SimEngBay 가 짚었다, 2026-09-28)."""
    made = evaluate(
        parse({"nodes": [{"id": "b", "op": "box", "length": 10, "width": 10, "height": 5}]})
    )
    found, unresolved = regions(
        made.shape,
        [{"name": "점", "select": {"what": "vertices", "near": [5, 5, 5], "limit": 1}}],
    )
    assert unresolved == [] and found["점"] == [{"point": [5.0, 5.0, 2.5]}]


def _sketch_patch(두께: float, shapes: list[dict[str, Any]], **extra: Any) -> Any:
    """판 윗면 위에 그린 스케치 모양대로 나눈다 — 스케치 평면이 두께를 따라 올라간다."""
    return evaluate(
        parse(
            {
                "params": {"두께": 두께},
                "nodes": [
                    {"id": "b", "op": "box", "length": 100, "width": 60, "height": "=두께",
                     "align": ["center", "center", "min"]},
                    {"id": "모양", "op": "sketch",
                     "plane": {"name": "XY", "origin": [0, 0, "=두께"]}, "shapes": shapes},
                    {"id": "나눔", "op": "divide_face", "target": "b", "shape": "sketch",
                     "sketch": "모양", "tag": "패드", **extra},
                ],
            }
        )
    )  # fmt: skip


#: ㄴ자 패드(30 x 10 + 10 x 20 = 500 mm²)와 고리(반지름 12 - 6 → π · 108 = 339.29 mm²).
L_AND_RING: list[dict[str, Any]] = [
    {"type": "polyline", "start": [-40, -20],
     "segments": [{"to": [-10, -20]}, {"to": [-10, -10]}, {"to": [-30, -10]},
                  {"to": [-30, 10]}, {"to": [-40, 10]}]},
    {"type": "circle", "radius": 12, "at": [25, 0]},
    {"type": "circle", "radius": 6, "at": [25, 0], "mode": "cut"},
]  # fmt: skip


@pytest.mark.parametrize("두께", [5.0, 12.0])
def test_스케치_모양대로_나누고_고리의_섬은_빠진다(두께: float) -> None:
    got = _sketch_patch(두께, L_AND_RING)
    faces = [got.shape.faces()[i] for i in got.tags["패드"]]
    assert sorted(round(one.area, 2) for one in faces) == [339.29, 500.0]
    assert all(abs(one.center().Z - 두께) < 1e-6 for one in faces)
    plain = 100 * 60 * 두께
    assert abs(got.shape.volume - plain) < 1e-6  # 형상은 그대로


def test_스케치가_면과_나란하지_않거나_떠_있으면_말한다() -> None:
    import re

    tilted = {"type": "rect", "width": 10, "height": 4}
    with pytest.raises(RecipeError, match=re.escape("스케치가 놓인 면이 없습니다")):
        evaluate(
            parse(
                {
                    "nodes": [
                        {"id": "b", "op": "box", "length": 100, "width": 60, "height": 10},
                        {"id": "모양", "op": "sketch",
                         "plane": {"name": "XY", "origin": [0, 0, 3]}, "shapes": [tilted]},
                        {"id": "나눔", "op": "divide_face", "target": "b", "shape": "sketch",
                         "sketch": "모양", "tag": "패드"},
                    ]
                }
            )
        )  # fmt: skip
    # 윗면을 골랐는데 스케치는 옆(XZ)에 그렸다.
    upright = {
        "nodes": [
            {"id": "b", "op": "box", "length": 100, "width": 60, "height": 10},
            {"id": "모양", "op": "sketch", "plane": {"name": "XZ"}, "shapes": [tilted]},
            {"id": "나눔", "op": "divide_face", "target": "b", "on": {"role": "top"},
             "shape": "sketch", "sketch": "모양", "tag": "패드"},
        ]
    }  # fmt: skip
    with pytest.raises(RecipeError, match="평행해야"):
        evaluate(parse(upright))


def test_겹쳐_놓은_바디의_패치는_같은_평면의_면만_잡는다() -> None:
    """위판 윗면의 패치(z 10)와 그 바로 아래 아래판 윗면에 새긴 자리(z 5)는 법선이 같고
    경계상자도 겹친다 — 평면이 다르면 그 패치가 아니다. 전단 이음 픽스처를 만들다 잡았다
    (2026-10-03): 클램프 압력이 이음 속 면에도 걸릴 뻔했다."""
    made = evaluate(
        parse(
            {
                "nodes": [
                    {"id": "아래판", "op": "box", "length": 100, "width": 25, "height": 5,
                     "align": ["min", "center", "min"]},
                    {"id": "위판_원형", "op": "box", "length": 100, "width": 25, "height": 5,
                     "at": [60, 0, 5], "align": ["min", "center", "min"]},
                    {"id": "위판", "op": "divide_face", "target": "위판_원형",
                     "on": {"normal": [0, 0, 1]}, "shape": "rect", "size": [40, 20],
                     "at": [80, 0, 10], "tag": "클램프"},
                    {"id": "조립", "op": "group", "targets": ["아래판", "위판"]},
                    {"id": "새김", "op": "imprint", "target": "조립"},
                ]
            }
        )
    )  # fmt: skip
    faces = made.shape.faces()
    clamp = [
        (round(faces[i].area, 1), round(faces[i].center().Z, 3)) for i in made.tags["클램프"]
    ]
    assert clamp == [(800.0, 10.0)]
    assert [round(faces[i].center().Z, 3) for i in made.tags["아래판/위판"]] == [5.0]
    # 조립의 지문에는 바디 이름이 붙는다 — 같은 자리의 점을 바디로 가른다.
    found, unresolved = regions(
        made.shape,
        [
            {"name": "위", "select": {"what": "vertices", "near": [60, 12.5, 5], "limit": 1,
                                      "of_face": {"body": "위판", "normal": [0, 0, -1]}}},
            {"name": "아래", "select": {"what": "vertices", "near": [60, 12.5, 5], "limit": 1,
                                        "of_face": {"body": "아래판", "normal": [0, 0, 1]}}},
            {"name": "클램프면", "select": {"what": "faces", "tag": "클램프"}},
        ],
        made.tags,
    )  # fmt: skip
    assert unresolved == []
    assert found["위"] == [{"point": [60.0, 12.5, 5.0], "body": "위판"}]
    assert found["아래"] == [{"point": [60.0, 12.5, 5.0], "body": "아래판"}]
    assert found["클램프면"][0]["body"] == "위판" and found["클램프면"][0]["area"] == 800.0
