"""레시피 — 모양(schema) · 평가 · 템플릿을 서버 없이 본다."""

from __future__ import annotations

from typing import Any

import pytest

from app.core import primitives
from app.core.recipe import RecipeError, evaluate, parse, templates
from app.core.recipe.schema import RecipeValidationError


def _box(**extra: object) -> dict[str, object]:
    return {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 20, "height": 10}],
            },
            {"id": "b", "op": "extrude", "sketch": "s", "distance": 5},
            *extra.get("more", []),  # type: ignore[misc]
        ]
    }


SPECS = {
    "box": {"kind": "box", "length": 80, "width": 50, "height": 20},
    "cylinder": {"kind": "cylinder", "radius": 25, "height": 40},
    "plate_with_holes": {
        "kind": "plate_with_holes",
        "length": 100,
        "width": 60,
        "thickness": 12,
    },
    "bracket": {"kind": "bracket", "length": 80, "width": 50, "height": 40, "thickness": 8},
}


def test_템플릿은_원시_도형과_같은_부피() -> None:
    for name, make in templates.TEMPLATES.items():
        evaluation = evaluate(parse(make()))
        reference = primitives.build(SPECS[name])
        assert evaluation.shape.volume == pytest.approx(reference.volume, rel=0.02), name


def test_상자_하나() -> None:
    evaluation = evaluate(parse(_box()))
    assert evaluation.shape.volume == pytest.approx(20 * 10 * 5)
    summary = evaluation.summary()
    assert summary["bbox"]["size"] == (20.0, 10.0, 5.0)
    assert [one["id"] for one in summary["nodes"]] == ["s", "b"]
    assert summary["nodes"][0]["kind"] == "sketch"


def test_앞에_없는_노드를_가리키면_거절() -> None:
    with pytest.raises(RecipeValidationError) as caught:
        parse({"nodes": [{"id": "b", "op": "extrude", "sketch": "s", "distance": 5}]})
    assert "앞에 없는 피처" in caught.value.problems[0]


def test_id_가_겹치면_거절() -> None:
    with pytest.raises(RecipeValidationError) as caught:
        parse(
            {
                "nodes": [
                    {"id": "s", "op": "sketch", "shapes": [{"type": "circle", "radius": 1}]},
                    {"id": "s", "op": "sketch", "shapes": [{"type": "circle", "radius": 2}]},
                ]
            }
        )
    assert "겹칩니다" in caught.value.problems[0]


def test_틀린_칸은_어느_칸인지_말한다() -> None:
    with pytest.raises(RecipeValidationError) as caught:
        parse(
            {
                "nodes": [
                    {"id": "s", "op": "sketch", "shapes": [{"type": "circle", "radius": 0}]}
                ]
            }
        )
    assert caught.value.problems[0].startswith("nodes.0.sketch.shapes.0.circle.radius")


def test_결과가_스케치면_평가에서_거절() -> None:
    with pytest.raises(RecipeError) as caught:
        evaluate(
            parse(
                {
                    "nodes": [
                        {
                            "id": "s",
                            "op": "sketch",
                            "shapes": [{"type": "circle", "radius": 3}],
                        }
                    ]
                }
            )
        )
    assert caught.value.node_id == "s"


def test_너무_큰_필렛은_노드와_함께_실패() -> None:
    recipe = _box(
        more=[{"id": "f", "op": "fillet", "target": "b", "edges": "vertical", "radius": 50}]
    )
    with pytest.raises(RecipeError) as caught:
        evaluate(parse(recipe))
    assert caught.value.node_id == "f"
    assert "반지름" in caught.value.message


def test_구멍_컷_패턴_회전() -> None:
    recipe = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 100, "height": 60}],
            },
            {"id": "plate", "op": "extrude", "sketch": "s", "distance": 10},
            {"id": "peg", "op": "cylinder", "radius": 3, "height": 30, "at": [-30, 0, 0]},
            {
                "id": "pegs",
                "op": "pattern",
                "source": "peg",
                "count": 4,
                "spacing": [20, 0, 0],
            },
            {"id": "cut", "op": "cut", "target": "plate", "tools": ["pegs"]},
            {
                "id": "h",
                "op": "hole",
                "target": "cut",
                "at": [[-40, 0]],
                "diameter": 6,
                "depth": 4,
            },
            {"id": "t", "op": "transform", "target": "h", "rotate": [0, 0, 90]},
        ]
    }
    evaluation = evaluate(parse(recipe))
    size = evaluation.summary()["bbox"]["size"]
    assert size[0] == pytest.approx(60) and size[1] == pytest.approx(100)  # 90° 돌았다
    assert evaluation.shape.volume < 100 * 60 * 10
    assert len(evaluation.shape.faces()) == 6 + 4 + 2  # 4 관통 + 막힌 구멍(옆 · 바닥)


