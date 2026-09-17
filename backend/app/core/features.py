"""2단계 — Feature Recognition.

지그가 관심 있는 특징만 뽑는다: **바닥면**(받침이 닿을 곳) · **윗면**(클램프가 누를 곳) ·
**옆면**(레스트가 기댈 곳) · **수직 구멍**(핀이 들어갈 곳). 그 이상(포켓 · 슬롯 · 필렛)은
이 뼈대에서 다루지 않는다 — 필요해지면 이 파일에 `kind` 를 하나 더한다.
"""

from __future__ import annotations

from build123d import Face, GeomType, Vector

from app.core.model import Feature, ProductGeometry, xyz

#: 법선이 축과 이만큼 가까우면 그 축을 향한 것으로 본다(코사인).
_AXIS_COS = 0.95
#: 바닥 · 윗면으로 볼 최소 면적(mm²). 모따기 자투리 면을 걸러 낸다.
_MIN_PLANE_AREA = 4.0
#: 구멍으로 볼 최소 반지름.
_MIN_HOLE_RADIUS = 1.0


def _plane_role(normal: Vector, center: Vector, geometry: ProductGeometry) -> str | None:
    z_lo, z_hi = geometry.bbox.min[2], geometry.bbox.max[2]
    if normal.Z < -_AXIS_COS:
        return "bottom" if abs(center.Z - z_lo) < 0.5 else "underside"
    if normal.Z > _AXIS_COS:
        return "top" if abs(center.Z - z_hi) < 0.5 else "step"
    if abs(normal.Z) < 1 - _AXIS_COS:
        return "side"
    return None


def _planes(geometry: ProductGeometry, start: int) -> list[Feature]:
    found: list[Feature] = []
    for face in geometry.shape.faces().filter_by(GeomType.PLANE):
        if face.area < _MIN_PLANE_AREA:
            continue
        center = face.center()
        normal = face.normal_at(center)
        role = _plane_role(normal, center, geometry)
        if role is None:
            continue
        found.append(
            Feature(
                index=start + len(found),
                kind="plane",
                role=role,
                center=xyz(center),
                normal=xyz(normal),
                area=round(float(face.area), 2),
            )
        )
    return found


def _is_hole(face: Face, axis_position: Vector) -> bool:
    """바깥쪽 법선이 축을 향하면 구멍(재료가 밖), 축에서 멀어지면 보스(재료가 안)."""
    center = face.center()
    normal = face.normal_at(center)
    to_axis = axis_position - center
    to_axis = Vector(to_axis.X, to_axis.Y, 0)
    if to_axis.length < 1e-6:
        return False
    return normal.dot(to_axis.normalized()) > 0


def _cylinders(geometry: ProductGeometry, start: int) -> list[Feature]:
    found: list[Feature] = []
    seen: list[tuple[float, float, float]] = []
    for face in geometry.shape.faces().filter_by(GeomType.CYLINDER):
        axis = face.axis_of_rotation
        if axis is None or abs(axis.direction.Z) < _AXIS_COS:
            continue  # 수직 구멍만 — 옆으로 난 구멍에는 판에서 핀을 세울 수 없다
        radius = float(face.radius)
        if radius < _MIN_HOLE_RADIUS:
            continue
        box = face.bounding_box()
        # 축 위의 점으로 구멍 중심을 잡는다. 반쪽 면 둘로 나뉜 구멍은 하나로 합친다.
        key = (round(axis.position.X, 2), round(axis.position.Y, 2), round(radius, 2))
        if key in seen:
            continue
        seen.append(key)
        kind = "hole" if _is_hole(face, axis.position) else "boss"
        z_lo, z_hi = geometry.bbox.min[2], geometry.bbox.max[2]
        through = abs(box.min.Z - z_lo) < 0.5 and abs(box.max.Z - z_hi) < 0.5
        role = ("through" if through else "blind") if kind == "hole" else "vertical"
        found.append(
            Feature(
                index=start + len(found),
                kind=kind,
                role=role,
                center=(key[0], key[1], round(float(box.min.Z), 3)),
                normal=None,
                area=round(float(face.area), 2),
                radius=round(radius, 3),
                depth=round(float(box.size.Z), 3),
                axis=(0.0, 0.0, 1.0),
            )
        )
    return found


def recognize(geometry: ProductGeometry) -> list[Feature]:
    planes = _planes(geometry, 0)
    cylinders = _cylinders(geometry, len(planes))
    return [*planes, *cylinders]


def largest(features: list[Feature], kind: str, role: str) -> Feature | None:
    picked = [one for one in features if one.kind == kind and one.role == role]
    return max(picked, key=lambda one: one.area) if picked else None


def bottom_face(geometry: ProductGeometry) -> Face:
    """가장 넓은 바닥 평면. 받침 후보점이 그 면 **안**에 있는지 물을 때 쓴다."""
    faces = geometry.shape.faces().filter_by(GeomType.PLANE)
    bottoms = [f for f in faces if f.normal_at(f.center()).Z < -_AXIS_COS]
    if not bottoms:
        raise ValueError("바닥에 평면이 없습니다 — 곡면 바닥은 이 뼈대가 다루지 않습니다.")
    return max(bottoms, key=lambda f: f.area)


def top_faces(geometry: ProductGeometry) -> list[Face]:
    faces = geometry.shape.faces().filter_by(GeomType.PLANE)
    z_hi = geometry.bbox.max[2]
    tops = [
        f
        for f in faces
        if f.normal_at(f.center()).Z > _AXIS_COS and abs(f.center().Z - z_hi) < 0.5
    ]
    return sorted(tops, key=lambda f: -f.area)


def upward_faces(geometry: ProductGeometry) -> list[Face]:
    """위를 보는 평면 전부(맨 위 · 단차) — 클램프 패드는 어느 쪽이든 누를 수 있다. 넓은 순."""
    faces = geometry.shape.faces().filter_by(GeomType.PLANE)
    ups = [
        f for f in faces if f.normal_at(f.center()).Z > _AXIS_COS and f.area >= _MIN_PLANE_AREA
    ]
    return sorted(ups, key=lambda f: -f.area)


def side_faces(geometry: ProductGeometry) -> list[Face]:
    faces = geometry.shape.faces().filter_by(GeomType.PLANE)
    sides = [f for f in faces if abs(f.normal_at(f.center()).Z) < 1 - _AXIS_COS]
    return sorted(sides, key=lambda f: -f.area)
