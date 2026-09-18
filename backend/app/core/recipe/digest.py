"""형상 요약 — **AI 가 읽는 치수표.**

사람은 3D 에서 면을 눌러 보고 자를 대지만, AI 는 못 본다. 그래서 만든 형상에서 **설계에 쓰는
값**만 추려 말로 준다: 크기 · 평면(법선 · 넓이) · 원통 · **구멍(지름 · 중심 · 깊이)** ·
긴 모서리.

메시 전체(`mesh.py`)는 삼각형 좌표까지 있어 수십만 자다 — 그대로 주면 AI 의 맥락이 다 찬다.
여기서는 종류별로 **큰 것부터 몇 개**만 남기고 나머지는 개수로 말한다.
"""

from __future__ import annotations

import contextlib
import math
from typing import Any

from build123d import Shape
from OCP.BRepGProp import BRepGProp
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps

#: 자주 쓰는 재료의 밀도(g/cm³). 지그는 보통 알루미늄 · 강, 시제품은 수지다.
DENSITIES: dict[str, float] = {
    "steel": 7.85,
    "stainless": 7.9,
    "aluminum": 2.70,
    "brass": 8.5,
    "abs": 1.05,
    "pla": 1.24,
    "nylon": 1.14,
    "pom": 1.41,
}

#: 종류마다 몇 개까지 이름을 붙여 줄 것인가.
_LIMIT = 12


def _xyz(v: Any) -> list[float]:
    return [round(v.X, 3), round(v.Y, 3), round(v.Z, 3)]


def _same(a: list[float], b: list[float], tolerance: float = 1e-3) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def _circle_axis(edge: Any) -> list[float] | None:
    """원이 놓인 평면의 법선 = 구멍이 뚫린 방향. 세 점으로 구한다."""
    try:
        a, b, c = (edge.position_at(t) for t in (0.0, 0.34, 0.67))
    except Exception:
        return None
    u = (b - a).normalized()
    v = (c - a).normalized()
    normal = u.cross(v)
    if normal.length < 1e-9:
        return None
    normal = normal.normalized()
    # 방향은 뒤집혀도 같은 축이다 — 첫 성분이 양수가 되게 맞춰 둔다.
    for value in (normal.X, normal.Y, normal.Z):
        if abs(value) > 1e-9:
            if value < 0:
                normal = normal * -1
            break
    return [round(normal.X, 4), round(normal.Y, 4), round(normal.Z, 4)]