def test_회전체와_거울() -> None:
    recipe = {
        "nodes": [
            {
                "id": "p",
                "op": "sketch",
                "plane": {"name": "XZ"},
                "shapes": [{"type": "rect", "width": 10, "height": 30, "at": [20, 0]}],
            },
            {"id": "ring", "op": "revolve", "sketch": "p", "axis": "Z", "angle": 180},
            {"id": "full", "op": "mirror", "target": "ring", "plane": "XZ"},
        ]
    }
    half = evaluate(parse({"nodes": recipe["nodes"][:2]})).shape.volume
    full = evaluate(parse(recipe)).shape.volume
    assert full == pytest.approx(half * 2, rel=0.01)


def test_옛_도형_스펙을_레시피로() -> None:
    recipe = templates.from_primitive_spec(
        {"kind": "box", "length": 30, "width": 20, "height": 10}
    )
    assert evaluate(parse(recipe)).shape.volume == pytest.approx(6000)
    with pytest.raises(ValueError):
        templates.from_primitive_spec({"kind": "sphere"})


def test_면_위_평면과_위치로_고른_엣지() -> None:
    from app.core.recipe.mesh import mesh

    base = evaluate(parse(_box()))
    top = next(f for f in mesh(base.shape)["faces"] if f["normal"][2] > 0.9)
    # 윗면 중심 · 법선으로 평면을 만들어 그 위에 원기둥을 세운다.
    recipe = _box(
        more=[
            {
                "id": "s2",
                "op": "sketch",
                "plane": {"origin": top["center"], "normal": top["normal"]},
                "shapes": [{"type": "circle", "radius": 2}],
            },
            {"id": "boss", "op": "extrude", "sketch": "s2", "distance": 4},
            {"id": "u", "op": "union", "targets": ["b", "boss"]},
        ]
    )
    grown = evaluate(parse(recipe))
    top_z = grown.shape.bounding_box().max.Z
    assert top_z == pytest.approx(9.0)

    # 수직 엣지 하나를 중점으로 골라 필렛.
    vertical = [e for e in mesh(base.shape)["edges"] if e["vertical"]]
    assert len(vertical) == 4
    picked = _box(
        more=[
            {
                "id": "f",
                "op": "fillet",
                "target": "b",
                "edges": {"near": [vertical[0]["midpoint"]]},
                "radius": 2,
            }
        ]
    )
    filleted = evaluate(parse(picked))
    assert filleted.shape.volume < base.shape.volume
    assert len(filleted.shape.faces()) == 7  # 면 하나(필렛)만 는다

    # 그 자리에 엣지가 없으면 노드가 말한다.
    gone = _box(
        more=[
            {
                "id": "f",
                "op": "fillet",
                "target": "b",
                "edges": {"near": [[99, 99, 99]]},
                "radius": 1,
            }
        ]
    )
    with pytest.raises(RecipeError) as caught:
        evaluate(parse(gone))
    assert "찾았습니다" in caught.value.message


def test_vertical_은_구멍_이음선을_빼고_고른다() -> None:
    """구멍이 있는 판에 `vertical` 필렛 — 원기둥면의 이음선을 함께 잡으면 OCC 가 터진다."""
    recipe = {
        "nodes": [
            {
                "id": "s",
                "op": "sketch",
                "shapes": [{"type": "rect", "width": 60, "height": 40}],
            },
            {"id": "b", "op": "extrude", "sketch": "s", "distance": 10},
            {"id": "h", "op": "hole", "target": "b", "at": [[-20, 0], [20, 0]], "diameter": 6},
            {"id": "f", "op": "fillet", "target": "h", "edges": "vertical", "radius": 5},
        ]
    }
    evaluation = evaluate(parse(recipe))
    assert len(evaluation.shape.faces()) == 6 + 2 + 4  # 구멍 둘 + 필렛 넷


