"""면 · 엣지 단위 메시 — 3D 에서 고르기 위한 것.

glTF 는 형상 하나를 한 덩어리로 주므로 어느 면을 눌렀는지 알 수 없다. 여기서는 면마다 삼각형을,
엣지마다 꺾은선을 따로 내고, 면의 중심 · 법선, 엣지의 중점을 함께 준다 — 편집기가 「이 면에
스케치」 「이 엣지에 필렛」 을 할 때 쓰는 값이다.
"""

from __future__ import annotations

import contextlib
from typing import Any

from build123d import Axis, Edge, Face, GeomType, Shape

#: 삼각형 분할 허용치. 미리보기용이라 거칠어도 된다 — 작을수록 삼각형이 배로 는다.
_LINEAR = 0.1
_ANGULAR = 0.3
#: 곡선 엣지를 몇 점으로 그리나.
_CURVE_POINTS = 24


def _xyz(v: Any) -> list[float]:
    return [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]


def _radius(shape: Any) -> float | None:
    """원 · 원통의 반지름. 아닌 것은 None — 화면이 「지름 ⌀16」 을 그때만 보여 준다.

    `radius` 는 원으로 줄일 수 없는 모양에서 예외를 던진다(직선 엣지 · 평면). 값으로 묻는다."""
    try:
        return round(float(shape.radius), 4)
    except Exception:
        return None


def _face(index: int, face: Face) -> dict[str, Any]:
    vertices, triangles = face.tessellate(_LINEAR, _ANGULAR)
    center = face.center()
    try:
        normal = face.normal_at(center)
    except Exception:
        normal = face.normal_at()
    out = {
        "index": index,
        "kind": face.geom_type.name.lower(),
        "center": _xyz(center),
        "normal": _xyz(normal),
        "area": round(float(face.area), 3),
        "vertices": [c for v in vertices for c in _xyz(v)],
        "triangles": [i for tri in triangles for i in tri],
    }
    radius = _radius(face)
    if radius is not None:
        # 원통 · 구는 **축 위의 중심**이 뜻을 갖는다 — 면 중심은 껍질 위의 한 점이다.
        out["radius"] = radius
        with contextlib.suppress(Exception):
            out["axis"] = {
                "origin": _xyz(face.axis_of_rotation.position),
                "direction": _xyz(face.axis_of_rotation.direction),
            }
    return out


def _edge(index: int, edge: Edge) -> dict[str, Any]:
    straight = edge.geom_type == GeomType.LINE
    count = 2 if straight else _CURVE_POINTS
    points = [edge.position_at(i / (count - 1)) for i in range(count)]
    tangent = edge.tangent_at(0.5)
    out = {
        "index": index,
        "kind": edge.geom_type.name.lower(),
        "midpoint": _xyz(edge.position_at(0.5)),
        "length": round(float(edge.length), 3),
        "vertical": abs(tangent.dot(Axis.Z.direction)) > 0.95,
        "points": [c for p in points for c in _xyz(p)],
    }
    radius = _radius(edge)
    if radius is not None:
        # 구멍 지름은 가장 자주 재는 값이다 — 점을 찍어 재게 하지 않는다.
        out["radius"] = radius
        with contextlib.suppress(Exception):
            out["center"] = _xyz(edge.arc_center)
    return out


def mesh(shape: Shape) -> dict[str, Any]:
    box = shape.bounding_box()
    return {
        "bbox": {"min": _xyz(box.min), "max": _xyz(box.max)},
        "faces": [_face(i, f) for i, f in enumerate(shape.faces())],
        "edges": [_edge(i, e) for i, e in enumerate(shape.edges())],
    }
