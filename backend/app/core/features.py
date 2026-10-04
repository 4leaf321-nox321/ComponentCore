"""2단계 — Feature Recognition.

지그가 관심 있는 특징만 뽑는다: **바닥면**(받침이 닿을 곳) · **윗면**(클램프가 누를 곳) ·
**옆면**(레스트가 기댈 곳) · **수직 구멍**(핀이 들어갈 곳).

2026-10-04 에 셋을 더했다 — 전에는 조용히 버려져 계획이 「없는 것」 으로 다뤘다.

- **경사면**(`plane` · `slope_up` / `slope_down`) — 축에 나란하지 않은 평면. 받침 · 클램프는
  평면에만 놓으므로 계획은 피하고, 그렇다고 메모로 말한다.
- **옆 구멍**(`hole` · `side_through` / `side_blind`, 축이 X · Y 에 나란하지 않으면
  `side_angled`) — 바닥 구멍이 모자라면 **측면 위치 핀**이 들어간다. 받침대는 그 입구를
  덮지 않는다.
- **포켓**(`pocket` · `top` / `bottom`) — 사방이 벽으로 막힌 바닥(위로 열림) · 천장(아래로
  열림). 전에는 「단차」 평면이었다. 클램프 패드를 그 바닥에 내리지 않는다.

슬롯 · 필렛은 아직 다루지 않는다 — 필요해지면 이 파일에 `kind` 를 하나 더한다.
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


def _plane_role(normal: Vector, center: Vector, geometry: ProductGeometry) -> str:
    z_lo, z_hi = geometry.bbox.min[2], geometry.bbox.max[2]
    if normal.Z < -_AXIS_COS:
        return "bottom" if abs(center.Z - z_lo) < 0.5 else "underside"
    if normal.Z > _AXIS_COS:
        return "top" if abs(center.Z - z_hi) < 0.5 else "step"
    if abs(normal.Z) < 1 - _AXIS_COS:
        return "side"
    return "slope_up" if normal.Z > 0 else "slope_down"


def is_pocket_floor(geometry: ProductGeometry, face: Face) -> bool:
    """위를 보는 평면이 **사방이 벽**인가 — 포켓의 바닥(아래를 보면 오목한 천장).

    면의 상자 네 변 바로 바깥을, 면에서 재료 쪽이 아닌 쪽으로 조금 띄워 찔러 본다: 넷 다
    재료 안이면 둘러싸였다(포켓 · 카운터보어), 한쪽이라도 허공이면 턱이다(단차). 둥근 포켓도
    상자 변의 가운데는 벽에 걸린다."""
    center = face.center()
    up = face.normal_at(center).Z > 0
    box = face.bounding_box()
    z = center.Z + (0.5 if up else -0.5)
    cx, cy = center.X, center.Y
    probes = [
        (box.min.X - 0.5, cy),
        (box.max.X + 0.5, cy),
        (cx, box.min.Y - 0.5),
        (cx, box.max.Y + 0.5),
    ]
    return all(geometry.shape.is_inside((x, y, z)) for x, y in probes)


def _planes(geometry: ProductGeometry, start: int) -> list[Feature]:
    found: list[Feature] = []
    for face in geometry.shape.faces().filter_by(GeomType.PLANE):
        if face.area < _MIN_PLANE_AREA:
            continue
        center = face.center()
        normal = face.normal_at(center)
        role = _plane_role(normal, center, geometry)
        kind = "plane"
        depth: float | None = None
        if role in ("step", "underside") and is_pocket_floor(geometry, face):
            kind, role = "pocket", "top" if role == "step" else "bottom"
            z_lo, z_hi = geometry.bbox.min[2], geometry.bbox.max[2]
            depth = round(float(z_hi - center.Z if role == "top" else center.Z - z_lo), 3)
        found.append(
            Feature(
                index=start + len(found),
                kind=kind,
                role=role,
                center=xyz(center),
                normal=xyz(normal),
                area=round(float(face.area), 2),
                depth=depth,
            )
        )
    return found


def _is_hole(face: Face, axis_position: Vector, direction: Vector | None = None) -> bool:
    """바깥쪽 법선이 축을 향하면 구멍(재료가 밖), 축에서 멀어지면 보스(재료가 안). 축에
    수직인 성분만 본다(세로 축이면 XY)."""
    center = face.center()
    normal = face.normal_at(center)
    axis = (direction or Vector(0, 0, 1)).normalized()
    to_axis = axis_position - center
    to_axis = to_axis - axis * to_axis.dot(axis)
    if to_axis.length < 1e-6:
        return False
    return normal.dot(to_axis.normalized()) > 0


def _side_cylinder(
    face: Face, geometry: ProductGeometry, index: int, seen: list[tuple[float, ...]]
) -> Feature | None:
    """옆으로 난 구멍 · 보스 — 축이 수평인 원통면. 축이 X · Y 에 나란하면 관통 여부를 본다."""
    axis = face.axis_of_rotation
    if axis is None:
        return None
    direction = axis.direction.normalized()
    radius = float(face.radius)
    if radius < _MIN_HOLE_RADIUS:
        return None
    # 축 위에서 원점에 가장 가까운 점 — 반쪽 면 둘로 나뉜 구멍을 하나로 합친다.
    foot = axis.position - direction * axis.position.dot(direction)
    key = (round(foot.X, 1), round(foot.Y, 1), round(foot.Z, 1), round(radius, 2))
    if key in seen:
        return None
    seen.append(key)
    is_hole = _is_hole(face, axis.position, direction)
    box = face.bounding_box()
    # 원통면의 `center()` 는 축 위가 아니라 면 위의 점이다(실측 — 반지름만큼 떠 있었다).
    # 축 위에서 면의 상자 한가운데에 가장 가까운 점을 중심으로 잡는다.
    middle = box.center()
    center = axis.position + direction * (middle - axis.position).dot(direction)
    if abs(direction.X) > _AXIS_COS or abs(direction.Y) > _AXIS_COS:
        i = 0 if abs(direction.X) > _AXIS_COS else 1
        lo, hi = (box.min.X, box.max.X) if i == 0 else (box.min.Y, box.max.Y)
        through = abs(lo - geometry.bbox.min[i]) < 0.5 and abs(hi - geometry.bbox.max[i]) < 0.5
        unit = (1.0, 0.0, 0.0) if i == 0 else (0.0, 1.0, 0.0)
        role = ("side_through" if through else "side_blind") if is_hole else "side"
        depth = float(hi - lo)
    else:
        unit = xyz(direction)
        role = "side_angled" if is_hole else "side"
        depth = float(
            abs(box.size.X * direction.X)
            + abs(box.size.Y * direction.Y)
            + abs(box.size.Z * direction.Z)
        )
    return Feature(
        index=index,
        kind="hole" if is_hole else "boss",
        role=role,
        center=xyz(center),
        normal=None,
        area=round(float(face.area), 2),
        radius=round(radius, 3),
        depth=round(depth, 3),
        axis=unit,
    )


def _cylinders(geometry: ProductGeometry, start: int) -> list[Feature]:
    found: list[Feature] = []
    seen: list[tuple[float, ...]] = []
    for face in geometry.shape.faces().filter_by(GeomType.CYLINDER):
        axis = face.axis_of_rotation
        if axis is None:
            continue
        if abs(axis.direction.Z) < 1 - _AXIS_COS:
            # 옆으로 난 구멍 — 판에서 세운 핀은 못 들어가지만 측면 핀이 들어간다.
            side = _side_cylinder(face, geometry, start + len(found), seen)
            if side is not None:
                found.append(side)
            continue
        if abs(axis.direction.Z) < _AXIS_COS:
            continue  # 비스듬한 축 — 아직 다루지 않는다
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
        raise ValueError("바닥에 평면이 없습니다. 곡면 바닥은 지원하지 않습니다.")
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