BASE: list[dict[str, Any]] = [
    {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 60, "height": 40}]},
    {"id": "b", "op": "extrude", "sketch": "s", "distance": 20},
]


def _vol(nodes: list[dict[str, Any]]) -> float:
    return float(evaluate(parse({"nodes": nodes})).shape.volume)


def test_임의_윤곽_호_포함() -> None:
    shape = {
        "type": "polyline",
        "start": [0, 0],
        "segments": [{"to": [40, 0]}, {"to": [40, 20], "via": [50, 10]}, {"to": [0, 20]}],
    }
    ev = evaluate(
        parse(
            {
                "nodes": [
                    {"id": "s", "op": "sketch", "shapes": [shape]},
                    {"id": "b", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert ev.summary()["bbox"]["size"][0] == pytest.approx(50)  # 호가 오른쪽으로 10 나간다
    assert ev.shape.volume > 40 * 20 * 5


def test_규격_구멍_네_종류() -> None:
    plain = _vol(BASE)
    simple = _vol(
        [*BASE, {"id": "h", "op": "hole", "target": "b", "at": [[0, 0]], "thread": "M6"}]
    )
    cbore = _vol(
        [
            *BASE,
            {
                "id": "h",
                "op": "hole",
                "target": "b",
                "at": [[0, 0]],
                "kind": "counterbore",
                "thread": "M6",
            },
        ]
    )
    csink = _vol(
        [
            *BASE,
            {
                "id": "h",
                "op": "hole",
                "target": "b",
                "at": [[0, 0]],
                "kind": "countersink",
                "thread": "M6",
            },
        ]
    )
    tap = _vol(
        [
            *BASE,
            {
                "id": "h",
                "op": "hole",
                "target": "b",
                "at": [[0, 0]],
                "kind": "tap",
                "thread": "M6",
                "depth": 12,
            },
        ]
    )
    assert (
        plain > tap > simple > csink and plain > cbore < simple
    )  # 카운터는 더 파고, 탭은 덜 판다


def test_임의_면에서_뚫는_구멍() -> None:
    nodes = [
        *BASE,
        {
            "id": "h",
            "op": "hole",
            "target": "b",
            "at": [[0, 0]],
            "diameter": 8,
            "depth": 15,
            "plane": {"origin": [30, 0, 10], "normal": [1, 0, 0]},
        },
    ]
    ev = evaluate(parse({"nodes": nodes}))
    # +X 면에서 안쪽(-X)으로 15 — 구멍 원기둥면의 축이 X.
    from build123d import GeomType

    cyl = [f for f in ev.shape.faces() if f.geom_type == GeomType.CYLINDER]
    assert len(cyl) == 1 and abs(cyl[0].axis_of_rotation.direction.X) > 0.99


def test_쉘_열린_것과_닫힌_것() -> None:
    plain = _vol(BASE)
    opened = _vol(
        [*BASE, {"id": "sh", "op": "shell", "target": "b", "thickness": 2, "open": "top"}]
    )
    closed = _vol(
        [*BASE, {"id": "sh", "op": "shell", "target": "b", "thickness": 2, "open": "none"}]
    )
    assert opened < plain and closed < plain
    assert closed == pytest.approx(plain - 56 * 36 * 16, rel=0.01)  # 닫힌 껍질 = 전체 - 안쪽


def test_격자_패턴_로프트_기본_입체() -> None:
    grid = [
        *BASE,
        {"id": "peg", "op": "cylinder", "radius": 2, "height": 40, "at": [-20, -10, 0]},
        {
            "id": "pegs",
            "op": "pattern",
            "source": "peg",
            "kind": "grid",
            "count": 3,
            "count_y": 2,
            "spacing": [20, 0, 0],
            "spacing_y": [0, 20, 0],
        },
        {"id": "c", "op": "cut", "target": "b", "tools": ["pegs"]},
    ]
    ev = evaluate(parse({"nodes": grid}))
    assert len(ev.shape.faces()) == 6 + 6
    lofted = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "a",
                        "op": "sketch",
                        "shapes": [{"type": "rect", "width": 40, "height": 30}],
                    },
                    {
                        "id": "c",
                        "op": "sketch",
                        "plane": {"name": "XY", "origin": [0, 0, 30]},
                        "shapes": [{"type": "circle", "radius": 10}],
                    },
                    {"id": "l", "op": "loft", "sketches": ["a", "c"]},
                ]
            }
        )
    )
    assert lofted.summary()["bbox"]["size"][2] == pytest.approx(30)
    assert _vol([{"id": "s", "op": "sphere", "radius": 10}]) == pytest.approx(
        4 / 3 * 3.14159 * 1000, rel=0.01
    )
    assert _vol(
        [{"id": "s", "op": "cone", "bottom_radius": 10, "top_radius": 0, "height": 30}]
    ) == pytest.approx(3.14159 * 100 * 30 / 3, rel=0.01)
    assert _vol([{"id": "s", "op": "torus", "major_radius": 20, "minor_radius": 4}]) > 0


