"""조립 구속(mate) — 구성품을 **숫자 대신 관계로** 놓는다.

「이 바닥면을 지그 윗면에 맞대고, 이 구멍을 저 핀과 동심으로」. 자리 · 회전을 손으로 맞춰
두면 지그 높이가 실험계획으로 바뀌는 순간 부품이 허공에 뜨거나 파묻힌다. 구속은 설계점마다
다시 풀린다 — 면 · 축을 질의(`recipe_find` 와 같은 말)로 가리키니 치수가 바뀌어도 그 면을
따라간다.

풀이는 두 단계, 적은 차례대로:

1. **방향** — 맞대기 · 면 맞춤 · 동심 · 평행은 「이 방향을 저 방향에」(회전 둘을 정한다),
   직각 · 각도는 「두 방향 사이의 각」(하나). 첫 정렬은 가장 작은 회전으로, 다음 것은 앞에서
   정한 방향을 축으로 돌려서 맞춘다 — 손으로 놓은 자리(translate · rotate)에서 가장 덜 돈다.
   남은 어긋남은 가우스-뉴턴으로 다듬는다.
2. **위치** — 방향이 정해지면 위치 조건은 일차식이다(면 사이 거리 · 축이 겹침). 최소 이동(최소
   노름 최소제곱)으로 푼다. 구속이 정하지 않은 쪽은 손으로 놓은 자리 그대로라, 끌어 옮기면
   남은 방향으로만 미끄러진다. 회전은 구성품의 가운데를 중심으로 — 원점이 멀리 있는 도면이
   돌다가 엉뚱한 데로 날아가지 않게.

구속끼리 맞지 않으면(평행한 두 면에 서로 다른 거리) 몇째 구속이 앞의 것과 어긋나는지 말한다.
구성품끼리 서로를 가리키는 고리는 없다 — 구속은 레시피에서 **앞에 놓인 것**에만 건다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from build123d import Axis, GeomType, Location, Plane, Shape
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.gp import gp_Trsf
from OCP.TopLoc import TopLoc_Location

from app.core.recipe.datums import DatumError, _picked

#: 이만큼 안 맞으면 어긋남 — 방향(라디안 · 단위 벡터 차) · 위치(mm).
_TURN_TOL = 1e-6
_MOVE_TOL = 1e-4

LABELS = {
    "touch": "맞대기",
    "flush": "면 맞춤",
    "concentric": "동심",
    "parallel": "평행",
    "perpendicular": "직각",
    "angle": "각도",
}


class MateError(ValueError):
    """사람이 읽고 고칠 수 있는 실패 — 평가기가 노드 id 를 붙인다."""


@dataclass(frozen=True)
class Element:
    """구속이 잡는 것 — 평면(점 · 법선) 또는 축(점 · 방향)."""

    kind: str
    point: np.ndarray
    direction: np.ndarray

    @property
    def label(self) -> str:
        return "평면" if self.kind == "plane" else "축"


@dataclass(frozen=True)
class Spec:
    """풀 구속 하나 — `this` 는 구성품 자신의 좌표, `to` 는 조립의 좌표."""

    kind: str
    this: Element
    to: Element
    offset: float = 0.0
    angle: float | None = None
    flip: bool = False


def _vec(value: Any) -> np.ndarray:
    return np.array([float(value.X), float(value.Y), float(value.Z)])


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def element(shape: Any, select: dict[str, Any]) -> Element:
    """질의가 집는 **하나**를 평면 · 축으로. 평면 → 법선, 원통 · 원뿔면 → 축, 직선 엣지 →
    그 선, 원 · 호 엣지 → 그 원의 축(구멍 테두리)."""
    try:
        what, index = _picked(shape, select, ("faces", "edges"))
    except DatumError as failure:
        raise MateError(str(failure)) from failure
    if what == "faces":
        face = shape.faces()[index]
        if face.geom_type == GeomType.PLANE:
            middle = face.center()
            return Element("plane", _vec(middle), _unit(_vec(face.normal_at(middle))))
        if face.geom_type in (GeomType.CYLINDER, GeomType.CONE):
            line = face.axis_of_rotation
            # 축 위의 점은 그 면 곁으로 — OCC 가 주는 점은 면에서 멀기도 하다
            # (`datums.make_axis`).
            middle = _vec(face.bounding_box().center())
            base, direction = _vec(line.position), _unit(_vec(line.direction))
            foot = base + direction * float(np.dot(middle - base, direction))
            return Element("axis", foot, direction)
        raise MateError(
            f"select: {face.geom_type.name.lower()} 면은 구속에 못 씁니다 — "
            "평면 · 원통면 · 원뿔면"
        )
    edge = shape.edges()[index]
    if edge.geom_type == GeomType.LINE:
        return Element("axis", _vec(edge.position_at(0)), _unit(_vec(edge.tangent_at(0))))
    if edge.geom_type == GeomType.CIRCLE:
        circle = BRepAdaptor_Curve(edge.wrapped).Circle()
        center, normal = circle.Location(), circle.Axis().Direction()
        return Element(
            "axis",
            np.array([center.X(), center.Y(), center.Z()]),
            np.array([normal.X(), normal.Y(), normal.Z()]),
        )
    raise MateError(
        f"select: {edge.geom_type.name.lower()} 엣지는 구속에 못 씁니다 — 직선 · 원 엣지"
    )


def datum_element(value: Axis | Plane) -> Element:
    if isinstance(value, Axis):
        return Element("axis", _vec(value.position), _unit(_vec(value.direction)))
    return Element("plane", _vec(value.origin), _unit(_vec(value.z_dir)))


def check_kinds(spec: Spec) -> None:
    """구속 종류와 잡은 것이 맞나 — 맞대기 · 면 맞춤은 평면끼리, 동심은 축끼리."""
    name = LABELS[spec.kind]
    if spec.kind in ("touch", "flush"):
        for side, one in (("this", spec.this), ("to", spec.to)):
            if one.kind != "plane":
                raise MateError(f"{name}는 평면끼리입니다 — {side} 가 {one.label}입니다")
    if spec.kind == "concentric":
        for side, one in (("this", spec.this), ("to", spec.to)):
            if one.kind != "axis":
                raise MateError(
                    f"{name}은 축끼리입니다(원통면 · 원 엣지) — {side} 가 {one.label}입니다"
                )


# --- 회전 -------------------------------------------------------------------------


def _cross(v: np.ndarray) -> np.ndarray:
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def _about(axis: np.ndarray, angle: float) -> np.ndarray:
    """축 둘레 회전(로드리게스)."""
    k = _cross(_unit(axis))
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * (k @ k)


def _rotvec(omega: np.ndarray) -> np.ndarray:
    angle = float(np.linalg.norm(omega))
    return np.eye(3) if angle < 1e-15 else _about(omega, angle)


def _any_normal(v: np.ndarray) -> np.ndarray:
    other = np.array([1.0, 0, 0]) if abs(v[0]) < 0.9 else np.array([0, 1.0, 0])
    return _unit(np.cross(v, other))


def _between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a 를 b 로 보내는 가장 작은 회전."""
    axis = np.cross(a, b)
    sine, cosine = float(np.linalg.norm(axis)), float(np.dot(a, b))
    if sine < 1e-12:
        return np.eye(3) if cosine > 0 else _about(_any_normal(a), math.pi)
    return _about(axis, math.atan2(sine, cosine))


