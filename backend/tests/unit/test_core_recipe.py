"""레시피 — 모양(schema) · 평가 · 템플릿을 서버 없이 본다."""

from __future__ import annotations

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
    assert "앞에 없는 노드" in caught.value.problems[0]


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