def test_구배_스윕_타원_글자() -> None:
    tapered = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [{"type": "rect", "width": 40, "height": 30}],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 20, "taper": 10},
                ]
            }
        )
    )
    assert tapered.shape.volume < 40 * 30 * 20  # 갈수록 좁아진다
    swept = evaluate(
        parse(
            {
                "nodes": [
                    {"id": "c", "op": "sketch", "shapes": [{"type": "circle", "radius": 3}]},
                    {
                        "id": "w",
                        "op": "sweep",
                        "sketch": "c",
                        "path": [[0, 0, 0], [0, 0, 30], [30, 0, 60]],
                    },
                ]
            }
        )
    )
    assert swept.summary()["solid_count"] == 1
    assert swept.shape.bounding_box().max.Z > 59
    engraved = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [{"type": "ellipse", "x_radius": 30, "y_radius": 20}],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 10},
                    {
                        "id": "t",
                        "op": "sketch",
                        "plane": {"origin": [0, 0, 10]},
                        "shapes": [{"type": "text", "text": "AJ", "size": 8}],
                    },
                    {
                        "id": "te",
                        "op": "extrude",
                        "sketch": "t",
                        "distance": 1,
                        "direction": "reverse",
                    },
                    {"id": "cut", "op": "cut", "target": "e", "tools": ["te"]},
                ]
            }
        )
    )
    assert engraved.shape.volume < 3.14159 * 30 * 20 * 10 - 1


def test_자르기_여유_배율() -> None:
    box = {"id": "b", "op": "box", "length": 20, "width": 20, "height": 20}
    half = evaluate(
        parse(
            {
                "nodes": [
                    box,
                    {
                        "id": "h",
                        "op": "split",
                        "target": "b",
                        "plane": {"name": "XY", "origin": [0, 0, 5]},
                        "keep": "top",
                    },
                ]
            }
        )
    )
    assert half.shape.volume == pytest.approx(20 * 20 * 5)
    with pytest.raises(RecipeError, match="지나야"):
        evaluate(
            parse(
                {
                    "nodes": [
                        box,
                        {
                            "id": "h",
                            "op": "split",
                            "target": "b",
                            "plane": {"name": "XY", "origin": [0, 0, 50]},
                        },
                    ]
                }
            )
        )
    grown = evaluate(
        parse({"nodes": [box, {"id": "o", "op": "offset", "target": "b", "amount": 2}]})
    )
    assert tuple(grown.summary()["bbox"]["size"]) == (24.0, 24.0, 24.0)
    with pytest.raises(RecipeError, match="얇은"):
        evaluate(
            parse({"nodes": [box, {"id": "o", "op": "offset", "target": "b", "amount": -11}]})
        )
    with pytest.raises(RecipeValidationError, match="0 이면"):
        parse({"nodes": [box, {"id": "o", "op": "offset", "target": "b", "amount": 0}]})
    scaled = evaluate(
        parse(
            {
                "nodes": [
                    box,
                    {"id": "t", "op": "transform", "target": "b", "scale": 0.5},
                ]
            }
        )
    )
    assert scaled.shape.volume == pytest.approx(1000)