def _turn_for(axis: np.ndarray, x: np.ndarray, y: np.ndarray, target: float) -> float | None:
    """`axis` 둘레로 φ 돌려 (R_φ x)·y = target 이 되는 가장 작은 φ. 못 하면 None."""
    f = _unit(axis)
    k = float(np.dot(f, x) * np.dot(f, y))
    a = float(np.dot(x, y)) - k
    b = float(np.dot(np.cross(f, x), y))
    reach = math.hypot(a, b)
    if reach < 1e-12:
        return 0.0 if abs(target - k) < 1e-9 else None
    ratio = (target - k) / reach
    if abs(ratio) > 1 + 1e-9:
        return None
    base, spread = math.atan2(b, a), math.acos(max(-1.0, min(1.0, ratio)))
    options = [base + spread, base - spread]
    return min(options, key=lambda phi: abs(math.remainder(phi, 2 * math.pi)))


@dataclass
class _Rule:
    """방향 조건 — `align`(R·u = v) 또는 `angle`((R·u)·v = cos). `sign` 이 None 이면 정렬의
    방향(같은 쪽 · 반대쪽)을 처음 쓸 때 가까운 쪽으로 정하고, `flip` 이면 그 반대로."""

    index: int
    kind: str
    u: np.ndarray
    v: np.ndarray
    cos: float = 1.0
    sign: float | None = 1.0
    flip: bool = False

    def target(self, current: np.ndarray) -> np.ndarray:
        if self.sign is None:
            self.sign = 1.0 if float(np.dot(current, self.v)) >= 0 else -1.0
            if self.flip:
                self.sign = -self.sign
        return self.sign * self.v