def _parallel(a: list[float], b: list[float], tolerance: float = 1e-3) -> bool:
    cross = (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    return math.sqrt(sum(one * one for one in cross)) <= tolerance


def _holes(shape: Shape) -> list[dict[str, Any]]:
    """원 모서리를 짝지어 **구멍**으로 — 같은 지름의 원 둘이 **같은 축 위에서** 마주 보면 그
    사이가 깊이다.

    축을 안 보면 나란한 두 구멍의 입구끼리 묶여 「깊이 50 짜리 구멍」 같은 헛값이 나온다(실측).
    구멍은 지그에서 가장 자주 쓰는 값이다(핀 자리 · 볼트 자리). 짝을 못 찾은 원은 홀로 남긴다
    (관통 구멍의 한쪽 · 모따기 된 입구)."""
    circles: list[dict[str, Any]] = []
    for edge in shape.edges():
        try:
            radius = float(edge.radius)
        except Exception:
            continue
        circles.append(
            {
                "radius": round(radius, 3),
                "center": _xyz(edge.arc_center),
                "axis": _circle_axis(edge),
            }
        )
    out: list[dict[str, Any]] = []
    used: set[int] = set()
    for index, one in enumerate(circles):
        if index in used:
            continue
        mate = None
        for other_index in range(index + 1, len(circles)):
            other = circles[other_index]
            if other_index in used or other["radius"] != one["radius"]:
                continue
            if _same(one["center"], other["center"]):
                continue
            # 같은 축 위에 있어야 한 구멍의 입구와 바닥이다.
            gap = [b - a for a, b in zip(one["center"], other["center"], strict=True)]
            axis = one["axis"]
            if axis is None or other["axis"] is None:
                continue
            if not _parallel(axis, other["axis"]) or not _parallel(axis, gap):
                continue
            mate = other_index
            break
        if mate is None:
            out.append(
                {
                    "diameter": round(one["radius"] * 2, 3),
                    "at": one["center"],
                    "axis": one["axis"],
                }
            )
            used.add(index)
            continue
        other = circles[mate]
        used.update({index, mate})
        depth = math.dist(one["center"], other["center"])
        top = max(one["center"], other["center"], key=lambda p: p[2])
        out.append(
            {
                "diameter": round(one["radius"] * 2, 3),
                "at": top,
                "depth": round(depth, 3),
                "axis": one["axis"],
                "from": one["center"],
                "to": other["center"],
            }
        )
    out.sort(key=lambda hole: (-hole["diameter"], hole["at"]))
    return out


def mass_properties(shape: Shape, material: str = "aluminum") -> dict[str, Any]:
    """질량 · 무게중심 · **관성 모멘트** — 진동 · 무게 중심 잡기에 쓰는 값.

    관성은 **무게중심 기준**으로 낸다(원점 기준이면 형상을 옮기기만 해도 값이 바뀐다).
    단위: 부피 mm³ · 질량 g · 관성 g·mm². 공진 주파수는 여기서 바로 나오지 않는다 — 강성이
    있어야 하고, 그것은 해석(모달)의 몫이다.
    """
    density = DENSITIES.get(material.lower())
    if density is None:
        known = ", ".join(sorted(DENSITIES))
        raise ValueError(f"모르는 재료입니다: {material} (아는 것: {known})")
    at_origin = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, at_origin)
    center = at_origin.CentreOfMass()
    about_center = GProp_GProps(gp_Pnt(center.X(), center.Y(), center.Z()))
    BRepGProp.VolumeProperties_s(shape.wrapped, about_center)
    matrix = about_center.MatrixOfInertia()
    volume = float(at_origin.Mass())
    # g/cm³ 는 mm³ 당 1/1000 g 이다.
    mass = volume * density / 1000.0
    inertia = [
        [round(matrix.Value(i, j) * density / 1000.0, 3) for j in (1, 2, 3)] for i in (1, 2, 3)
    ]
    return {
        "material": material.lower(),
        "density_g_per_cm3": density,
        "volume_mm3": round(volume, 2),
        "mass_g": round(mass, 3),
        "center_of_mass": [round(center.X(), 3), round(center.Y(), 3), round(center.Z(), 3)],
        "inertia_g_mm2_about_com": inertia,
        "note": "관성은 무게중심 기준. 공진 주파수는 강성이 있어야 나온다(모달 해석).",
    }


def digest(shape: Shape, *, material: str | None = None) -> dict[str, Any]:
    """설계에 쓰는 값만 추린 요약."""
    box = shape.bounding_box()
    planes: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    other_faces = 0
    for face in shape.faces():
        kind = face.geom_type.name.lower()
        center = face.center()
        if kind == "plane":
            planes.append(
                {
                    "center": _xyz(center),
                    "normal": _xyz(face.normal_at(center)),
                    "area": round(float(face.area), 2),
                }
            )
        elif kind in {"cylinder", "cone", "sphere", "torus"}:
            entry: dict[str, Any] = {"kind": kind, "area": round(float(face.area), 2)}
            with contextlib.suppress(Exception):
                entry["radius"] = round(float(face.radius), 3)
            try:
                entry["axis"] = _xyz(face.axis_of_rotation.direction)
                entry["axis_at"] = _xyz(face.axis_of_rotation.position)
            except Exception:
                pass
            rounds.append(entry)
        else:
            other_faces += 1
    planes.sort(key=lambda one: -one["area"])
    rounds.sort(key=lambda one: -one["area"])

    edges = shape.edges()
    lengths = sorted((round(float(e.length), 3) for e in edges), reverse=True)
    holes = _holes(shape)
    out: dict[str, Any] = {
        "bbox": {"min": _xyz(box.min), "max": _xyz(box.max), "size": _xyz(box.size)},
        "volume": round(float(shape.volume), 2),
        "surface_area": round(float(shape.area), 2),
        "solid_count": len(shape.solids()),
        "faces": {
            "total": len(shape.faces()),
            "planes": planes[:_LIMIT],
            "planes_total": len(planes),
            "curved": rounds[:_LIMIT],
            "curved_total": len(rounds),
            "other": other_faces,
        },
        "holes": holes[:_LIMIT],
        "holes_total": len(holes),
        "edges": {"total": len(edges), "longest": lengths[:5]},
        "note": "면 · 구멍은 큰 것부터 추렸습니다(전체는 *_total). 좌표 mm, 법선은 단위 벡터.",
    }
    if material:
        out["mass"] = mass_properties(shape, material)
    return out