def test_면까지_돌출_나선_단면_윤곽_여유() -> None:
    box = {"id": "b", "op": "box", "length": 40, "width": 30, "height": 20}
    peg = {
        "id": "p",
        "op": "sketch",
        "plane": {"origin": [0, 0, -30]},
        "shapes": [{"type": "circle", "radius": 3}],
    }
    to_next = evaluate(
        parse(
            {
                "nodes": [
                    box,
                    peg,
                    {
                        "id": "e",
                        "op": "extrude",
                        "sketch": "p",
                        "distance": 1,
                        "until": "next",
                        "target": "b",
                    },
                ]
            }
        )
    )
    assert pytest.approx(-10) == to_next.shape.bounding_box().max.Z  # 상자 바닥에서 멈춘다
    with pytest.raises(RecipeValidationError, match="대상 입체"):
        parse(
            {
                "nodes": [
                    box,
                    peg,
                    {
                        "id": "e",
                        "op": "extrude",
                        "sketch": "p",
                        "distance": 1,
                        "until": "next",
                    },
                ]
            }
        )
    spring = evaluate(
        parse(
            {
                "nodes": [
                    {"id": "s", "op": "sketch", "shapes": [{"type": "circle", "radius": 1.5}]},
                    {
                        "id": "h",
                        "op": "helix",
                        "sketch": "s",
                        "radius": 10,
                        "pitch": 5,
                        "height": 30,
                    },
                ]
            }
        )
    )
    assert spring.summary()["solid_count"] == 1
    assert pytest.approx(23, abs=0.1) == spring.shape.bounding_box().size.X
    pocket = evaluate(
        parse(
            {
                "nodes": [
                    box,
                    {
                        "id": "sec",
                        "op": "section",
                        "target": "b",
                        "plane": {"name": "XY", "origin": [0, 0, 5]},
                        "offset": 2,
                    },
                    {"id": "e", "op": "extrude", "sketch": "sec", "distance": 10},
                ]
            }
        )
    )
    assert tuple(pocket.summary()["bbox"]["size"]) == (44.0, 34.0, 10.0)
    outline = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [{"type": "rect", "width": 20, "height": 10}],
                        "offset": -2,
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert tuple(outline.summary()["bbox"]["size"]) == (16.0, 6.0, 5.0)


def test_두께_있는_선_리브와_가르기() -> None:
    rib = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "path",
                                "start": [0, 0],
                                "segments": [
                                    {"to": [30, 0]},
                                    {"to": [30, 20], "via": [36, 10]},
                                ],
                                "width": 4,
                            }
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert tuple(rib.summary()["bbox"]["size"]) == (40.0, 24.0, 5.0)  # 양 끝이 둥글어 폭/2 씩
    # 사각형을 대각선으로 가르면 면이 둘 — 스케치가 Compound 로 바뀌던 자리.
    halves = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {"type": "rect", "width": 40, "height": 30},
                            {
                                "type": "path",
                                "start": [-20, -15],
                                "segments": [{"to": [20, 15]}],
                                "width": 3,
                                "mode": "cut",
                            },
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert halves.summary()["solid_count"] == 2


def test_둥근_사각형_사다리꼴_볼록윤곽_쐐기_구배() -> None:
    rounded = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {"type": "rounded_rect", "width": 40, "height": 30, "radius": 5}
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert rounded.shape.volume < 40 * 30 * 5  # 모서리가 깎였다
    with pytest.raises(RecipeError, match="절반"):
        evaluate(
            parse(
                {
                    "nodes": [
                        {
                            "id": "s",
                            "op": "sketch",
                            "shapes": [
                                {
                                    "type": "rounded_rect",
                                    "width": 40,
                                    "height": 30,
                                    "radius": 20,
                                }
                            ],
                        },
                        {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                    ]
                }
            )
        )
    # 흩어진 원을 감싸는 볼록 윤곽 하나 — 베이스 판.
    plate = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "hull": True,
                        "shapes": [
                            {"type": "circle", "radius": 6, "at": [-30, 0]},
                            {"type": "circle", "radius": 6, "at": [30, 0]},
                            {"type": "circle", "radius": 6, "at": [0, 25]},
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 8},
                ]
            }
        )
    )
    assert plate.summary()["solid_count"] == 1
    assert plate.shape.volume > 3 * 3.14159 * 36 * 8  # 원 셋보다 넓다
    wedge = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "w",
                        "op": "wedge",
                        "length": 40,
                        "width": 30,
                        "height": 20,
                        "top_x_min": 10,
                        "top_x_max": 30,
                    }
                ]
            }
        )
    )
    assert wedge.shape.volume < 40 * 30 * 20
    drafted = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "b",
                        "op": "box",
                        "length": 40,
                        "width": 30,
                        "height": 20,
                        "at": [0, 0, 10],
                    },
                    {
                        "id": "d",
                        "op": "draft",
                        "target": "b",
                        "faces": "sides",
                        "angle": 5,
                        "neutral": {"name": "XY", "origin": [0, 0, 0]},
                    },
                ]
            }
        )
    )
    assert drafted.shape.volume < 40 * 30 * 20  # 위로 갈수록 좁아진다
    with pytest.raises(RecipeError, match="구배"):
        evaluate(
            parse(
                {
                    "nodes": [
                        {
                            "id": "b",
                            "op": "box",
                            "length": 40,
                            "width": 30,
                            "height": 20,
                            "at": [0, 0, 10],
                        },
                        {
                            "id": "d",
                            "op": "draft",
                            "target": "b",
                            "faces": "sides",
                            "angle": 44,
                        },
                    ]
                }
            )
        )


