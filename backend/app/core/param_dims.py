"""변수 → 형상 위의 치수 — 「이 변수가 어느 치수인가」 를 3D 에 보인다.

DOE 표에는 `두께 3.2 · 폭 20 · 간격비 16` 이 있는데 3D 에는 어느 것이 어디인지 적혀 있지
않았다. 형상을 여럿 훑으면 더 헷갈린다(2026-11-16 사용자 요청). 편집기의 변수 목록, 새 DOE,
DOE 결과의 3D 가 이것으로 치수선을 긋는다.

## 어떻게 찾나

변수 값을 조금(`δ` — 값의 1%, 적어도 0.05) 바꿔 **한 번 더 만들고 두 형상을 견준다.** 지금 값과
같고 바꾼 형상에서는 `값 + δ` 인 치수가 그 변수의 치수다:

- 평행한 두 평면 사이(두께 · 폭 · 길이) — `distance`
- 원통 · 구의 지름 · 반지름(구멍 · 필렛) — `diameter` · `radius`
- 평행한 두 원통 축 사이(지지 간격 · 구멍 간격) — `axes`
- 원통 축과 평면 사이(가장자리에서 구멍까지) — `axis_plane`
- 두 평면의 각(도) — `angle`

치수에는 **바탕이 움직인 면이 하나는 끼어야** 한다. 같은 값의 다른 치수(폭 50 과 길이 50)가
걸리지 않고, 면이 많은 조립에서 짝을 다 세지 않는다. 연산마다 규칙을 두지 않는다 — 식
(`=판_길이 - 15`) · 구속 스케치 · 조립의 구성품 무엇으로 정했든 형상만 본다.

값과 같은 치수가 없으면(비율 `간격비` · 원점에서 잰 위치 · 각도 0°) 그 변수가 **바탕을 옮긴
면**을 알린다(`moved`) — 평면의 자리, 원통의 축 · 반지름이 바뀐 면이다. 늘어나기만 한 면(판
길이를 늘릴 때의 윗면)은 아니다. 형상이 그대로면 형상에 안 쓰는 변수다(`unused` — 압력 ·
마찰계수 같은 해석 조건).

## 실측(2026-11-16, 개발 DB 의 도면 28 · 변수 85)

치수까지 찾음 63 · 움직인 면만 9 · 형상과 무관 13. 한 번 더 만드는 데 부품 0.01 ~ 1.7 초, 조립
2.5 초 — 변수가 여럿이면 그 배다. 그래서 시간 상한(`BUDGET`)이 있고, 넘으면 남은 변수는
건너뛴다(`skipped`).

면 번호는 메시와 같은 순서다(`mesh.ordered_faces`) — 화면이 그 번호의 면을 칠한다. 웹 · DB 를
모른다: 만드는 함수(`build`)를 받는다.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from build123d import GeomType, Shape, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface

from app.core.recipe.mesh import ordered_faces
from app.core.recipe.params import resolve_params

#: 같은 자리로 볼 거리(mm). 해석적 면은 1e-9 안쪽으로 맞고, 구속 스케치의 수치 풀이가 그보다
#: 거칠다. δ 는 적어도 0.05 라 움직인 면과 헷갈리지 않는다.
_TOL = 1e-5
#: 평행으로 볼 내적의 여유(1 - |cos|). 0.05° 돌린 면도 움직인 것으로 잡는다.
_PARALLEL = 1e-9
#: 한 요청에 쓸 시간(초) — 화면이 기다린다. 넘으면 남은 변수는 `skipped`.
BUDGET = 30.0
#: 칠할 면 수의 상한 — 「벽」 하나가 수십 면을 움직인다. 화면에 보낼 양이다.
MAX_FACES = 200
#: 치수를 찾을 때 볼 움직인 면의 상한(넓은 것부터) — 구성품 하나를 옮기는 변수는 그 면을 다
#: 움직이고, 짝을 다 세면 면 수의 제곱이다.
MAX_DRIVING = 200
#: 같은 변수가 여러 꼴로 맞으면 사람이 그 값으로 부를 법한 것을 앞에 — 구멍은 지름, 판은 두께.
_RANK = {"diameter": 0, "radius": 0, "distance": 1, "axes": 2, "axis_plane": 3, "angle": 4}


@dataclass
class _Face:
    index: int
    kind: str
    """`plane` · `cylinder` · `sphere` · `other`(그 밖의 곡면 — 중심 · 넓이로만 견준다)."""
    center: Vector
    area: float
    face: Any
    normal: Vector | None = None
    offset: float = 0.0
    """평면의 자리 — `normal · 면 위의 점`."""
    radius: float = 0.0
    axis: Vector | None = None
    origin: Vector | None = None
    """원통이면 축 위에서 면 중심에 가장 가까운 점, 구면 중심."""


@dataclass
class _Hit:
    kind: str
    value: float
    faces: tuple[int, ...]
    mid: Vector
    """치수의 자리 — 바꾼 형상의 같은 치수를 찾을 때 견준다."""
    a: _Face
    b: _Face | None
    place: tuple[Any, ...]
    """같은 치수인지 — 한 평면이 면 여럿으로 쪼개져도 한 곳으로 센다."""


def _vec(x: Any) -> Vector:
    return Vector(float(x.X()), float(x.Y()), float(x.Z()))


def _features(shape: Shape) -> list[_Face]:
    out: list[_Face] = []
    for index, face in enumerate(ordered_faces(shape)):
        center = face.center()
        one = _Face(index, "other", center, float(face.area), face)
        try:
            if face.geom_type == GeomType.PLANE:
                normal = face.normal_at()
                one.kind, one.normal, one.offset = "plane", normal, normal.dot(center)
            elif face.geom_type == GeomType.CYLINDER:
                cylinder = BRepAdaptor_Surface(face.wrapped).Cylinder()
                axis = _vec(cylinder.Axis().Direction()).normalized()
                point = _vec(cylinder.Axis().Location())
                one.kind, one.radius, one.axis = "cylinder", float(cylinder.Radius()), axis
                one.origin = point + axis * axis.dot(center - point)
            elif face.geom_type == GeomType.SPHERE:
                sphere = BRepAdaptor_Surface(face.wrapped).Sphere()
                one.kind, one.radius = "sphere", float(sphere.Radius())
                one.origin = _vec(sphere.Location())
        except Exception:
            # 바탕을 못 읽는 면은 중심 · 넓이로만 견준다 — 치수에는 안 끼지만 움직인 면으로는
            # 잡힌다.
            one.kind = "other"
        out.append(one)
    return out


def _line_gap(point: Vector, axis: Vector, other: Vector) -> float:
    """`point` 를 지나는 `axis` 방향 직선에서 `other` 까지."""
    w = other - point
    return (w - axis * w.dot(axis)).length


def _same(a: _Face, b: _Face) -> bool:
    """바탕이 같은 면인가 — 평면은 자리, 원통은 축 · 반지름. 테두리(넓이)는 안 본다."""
    if a.kind != b.kind:
        return False
    if a.kind == "plane":
        assert a.normal is not None and b.normal is not None
        return a.normal.dot(b.normal) > 1 - _PARALLEL and abs(a.offset - b.offset) < _TOL
    if a.kind == "cylinder":
        assert a.axis is not None and b.axis is not None
        assert a.origin is not None and b.origin is not None
        return (
            abs(a.radius - b.radius) < _TOL
            and abs(a.axis.dot(b.axis)) > 1 - _PARALLEL
            and _line_gap(a.origin, a.axis, b.origin) < _TOL
        )
    if a.kind == "sphere":
        assert a.origin is not None and b.origin is not None
        return abs(a.radius - b.radius) < _TOL and (a.origin - b.origin).length < _TOL
    return (a.center - b.center).length < _TOL and abs(a.area - b.area) < _TOL * max(
        1.0, a.area
    )


def _bucket(face: _Face) -> tuple[Any, ...]:
    """견줄 후보를 좁히는 열쇠 — 평면은 법선, 원통은 반지름. 경계에 걸려 못 찾으면 다
    훑는다."""
    if face.kind == "plane" and face.normal is not None:
        return ("plane", *(round(c, 3) + 0.0 for c in face.normal))
    if face.kind in ("cylinder", "sphere"):
        return (face.kind, round(face.radius, 3))
    return (face.kind,)


def _unmatched(these: list[_Face], those: list[_Face]) -> list[_Face]:
    """`these` 중에 `those` 에 같은 바탕이 없는 면."""
    buckets: dict[tuple[Any, ...], list[_Face]] = {}
    by_kind: dict[str, list[_Face]] = {}
    for one in those:
        buckets.setdefault(_bucket(one), []).append(one)
        by_kind.setdefault(one.kind, []).append(one)
    out = []
    for one in these:
        if any(_same(one, other) for other in buckets.get(_bucket(one), [])):
            continue
        if any(_same(one, other) for other in by_kind.get(one.kind, [])):
            continue
        out.append(one)
    return out


def _plane_key(face: _Face) -> tuple[Any, ...]:
    assert face.normal is not None
    return (*(round(c, 4) + 0.0 for c in face.normal), round(face.offset, 4) + 0.0)


def _axis_key(face: _Face) -> tuple[Any, ...]:
    """축 직선 하나 — 방향의 부호를 맞추고, 원점에 가장 가까운 점."""
    assert face.axis is not None and face.origin is not None
    axis = face.axis
    first = next((c for c in (axis.X, axis.Y, axis.Z) if abs(c) > 1e-9), 1.0)
    if first < 0:
        axis = -axis
    foot = face.origin - axis * axis.dot(face.origin)
    return (*(round(c, 4) + 0.0 for c in axis), *(round(c, 4) + 0.0 for c in foot))


def _pairs(a: _Face, b: _Face) -> list[tuple[str, float, tuple[Any, ...]]]:
    """두 면 사이의 치수들 — `(종류, 값, 같은 곳 열쇠)`."""
    out: list[tuple[str, float, tuple[Any, ...]]] = []
    if a.kind == "plane" and b.kind == "plane":
        assert a.normal is not None and b.normal is not None
        dot = a.normal.dot(b.normal)
        keys = tuple(sorted((_plane_key(a), _plane_key(b))))
        if abs(dot) > 1 - _PARALLEL:
            gap = abs(a.normal.dot(b.center - a.center))
            if gap > _TOL:
                out.append(("distance", gap, keys))
        else:
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            out.append(("angle", angle, keys))
            out.append(("angle", 180.0 - angle, keys))
        return out
    cylinder, plane = (a, b) if a.kind == "cylinder" else (b, a)
    if cylinder.kind == "cylinder" and plane.kind == "plane":
        assert cylinder.axis is not None and cylinder.origin is not None
        assert plane.normal is not None
        if abs(cylinder.axis.dot(plane.normal)) < 1e-7:
            gap = abs(plane.normal.dot(cylinder.origin) - plane.offset)
            if gap > _TOL:
                out.append(("axis_plane", gap, (_axis_key(cylinder), _plane_key(plane))))
        return out
    if a.kind == "cylinder" and b.kind == "cylinder":
        assert a.axis is not None and b.axis is not None
        assert a.origin is not None and b.origin is not None
        if abs(a.axis.dot(b.axis)) > 1 - _PARALLEL:
            gap = _line_gap(a.origin, a.axis, b.origin)
            if gap > _TOL:
                out.append(("axes", gap, tuple(sorted((_axis_key(a), _axis_key(b))))))
    return out


def _near(value: float, wanted: float) -> bool:
    return abs(value - wanted) <= max(1e-6, 1e-5 * abs(wanted))


def _hits(faces: list[_Face], driving: list[_Face], wanted: float) -> list[_Hit]:
    """`driving`(바탕이 움직인 면)이 끼고 값이 `wanted` 인 치수들 — 같은 곳은 하나로."""
    found: dict[tuple[Any, ...], _Hit] = {}

    def keep(hit: _Hit) -> None:
        key = (hit.kind, *hit.place)
        best = found.get(key)
        # 같은 곳이면 넓은 면 쪽 — 화면에서 잘 보인다.
        if best is None or _weight(hit) > _weight(best):
            found[key] = hit

    for a in sorted(driving, key=lambda one: one.area, reverse=True)[:MAX_DRIVING]:
        if a.kind in ("cylinder", "sphere"):
            assert a.origin is not None
            where = (_axis_key(a),) if a.kind == "cylinder" else (round(a.origin.X, 4),)
            for kind, value in (("radius", a.radius), ("diameter", 2 * a.radius)):
                if _near(value, wanted):
                    keep(
                        _Hit(
                            kind,
                            value,
                            (a.index,),
                            a.origin,
                            a,
                            None,
                            (round(a.radius, 4), *where),
                        )
                    )
        for b in faces:
            if b.index == a.index:
                continue
            for kind, value, place in _pairs(a, b):
                if _near(value, wanted):
                    first, second = (
                        (a, b) if a.kind != "plane" or b.kind == "plane" else (b, a)
                    )
                    mid = (a.center + b.center) * 0.5
                    keep(
                        _Hit(
                            kind, value, (first.index, second.index), mid, first, second, place
                        )
                    )
    return list(found.values())


def _weight(hit: _Hit) -> float:
    return min(hit.a.area, hit.b.area) if hit.b is not None else hit.a.area


def _xyz(v: Vector) -> list[float]:
    return [round(v.X, 4) + 0.0, round(v.Y, 4) + 0.0, round(v.Z, 4) + 0.0]


def _vertices(face: _Face) -> list[Vector]:
    try:
        return [Vector(v.X, v.Y, v.Z) for v in face.face.vertices()]
    except Exception:
        return []


def _rim(face: _Face, middle: Vector) -> tuple[Vector, Vector]:
    """원통 축의 **끝**(형상 가운데에서 먼 쪽 — 구멍이면 윗면의 테)과, 그 테로 가는 방향."""
    assert face.axis is not None and face.origin is not None
    axis, origin = face.axis, face.origin
    corners = _vertices(face)
    if corners:
        spans = [axis.dot(v - origin) for v in corners]
        ends = [origin + axis * min(spans), origin + axis * max(spans)]
        at = max(ends, key=lambda p: (p - middle).length)
        rim = min(corners, key=lambda v: abs(axis.dot(v - at)))
        out = rim - at
        out = out - axis * out.dot(axis)
        if out.length > 1e-9:
            return at, out.normalized()
    else:
        at = origin
    side = axis.cross(Vector(0, 0, 1))
    if side.length < 1e-9:
        side = axis.cross(Vector(1, 0, 0))
    return at, side.normalized()


def _ends(hit: _Hit, middle: Vector, scale: float) -> tuple[Vector, Vector] | None:
    """치수선의 두 끝 — 형상 가운데에서 먼 테두리에 둔다(뷰어가 바깥으로 비켜 긋는다)."""
    a, b = hit.a, hit.b
    if hit.kind in ("radius", "diameter"):
        if a.kind == "sphere":
            assert a.origin is not None
            side = Vector(1, 0, 0)
            at = a.origin
        else:
            at, side = _rim(a, middle)
        if hit.kind == "radius":
            return at, at + side * a.radius
        return at - side * a.radius, at + side * a.radius
    if b is None:
        return None
    if hit.kind == "distance":
        assert a.normal is not None
        normal = a.normal

        def projected(p: Vector) -> Vector:
            return p - normal * normal.dot(p - b.center)

        def spread(p: Vector) -> float:
            w = p - middle
            return (w - normal * normal.dot(w)).length

        corners = sorted(_vertices(a), key=spread, reverse=True)
        for p in corners[:8]:
            q = projected(p)
            try:
                if b.face.distance_to(q) < 1e-3 * max(1.0, scale):
                    return p, q
            except Exception:
                break
        p = corners[0] if corners else a.center
        return p, projected(p)
    if hit.kind == "axes":
        assert b.axis is not None and b.origin is not None
        at, _ = _rim(a, middle)
        return at, b.origin + b.axis * b.axis.dot(at - b.origin)
    if hit.kind == "axis_plane":
        assert b.normal is not None
        at, _ = _rim(a, middle)
        return at, at - b.normal * (b.normal.dot(at) - b.offset)
    return None


def _with(raw: dict[str, Any], name: str, value: float) -> dict[str, Any]:
    return {**raw, "params": {**(raw.get("params") or {}), name: value}}


def _shifts(value: float) -> list[float]:
    """바꿔 볼 양 — 1% 위, 안 되면 아래. 정수면(개수일 수 있다) 끝에 ±1."""
    small = max(abs(value) * 0.01, 0.05)
    out = [small, -small]
    if float(value).is_integer():
        out += [1.0, -1.0]
    return out


def _signature(faces: list[_Face]) -> list[tuple[Any, ...]]:
    return sorted(
        (one.kind, *(round(c, 4) + 0.0 for c in one.center), round(one.area, 3))
        for one in faces
    )


def find(
    raw: dict[str, Any],
    names: list[str] | None,
    build: Callable[[dict[str, Any]], Shape],
    *,
    base: Shape | None = None,
    budget: float = BUDGET,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """변수마다 형상 위의 치수. `names` 가 없으면 도면의 변수 전부.

    `build` 는 레시피 → 형상(실패하면 무엇이든 던진다). `base` 를 주면 지금 형상을 다시 만들지
    않는다. 지금 형상이 안 만들어지면 그 예외가 그대로 나간다 — 부르는 쪽이 사람 말로 바꾼다.

    답: `{"face_count", "dims": [...]}`. 줄마다 `name` · `value` · `status`(`dimension` ·
    `moved` · `unused` · `failed` · `skipped`) · `kind` · `from` · `to`(치수선) · `at`(글자
    자리) · `faces`(칠할 면 번호 — 메시 순서) · `places`(같은 치수가 있는 곳 수) · `message`.
    """
    started = clock()
    values = resolve_params(raw)
    shape = base if base is not None else build(raw)
    faces = _features(shape)
    box = shape.bounding_box()
    middle = Vector(box.center())
    scale = max(1.0, float(box.diagonal))
    wanted = list(values) if names is None else names
    dims = []
    for name in wanted:
        if name not in values:
            dims.append(_row(name, None, "failed", message="도면에 없는 변수입니다."))
            continue
        if clock() - started > budget:
            dims.append(
                _row(
                    name, values[name], "skipped", message="시간이 오래 걸려 찾지 않았습니다."
                )
            )
            continue
        dims.append(_one(raw, name, values[name], build, faces, middle, scale))
    return {"face_count": len(faces), "dims": dims}


def _row(name: str, value: float | None, status: str, **rest: Any) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "status": status,
        "kind": rest.get("kind"),
        "from": rest.get("start"),
        "to": rest.get("end"),
        "at": rest.get("at"),
        "faces": rest.get("faces", []),
        "places": rest.get("places", 0),
        "message": rest.get("message"),
    }


def _one(
    raw: dict[str, Any],
    name: str,
    value: float,
    build: Callable[[dict[str, Any]], Shape],
    faces: list[_Face],
    middle: Vector,
    scale: float,
) -> dict[str, Any]:
    built_any = False
    for shift in _shifts(value):
        try:
            other = _features(build(_with(raw, name, value + shift)))
        except Exception:
            continue
        built_any = True
        moved = _unmatched(faces, other)
        fresh = _unmatched(other, faces)
        if not moved and not fresh and _signature(faces) == _signature(other):
            # 그대로다 — 정수 값이면 ±1 로 한 번 더(개수 변수는 0.05 를 버린다).
            continue
        here = _hits(faces, moved, value)
        there = _hits(other, fresh, value + shift)
        reach = 3 * abs(shift) + 0.05 * scale
        matched = [
            hit
            for hit in here
            if any(t.kind == hit.kind and (t.mid - hit.mid).length <= reach for t in there)
        ]
        if matched:
            matched.sort(key=lambda hit: (_RANK[hit.kind], -_weight(hit)))
            best = matched[0]
            ends = _ends(best, middle, scale)
            painted = sorted({i for hit in matched for i in hit.faces})[:MAX_FACES]
            return _row(
                name,
                value,
                "dimension",
                kind=best.kind,
                start=_xyz(ends[0]) if ends else None,
                end=_xyz(ends[1]) if ends else None,
                at=_xyz(best.mid if ends is None else (ends[0] + ends[1]) * 0.5),
                faces=painted,
                places=len(matched),
            )
        if not moved:
            # 면이 더해지거나 빠지기만 했다(개수) — 지금 형상에는 짚을 면이 없다.
            changed = {sig for sig in _signature(faces)} - set(_signature(other))
            touched = [one for one in faces if _signature([one])[0] in changed]
            if not touched:
                return _row(
                    name,
                    value,
                    "moved",
                    at=_xyz(middle),
                    message="형상이 바뀌지만 움직이는 면을 짚을 수 없습니다. 면이 더해지거나 "
                    "빠지는 변수(개수 등)입니다.",
                )
            moved = touched
        largest = max(moved, key=lambda one: one.area)
        return _row(
            name,
            value,
            "moved",
            at=_xyz(largest.center),
            faces=[one.index for one in moved][:MAX_FACES],
            places=len(moved),
            message="값과 같은 치수가 형상에 없어 이 변수가 움직이는 면을 표시합니다.",
        )
    if not built_any:
        return _row(
            name,
            value,
            "failed",
            message="값을 조금 바꾼 형상을 생성하지 못해 위치를 찾지 못했습니다.",
        )
    return _row(name, value, "unused", message="값을 바꾸어도 형상이 바뀌지 않습니다.")