def _rules(specs: list[Spec]) -> list[_Rule]:
    out: list[_Rule] = []
    for index, spec in enumerate(specs):
        u, v = spec.this.direction, spec.to.direction
        if spec.kind == "touch":
            out.append(_Rule(index, "align", u, -v))
        elif spec.kind == "flush":
            out.append(_Rule(index, "align", u, v))
        elif spec.kind in ("concentric", "parallel"):
            out.append(_Rule(index, "align", u, v, sign=None, flip=spec.flip))
        elif spec.kind == "perpendicular":
            out.append(_Rule(index, "angle", u, v, cos=0.0))
        else:
            angle = float(spec.angle or 0.0)
            if angle < 1e-6 or angle > 180 - 1e-6:
                # 0° · 180° 는 평행이다 — 각 조건으로 두면 회전 하나만 막는 것처럼 센다.
                out.append(_Rule(index, "align", u, v if angle < 90 else -v))
            else:
                out.append(_Rule(index, "angle", u, v, cos=math.cos(math.radians(angle))))
    return out


def _residual(rotation: np.ndarray, rules: list[_Rule]) -> tuple[np.ndarray, np.ndarray]:
    values: list[float] = []
    rows: list[np.ndarray] = []
    for rule in rules:
        x = rotation @ rule.u
        if rule.kind == "align":
            values.extend(x - rule.target(x))
            rows.extend(-_cross(x))
        else:
            values.append(float(np.dot(x, rule.v)) - rule.cos)
            rows.append(np.cross(x, rule.v))
    return np.array(values), np.array(rows).reshape(-1, 3)


def _orient(rotation: np.ndarray, rules: list[_Rule]) -> np.ndarray:
    """방향 — 정렬 먼저, 각은 그다음. 앞에서 정한 것을 지키는 축(`keep`)으로만 돌린다."""
    keep: np.ndarray | None = None
    full = False
    ordered = [r for r in rules if r.kind == "align"] + [r for r in rules if r.kind == "angle"]
    for rule in ordered:
        if full:
            continue
        x = rotation @ rule.u
        if rule.kind == "align":
            want = rule.target(x)
            if keep is None:
                rotation = _between(x, want) @ rotation
                keep = want
            elif abs(abs(float(np.dot(want, keep))) - 1) > 1e-9:
                phi = _turn_for(keep, x, want, 1.0)
                if phi is not None:
                    rotation = _about(keep, phi) @ rotation
                full = True
            continue
        if keep is None:
            # 두 방향 사이를 그 각으로 — 둘이 이루는 평면 안에서 가장 덜 돌린다.
            now = math.acos(max(-1.0, min(1.0, float(np.dot(x, rule.v)))))
            hinge = np.cross(rule.v, x)
            hinge = _any_normal(rule.v) if np.linalg.norm(hinge) < 1e-12 else hinge
            rotation = _about(hinge, math.acos(rule.cos) - now) @ rotation
            keep = rule.v
        else:
            phi = _turn_for(keep, x, rule.v, rule.cos)
            if phi is not None:
                rotation = _about(keep, phi) @ rotation
            full = True
    # 남은 어긋남 — 짝이 안 맞는 조합(각 둘 등)을 가우스-뉴턴으로.
    for _ in range(60):
        values, jacobian = _residual(rotation, rules)
        if not len(values) or float(np.abs(values).max()) < 1e-13:
            break
        step = -np.linalg.lstsq(jacobian, values, rcond=None)[0]
        rotation = _rotvec(step) @ rotation
    # 수치 오차로 직교성이 흐트러지지 않게.
    left, _, right = np.linalg.svd(rotation)
    return left @ right


def _rule_error(rotation: np.ndarray, rule: _Rule) -> float:
    """어긋남(도)."""
    x = rotation @ rule.u
    if rule.kind == "align":
        want = rule.sign * rule.v if rule.sign is not None else rule.v
        return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(x, want))))))
    now = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(x, rule.v))))))
    return abs(now - math.degrees(math.acos(rule.cos)))


# --- 위치 -------------------------------------------------------------------------


def _rows(spec: Spec, rotation: np.ndarray) -> tuple[list[np.ndarray], list[float]]:
    """위치 조건 — a·t = b 꼴의 줄들. 방향만 정하는 구속은 줄이 없다."""
    moved = rotation @ spec.this.point
    if spec.kind in ("touch", "flush"):
        normal = spec.to.direction
        return [normal], [spec.offset + float(np.dot(normal, spec.to.point - moved))]
    if spec.kind == "concentric":
        a = spec.to.direction
        e1 = _any_normal(a)
        e2 = np.cross(a, e1)
        gap = spec.to.point - moved
        return [e1, e2], [float(np.dot(e1, gap)), float(np.dot(e2, gap))]
    return [], []