def test_모서리_둥근_윤곽() -> None:
    rounded = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "polyline",
                                "start": [0, 0],
                                "segments": [
                                    {"to": [40, 0]},
                                    {"to": [40, 25]},
                                    {"to": [0, 25]},
                                ],
                                "corner_radius": 6,
                            }
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert rounded.shape.volume < 40 * 25 * 5
    with pytest.raises(RecipeError, match="호"):
        evaluate(
            parse(
                {
                    "nodes": [
                        {
                            "id": "s",
                            "op": "sketch",
                            "shapes": [
                                {
                                    "type": "polyline",
                                    "start": [0, 0],
                                    "segments": [
                                        {"to": [40, 0]},
                                        {"to": [40, 25], "via": [46, 12]},
                                        {"to": [0, 25]},
                                    ],
                                    "corner_radius": 6,
                                }
                            ],
                        },
                        {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                    ]
                }
            )
        )


def test_말로_받은_치수_그대로_호_장공_삼각형() -> None:
    """AI 가 글로 받은 치수를 옮기는 칸들 — 좌표로 환산하지 않고 그대로 넣는다."""
    # 「R25 로 둥글게 이어라」 — 호 위의 점을 계산하지 않는다.
    by_radius = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "polyline",
                                "start": [0, 0],
                                "segments": [
                                    {"to": [40, 0]},
                                    {"to": [40, 30], "radius": 25},
                                    {"to": [0, 30]},
                                ],
                            }
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    # 반지름의 부호가 휘는 쪽을 정한다 — 왼쪽(안으로)이면 부피가 줄고 오른쪽이면 는다.
    assert by_radius.shape.volume < 40 * 30 * 5
    with pytest.raises(RecipeError, match="절반보다 작습니다"):
        evaluate(
            parse(
                {
                    "nodes": [
                        {
                            "id": "s",
                            "op": "sketch",
                            "shapes": [
                                {
                                    "type": "polyline",
                                    "start": [0, 0],
                                    "segments": [
                                        {"to": [40, 0]},
                                        {"to": [40, 30], "radius": 5},
                                        {"to": [0, 30]},
                                    ],
                                }
                            ],
                        },
                        {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                    ]
                }
            )
        )
    # 접선 호 — 앞 구간에 매끄럽게. 첫 구간이면 방향이 없다.
    tangent = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "path",
                                "start": [0, 0],
                                "segments": [
                                    {"to": [30, 0]},
                                    {"to": [45, 15], "tangent": True},
                                ],
                                "width": 4,
                            }
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert tangent.summary()["solid_count"] == 1
    with pytest.raises(RecipeValidationError, match="하나만"):
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {
                                "type": "path",
                                "start": [0, 0],
                                "segments": [{"to": [30, 0], "radius": 20, "tangent": True}],
                                "width": 4,
                            }
                        ],
                    }
                ]
            }
        )
    # 장공은 도면이 「중심 사이 30」 을 준다 — 전체 길이는 폭만큼 더 길다.
    centers = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [
                            {"type": "slot", "length": 30, "width": 8, "measure": "centers"}
                        ],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert centers.summary()["bbox"]["size"][0] == 38.0
    # 삼각형은 변 · 각 셋으로.
    triangle = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [{"type": "triangle", "a": 30, "b": 40, "C": 90}],
                    },
                    {"id": "e", "op": "extrude", "sketch": "s", "distance": 5},
                ]
            }
        )
    )
    assert triangle.shape.volume == pytest.approx(30 * 40 / 2 * 5)
    with pytest.raises(RecipeValidationError, match="변을 적어도"):
        parse(
            {
                "nodes": [
                    {
                        "id": "s",
                        "op": "sketch",
                        "shapes": [{"type": "triangle", "A": 30, "B": 60, "C": 90}],
                    }
                ]
            }
        )


