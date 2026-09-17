"""기본 도형 템플릿 — 레시피로 적은 상자 · 원기둥 · 구멍판 · L 브래킷.

`core/primitives.py` 의 네 가지와 같은 형상이다. 편집기는 이것을 「새로 만들기」 의 출발점으로
쓰고, 옛 `product_spec` 은 `from_primitive_spec` 으로 레시피가 된다.
"""

from __future__ import annotations

from typing import Any


def box(length: float = 80, width: float = 50, height: float = 20) -> dict[str, Any]:
    return {
        "version": 1,
        "nodes": [
            {
                "id": "base",
                "op": "sketch",
                "label": "바닥 윤곽",
                "shapes": [{"type": "rect", "width": length, "height": width}],
            },
            {
                "id": "body",
                "op": "extrude",
                "label": "몸통",
                "sketch": "base",
                "distance": height,
            },
        ],
    }


def cylinder(radius: float = 25, height: float = 40) -> dict[str, Any]:
    return {
        "version": 1,
        "nodes": [
            {
                "id": "base",
                "op": "sketch",
                "label": "바닥 원",
                "shapes": [{"type": "circle", "radius": radius}],
            },
            {
                "id": "body",
                "op": "extrude",
                "label": "몸통",
                "sketch": "base",
                "distance": height,
            },
        ],
    }


def plate_with_holes(
    length: float = 100,
    width: float = 60,
    thickness: float = 12,
    hole_diameter: float = 8,
    hole_margin: float = 10,
) -> dict[str, Any]:
    dx, dy = length / 2 - hole_margin, width / 2 - hole_margin
    return {
        "version": 1,
        "nodes": [
            {
                "id": "base",
                "op": "sketch",
                "label": "판 윤곽",
                "shapes": [{"type": "rect", "width": length, "height": width}],
            },
            {
                "id": "plate",
                "op": "extrude",
                "label": "판",
                "sketch": "base",
                "distance": thickness,
            },
            {
                "id": "holes",
                "op": "hole",
                "label": "모서리 구멍 4",
                "target": "plate",
                "at": [[-dx, -dy], [dx, -dy], [dx, dy], [-dx, dy]],
                "diameter": hole_diameter,
            },
        ],
    }


def bracket(
    length: float = 80,
    width: float = 50,
    height: float = 40,
    thickness: float = 8,
    hole_diameter: float = 6,
) -> dict[str, Any]:
    hole_y = width / 2 - (width - thickness) / 3
    return {
        "version": 1,
        "nodes": [
            {
                "id": "base_sk",
                "op": "sketch",
                "label": "바닥판 윤곽",
                "shapes": [{"type": "rect", "width": length, "height": width}],
            },
            {
                "id": "base",
                "op": "extrude",
                "label": "바닥판",
                "sketch": "base_sk",
                "distance": thickness,
            },
            {
                "id": "wall_sk",
                "op": "sketch",
                "label": "벽 윤곽",
                "plane": {"name": "XY", "origin": [0, -(width - thickness) / 2, 0]},
                "shapes": [{"type": "rect", "width": length, "height": thickness}],
            },
            {
                "id": "wall",
                "op": "extrude",
                "label": "벽",
                "sketch": "wall_sk",
                "distance": height,
            },
            {"id": "body", "op": "union", "label": "몸통", "targets": ["base", "wall"]},
            {
                "id": "holes",
                "op": "hole",
                "label": "바닥 구멍 2",
                "target": "body",
                "at": [[-length / 3, hole_y], [length / 3, hole_y]],
                "diameter": hole_diameter,
            },
            {
                "id": "rounded",
                "op": "fillet",
                "label": "모서리 R",
                "target": "holes",
                "edges": "vertical",
                "radius": min(3.0, thickness / 3),
            },
        ],
    }


TEMPLATES: dict[str, Any] = {
    "box": box,
    "cylinder": cylinder,
    "plate_with_holes": plate_with_holes,
    "bracket": bracket,
}

#: 편집기 · AI 가 보는 설명.
TEMPLATE_LABELS = {
    "box": "상자",
    "cylinder": "원기둥",
    "plate_with_holes": "구멍 뚫린 판",
    "bracket": "L 브래킷",
}


def from_primitive_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """옛 `product_spec`({"kind": "box", "length": …}) 을 레시피로."""
    kind = str(spec.get("kind", ""))
    if kind not in TEMPLATES:
        raise ValueError(f"모르는 도형입니다: {kind!r}")
    params = {key: float(value) for key, value in spec.items() if key != "kind"}
    return dict(TEMPLATES[kind](**params))


def all_templates() -> dict[str, dict[str, Any]]:
    return {name: make() for name, make in TEMPLATES.items()}