def _rank(matrix: np.ndarray) -> int:
    if matrix.size == 0:
        return 0
    return int(np.linalg.matrix_rank(matrix, tol=1e-9))


# --- 바깥 -------------------------------------------------------------------------


def matrix_of(location: Location) -> tuple[np.ndarray, np.ndarray]:
    trsf = location.wrapped.Transformation()
    rotation = np.array([[trsf.Value(r, c) for c in (1, 2, 3)] for r in (1, 2, 3)])
    return rotation, np.array([trsf.Value(r, 4) for r in (1, 2, 3)])


def location_of(rotation: np.ndarray, translation: np.ndarray) -> Location:
    trsf = gp_Trsf()
    r, t = rotation, translation
    trsf.SetValues(
        r[0, 0], r[0, 1], r[0, 2], t[0],
        r[1, 0], r[1, 1], r[1, 2], t[1],
        r[2, 0], r[2, 1], r[2, 2], t[2],
    )  # fmt: skip
    return Location(TopLoc_Location(trsf))


def solve(
    local: Shape, specs: list[Spec], initial: Location
) -> tuple[Location, dict[str, Any]]:
    """구성품(`local` — 가져온 도면의 좌표)을 구속대로 놓을 자리와 보고(남은 움직임)."""
    for index, spec in enumerate(specs):
        try:
            check_kinds(spec)
        except MateError as failure:
            raise MateError(f"구속 {index + 1}: {failure}") from failure
    start, moved = matrix_of(initial)
    center = _vec(local.bounding_box().center())
    anchor = start @ center + moved  # 손으로 놓은 가운데 — 돌아도 여기를 지킨다

    rules = _rules(specs)
    rotation = _orient(start, rules)
    for rule in sorted(rules, key=lambda one: one.index):
        miss = _rule_error(rotation, rule)
        if miss > math.degrees(_TURN_TOL) * 10:
            raise MateError(_conflict(specs, rule.index, f"{miss:.3g}°"))
    _, jacobian = _residual(rotation, rules)
    free_rotation = 3 - _rank(jacobian)

    translation = anchor - rotation @ center
    lines: list[np.ndarray] = []
    values: list[float] = []
    owner: list[int] = []
    for index, spec in enumerate(specs):
        rows, rhs = _rows(spec, rotation)
        lines.extend(rows)
        values.extend(rhs)
        owner.extend([index] * len(rows))
    if lines:
        a, b = np.array(lines), np.array(values)
        # 앞의 것부터 차례로 — 처음 어긋나는 구속을 집어 말한다. 앞의 것은 무겁게 지켜서
        # 어긋남이 둘로 나뉘지 않고 새 구속에 다 실리게(3 mm 어긋난 것을 1.5 로 말하지 않게).
        for upto in sorted(set(owner)):
            take = [i for i, who in enumerate(owner) if who <= upto]
            weight = np.array([1.0 if owner[i] == upto else 1e6 for i in take])
            sub_a, sub_b = a[take], b[take]
            step = np.linalg.lstsq(
                sub_a * weight[:, None], (sub_b - sub_a @ translation) * weight, rcond=None
            )[0]
            miss = float(np.abs(sub_a @ (translation + step) - sub_b).max())
            if miss > _MOVE_TOL:
                raise MateError(_conflict(specs, upto, f"{miss:.3g} mm"))
        translation = translation + np.linalg.lstsq(a, b - a @ translation, rcond=None)[0]
    free_translation = 3 - _rank(np.array(lines)) if lines else 3

    report = {
        "mates": len(specs),
        "free_rotation": free_rotation,
        "free_translation": free_translation,
    }
    return location_of(rotation, translation), report


def _conflict(specs: list[Spec], index: int, miss: str) -> str:
    name = LABELS[specs[index].kind]
    if index == 0:
        return f"구속 1({name}) — 맞출 수 없습니다, {miss} 어긋남"
    return f"구속 {index + 1}({name}) — 앞의 구속과 맞지 않습니다, {miss} 어긋남"


def placement(location: Location, report: dict[str, Any] | None = None) -> dict[str, Any]:
    """요약에 싣는 자리 — 화면이 3D 에서 고른 점을 구성품의 좌표로 되돌릴 때 쓴다."""
    rotation, translation = matrix_of(location)
    out: dict[str, Any] = {
        "rotation": [[round(float(v), 9) for v in row] for row in rotation],
        "translation": [round(float(v), 6) for v in translation],
    }
    if report:
        out.update(report)
    return out