def test_판금_절곡() -> None:
    bracket = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "m",
                        "op": "sheet_metal",
                        "thickness": 2,
                        "width": 40,
                        "path": [[0, 0], [0, 30], [20, 30]],
                        "bend_radius": 3,
                    }
                ]
            }
        )
    )
    box = bracket.summary()["bbox"]
    assert box["size"][1] == 40.0  # 폭만큼 밀렸고
    assert box["min"][1] == -20.0 and box["max"][1] == 20.0  # 꺾은선이 폭의 가운데다
    # 접은 판에도 구멍은 뚫린다 — 지그 브래킷은 결국 볼트로 붙는다.
    with_hole = evaluate(
        parse(
            {
                "nodes": [
                    {
                        "id": "m",
                        "op": "sheet_metal",
                        "thickness": 2,
                        "width": 40,
                        "path": [[0, 0], [0, 30], [20, 30]],
                        "bend_radius": 3,
                    },
                    {"id": "h", "op": "hole", "target": "m", "at": [[10, 0]], "thread": "M5"},
                ]
            }
        )
    )
    assert with_hole.shape.volume < bracket.shape.volume


def test_메시가_측정에_필요한_값을_준다() -> None:
    """화면의 측정은 이 값들로 잰다 — 구멍 지름 · 원 중심 · 면 법선. 없으면 사람이 점을 찍어
    어림해야 한다."""
    from app.core.recipe.mesh import mesh

    got = mesh(
        evaluate(
            parse(
                {
                    "nodes": [
                        {"id": "b", "op": "box", "length": 80, "width": 50, "height": 10},
                        {
                            "id": "h",
                            "op": "hole",
                            "target": "b",
                            "at": [[-25, 0], [25, 0]],
                            "diameter": 6,
                        },
                    ]
                }
            )
        ).shape
    )
    circles = [e for e in got["edges"] if e.get("radius")]
    assert len(circles) == 4  # 구멍 둘, 위아래로 하나씩
    assert {round(e["radius"] * 2, 3) for e in circles} == {6.0}
    tops = [tuple(e["center"]) for e in circles if e["center"][2] > 0]
    assert sorted(tops) == [(-25.0, 0.0, 5.0), (25.0, 0.0, 5.0)]  # 피치 50 을 그대로 잰다

    barrels = [f for f in got["faces"] if f.get("radius")]
    assert barrels and barrels[0]["axis"]["direction"] == [0.0, 0.0, 1.0]
    planes = [f for f in got["faces"] if f["kind"] == "plane"]
    up = next(f for f in planes if f["normal"][2] > 0.9)
    down = next(f for f in planes if f["normal"][2] < -0.9)
    assert up["center"][2] - down["center"][2] == 10.0  # 나란한 두 면 = 두께


def test_group_의_메시는_면마다_어느_구성품인지_말한다() -> None:
    """조립 미리보기가 구성품마다 색을 달리 칠하려면 면 · 엣지에 구성품 id 가 붙어야 한다."""
    from app.core.recipe.mesh import mesh

    recipe = parse(
        {
            "version": 1,
            "nodes": [
                {"id": "a", "op": "box", "length": 10, "width": 10, "height": 10},
                {
                    "id": "b",
                    "op": "box",
                    "length": 5,
                    "width": 5,
                    "height": 5,
                    "at": [20, 0, 0],
                },
                {"id": "g", "op": "group", "targets": ["a", "b"]},
            ],
        }
    )
    made = mesh(evaluate(recipe, resolve_file=None).shape)
    assert {face["part"] for face in made["faces"]} == {"a", "b"}
    assert [face["index"] for face in made["faces"]] == list(range(12))
    assert {edge["part"] for edge in made["edges"]} == {"a", "b"}

    box = {"id": "a", "op": "box", "length": 10, "width": 10, "height": 10}
    alone = parse({"version": 1, "nodes": [box]})
    assert "part" not in mesh(evaluate(alone, resolve_file=None).shape)["faces"][0]
