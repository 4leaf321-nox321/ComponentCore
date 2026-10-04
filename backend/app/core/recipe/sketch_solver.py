"""스케치 구속 — 점을 이어 그린 윤곽을 **치수와 관계로** 정한다.

좌표로 그린 윤곽(`polyline`)은 치수 하나를 바꾸면 그에 딸린 점을 사람이 다 옮겨야 한다.
구속 윤곽은 점의 자리를 「대충」 두고(그린 대로) 관계를 적는다 — 「이 변은 수평」 · 「이 둘은
직각」 · 「길이 = 길이」 · 「이 호는 반지름 8, 저 선에 접한다」. 풀이가 점을 **가장 덜
옮겨** 그 관계를 맞춘다. 치수 칸에 `=변수` 를 쓰면 실험계획이 그 치수를 훑는다.

풀이: 점의 좌표 전부를 미지수로 두고 구속마다 잔차(0 이 되어야 하는 값)를 세운 뒤
가우스-뉴턴으로 — 매 걸음을 최소 노름(lstsq)으로 잡아 구속이 정하지 않은 쪽은 그린 자리를
지킨다. 각 · 방향 잔차는 그림의 크기를 곱해 길이(mm)와 견준다.

맞지 않는 구속은 앞에서부터 하나씩 더해 풀어 보며 **처음 어긋나는 것**을 집어 말한다. 다
맞으면 남은 움직임(자유도 = 미지수 - 잔차 자코비안의 계수)을 알린다 — 점 하나를 고정하고
한 변의 방향을 정하면 대개 0 이 된다.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.core.recipe import schema as S

#: 잔차가 이만큼 안이면 맞았다(mm, 각은 크기를 곱한 길이).
_TOL = 1e-7
_STEPS = 80

LABELS = {
    "fix": "고정",
    "coincident": "일치",
    "horizontal": "수평",
    "vertical": "수직",
    "distance": "거리",
    "length": "길이",
    "dx": "가로 거리",
    "dy": "세로 거리",
    "angle": "각도",
    "parallel": "평행",
    "perpendicular": "직각",
    "equal": "동일 길이",
    "radius": "반지름",
    "tangent": "접선",
    "on": "선 위의 점",
    "midpoint": "중점",
    "symmetric": "대칭",
}


class SketchSolveError(ValueError):
    """사람이 읽고 고칠 수 있는 실패."""


@dataclass
class Solved:
    points: dict[str, tuple[float, float]]
    free: int
    """남은 움직임 — 0 이면 완전히 정해졌다."""


Residual = Callable[[np.ndarray], list[float]]


def solve(shape: S.ConstrainedShape) -> Solved:
    names = list(shape.points)
    where = {name: index for index, name in enumerate(names)}
    start = np.array([coord for name in names for coord in shape.points[name]], dtype=float)
    span = float(np.ptp(start.reshape(-1, 2), axis=0).max()) or 1.0
    residuals = [
        _residual(shape, index, one, where, start, span)
        for index, one in enumerate(_implicit(shape) + list(shape.constraints))
    ]
    implicit = len(_implicit(shape))
    solved, miss = _gauss_newton(start, residuals)
    if miss > _TOL * span * 10:
        culprit = _first_conflict(start, residuals, implicit, span)
        one = shape.constraints[culprit]
        label = LABELS[one.type]
        raise SketchSolveError(
            f"구속 {culprit + 1}({label}): "
            + ("만족할 수 없습니다" if culprit == 0 else "이전 구속과 충돌합니다")
            + f"(오차 {_conflict_size(start, residuals[: implicit + culprit + 1]):.3g})."
        )
    jacobian = _jacobian(solved, residuals)
    rank = int(np.linalg.matrix_rank(jacobian, tol=1e-6)) if jacobian.size else 0
    points = {
        name: (float(solved[2 * i]), float(solved[2 * i + 1])) for i, name in enumerate(names)
    }
    return Solved(points=points, free=len(start) - rank)


def _implicit(shape: S.ConstrainedShape) -> list[S.SketchConstraint]:
    """호의 두 끝은 중심에서 같은 거리 — 사람이 적지 않아도 늘 걸린다."""
    return [
        S.SketchConstraint(type="radius", segments=[index], value=None)
        for index, segment in enumerate(shape.segments)
        if segment.center is not None
    ]


def _cross(u: np.ndarray, v: np.ndarray) -> float:
    """평면 두 벡터의 외적(z)."""
    return float(u[0] * v[1] - u[1] * v[0])


def _gauss_newton(start: np.ndarray, residuals: list[Residual]) -> tuple[np.ndarray, float]:
    x = start.copy()
    for _ in range(_STEPS):
        values = _values(x, residuals)
        miss = float(np.abs(values).max()) if values.size else 0.0
        if miss < _TOL:
            return x, miss
        jacobian = _jacobian(x, residuals)
        step = np.linalg.lstsq(jacobian, -values, rcond=None)[0]
        # 되돌아가며 줄인다 — 한 걸음에 잔차가 커지면 반으로.
        scale = 1.0
        before = float(np.linalg.norm(values))
        while scale > 1e-4:
            trial = x + scale * step
            if float(np.linalg.norm(_values(trial, residuals))) < before:
                x = trial
                break
            scale /= 2
        else:
            break
    values = _values(x, residuals)
    return x, float(np.abs(values).max()) if values.size else 0.0


def _values(x: np.ndarray, residuals: list[Residual]) -> np.ndarray:
    return np.array([value for one in residuals for value in one(x)], dtype=float)


def _jacobian(x: np.ndarray, residuals: list[Residual]) -> np.ndarray:
    """중앙 차분 — 미지수가 많아야 수십 개다."""
    base = _values(x, residuals)
    out = np.zeros((len(base), len(x)))
    for column in range(len(x)):
        h = 1e-6 * (1.0 + abs(x[column]))
        plus, minus = x.copy(), x.copy()
        plus[column] += h
        minus[column] -= h
        out[:, column] = (_values(plus, residuals) - _values(minus, residuals)) / (2 * h)
    return out


def _first_conflict(
    start: np.ndarray, residuals: list[Residual], implicit: int, span: float
) -> int:
    """앞에서부터 하나씩 더해 풀어 본다 — 처음 안 풀리는 구속의 번호(사람이 적은 것 기준)."""
    for count in range(1, len(residuals) - implicit + 1):
        _, miss = _gauss_newton(start, residuals[: implicit + count])
        if miss > _TOL * span * 10:
            return count - 1
    return len(residuals) - implicit - 1  # pragma: no cover — 다 풀리면 여기 안 온다


def _conflict_size(start: np.ndarray, residuals: list[Residual]) -> float:
    _, miss = _gauss_newton(start, residuals)
    return miss


# --- 구속마다의 잔차 --------------------------------------------------------------


def _residual(
    shape: S.ConstrainedShape,
    index: int,
    one: S.SketchConstraint,
    where: dict[str, int],
    start: np.ndarray,
    span: float,
) -> Residual:
    def p(x: np.ndarray, name: str) -> np.ndarray:
        i = where[name]
        return x[2 * i : 2 * i + 2]

    def ends(x: np.ndarray, segment: int) -> tuple[np.ndarray, np.ndarray]:
        one = shape.segments[segment]
        return p(x, one.start), p(x, one.end)

    def direction(x: np.ndarray, segment: int) -> np.ndarray:
        a, b = ends(x, segment)
        return b - a

    def center(x: np.ndarray, segment: int) -> np.ndarray:
        name = shape.segments[segment].center
        assert name is not None
        return p(x, name)

    def unit_cross(u: np.ndarray, v: np.ndarray) -> float:
        return float(u[0] * v[1] - u[1] * v[0]) / (
            float(np.linalg.norm(u) * np.linalg.norm(v)) or 1.0
        )

    def unit_dot(u: np.ndarray, v: np.ndarray) -> float:
        return float(u @ v) / (float(np.linalg.norm(u) * np.linalg.norm(v)) or 1.0)

    kind = one.type
    pts, segs, value = one.points, one.segments, one.value
    if kind == "fix":
        target = np.array(
            one.at if one.at is not None else start[2 * where[pts[0]] : 2 * where[pts[0]] + 2]
        )
        return lambda x: list(p(x, pts[0]) - target)
    if kind == "coincident":
        return lambda x: list(p(x, pts[0]) - p(x, pts[1]))
    if kind in ("horizontal", "vertical"):
        axis = 1 if kind == "horizontal" else 0
        if segs:
            return lambda x: [float(direction(x, segs[0])[axis])]
        return lambda x: [float((p(x, pts[1]) - p(x, pts[0]))[axis])]
    if kind == "distance":
        assert value is not None
        return lambda x: [float(np.linalg.norm(p(x, pts[1]) - p(x, pts[0]))) - value]
    if kind == "length":
        assert value is not None
        return lambda x: [float(np.linalg.norm(direction(x, segs[0]))) - value]
    if kind in ("dx", "dy"):
        assert value is not None
        axis = 0 if kind == "dx" else 1
        return lambda x: [float((p(x, pts[1]) - p(x, pts[0]))[axis]) - value]
    if kind == "angle":
        assert value is not None
        # 두 **선** 사이의 각 — 구간의 방향(어느 끝에서 그렸나)은 묻지 않는다. 사람은 「60°」
        # 라고만 적으니, ±θ · ±(180-θ) 중 그린 모양에 가장 가까운 것으로 맞춘다.
        u0, v0 = direction(start, segs[0]), direction(start, segs[1])
        drawn = math.atan2(unit_cross(u0, v0), unit_dot(u0, v0))
        candidates = [math.radians(one) for one in (value, -value, 180 - value, value - 180)]
        theta = min(candidates, key=lambda one: abs(math.remainder(one - drawn, 2 * math.pi)))
        return lambda x: [
            span
            * (
                unit_cross(direction(x, segs[0]), direction(x, segs[1])) * math.cos(theta)
                - unit_dot(direction(x, segs[0]), direction(x, segs[1])) * math.sin(theta)
            )
        ]
    if kind == "parallel":
        return lambda x: [span * unit_cross(direction(x, segs[0]), direction(x, segs[1]))]
    if kind == "perpendicular":
        return lambda x: [span * unit_dot(direction(x, segs[0]), direction(x, segs[1]))]
    if kind == "equal":
        first, second = (shape.segments[one] for one in segs)
        if (first.center is None) != (second.center is None):
            raise SketchSolveError(
                f"구속 {index + 1}(동일 길이): 선은 선끼리, 호는 호끼리만 지정할 수 있습니다."
            )
        if first.center is None:
            return lambda x: [
                float(
                    np.linalg.norm(direction(x, segs[0]))
                    - np.linalg.norm(direction(x, segs[1]))
                )
            ]
        return lambda x: [
            float(
                np.linalg.norm(ends(x, segs[0])[0] - center(x, segs[0]))
                - np.linalg.norm(ends(x, segs[1])[0] - center(x, segs[1]))
            )
        ]
    if kind == "radius":
        if value is None:  # 호의 두 끝이 중심에서 같은 거리(저절로 거는 것)
            return lambda x: [
                float(
                    np.linalg.norm(ends(x, segs[0])[1] - center(x, segs[0]))
                    - np.linalg.norm(ends(x, segs[0])[0] - center(x, segs[0]))
                )
            ]
        return lambda x: [
            float(np.linalg.norm(ends(x, segs[0])[0] - center(x, segs[0]))) - value
        ]
    if kind == "tangent":
        return _tangent(shape, index, start, segs, p, ends, direction, center)
    if kind == "on":
        segment = shape.segments[segs[0]]
        if segment.center is None:
            return lambda x: [
                float(
                    _cross(direction(x, segs[0]), p(x, pts[0]) - ends(x, segs[0])[0])
                    / (np.linalg.norm(direction(x, segs[0])) or 1.0)
                )
            ]
        return lambda x: [
            float(
                np.linalg.norm(p(x, pts[0]) - center(x, segs[0]))
                - np.linalg.norm(ends(x, segs[0])[0] - center(x, segs[0]))
            )
        ]
    if kind == "midpoint":
        return lambda x: list(p(x, pts[0]) - (ends(x, segs[0])[0] + ends(x, segs[0])[1]) / 2)
    if kind == "symmetric":

        def mirrored(x: np.ndarray) -> list[float]:
            a, b = ends(x, segs[0])
            axis = b - a
            middle = (p(x, pts[0]) + p(x, pts[1])) / 2
            across = p(x, pts[1]) - p(x, pts[0])
            return [
                float(_cross(axis, middle - a) / (np.linalg.norm(axis) or 1.0)),
                float(across @ axis / (np.linalg.norm(axis) or 1.0)),
            ]

        return mirrored
    raise SketchSolveError(  # pragma: no cover
        f"구속 {index + 1}: 알 수 없는 종류입니다({kind})."
    )


def _tangent(
    shape: S.ConstrainedShape,
    index: int,
    start_x: np.ndarray,
    segs: list[int],
    p: Callable[[np.ndarray, str], np.ndarray],
    ends: Callable[[np.ndarray, int], tuple[np.ndarray, np.ndarray]],
    direction: Callable[[np.ndarray, int], np.ndarray],
    center: Callable[[np.ndarray, int], np.ndarray],
) -> Residual:
    """선과 호(원) — 중심에서 선까지의 거리 = 반지름. 호와 호 — 중심 사이 = 반지름의 합 또는
    차(그린 쪽)."""
    first, second = (shape.segments[one] for one in segs)
    if first.center is None and second.center is None:
        raise SketchSolveError(f"구속 {index + 1}(접선): 둘 중 하나는 호여야 합니다.")
    shared = {first.start, first.end} & {second.start, second.end}
    if shared:
        # 끝을 나눠 가진 둘 — 그 점에서 반지름이 선에 수직(선과 호), 두 중심과 그 점이 한 줄
        # (호와 호). 「중심에서 선까지 = 반지름」 으로 두면 닿는 점이 겹근이라 풀이가 그 점
        # 곁에서 맴돌고 자유도를 하나 더 센다.
        name = next(iter(shared))
        if first.center is None or second.center is None:
            line, arc = (segs[0], segs[1]) if first.center is None else (segs[1], segs[0])

            def meeting(x: np.ndarray) -> list[float]:
                u = direction(x, line)
                radial = p(x, name) - center(x, arc)
                return [float(u @ radial) / (float(np.linalg.norm(u)) or 1.0)]

            return meeting

        def lined_up(x: np.ndarray) -> list[float]:
            a, b = p(x, name) - center(x, segs[0]), p(x, name) - center(x, segs[1])
            return [_cross(a, b) / (float(np.linalg.norm(b)) or 1.0)]

        return lined_up
    if first.center is None or second.center is None:
        line, arc = (segs[0], segs[1]) if first.center is None else (segs[1], segs[0])

        def touching(x: np.ndarray) -> list[float]:
            a, _ = ends(x, line)
            u = direction(x, line)
            c = center(x, arc)
            r = float(np.linalg.norm(ends(x, arc)[0] - c))
            gap = abs(float(_cross(u, c - a))) / (float(np.linalg.norm(u)) or 1.0)
            return [gap - r]

        return touching

    def radii(x: np.ndarray) -> tuple[float, float, float]:
        c1, c2 = center(x, segs[0]), center(x, segs[1])
        r1 = float(np.linalg.norm(ends(x, segs[0])[0] - c1))
        r2 = float(np.linalg.norm(ends(x, segs[1])[0] - c2))
        return float(np.linalg.norm(c2 - c1)), r1, r2

    # 밖에서 닿나(중심 사이 = r1 + r2) 안에서 닿나(= |r1 - r2|) — 그린 쪽에 가까운 것으로.
    apart, r1, r2 = radii(start_x)
    outside = abs(apart - (r1 + r2)) <= abs(apart - abs(r1 - r2))

    def kissing(x: np.ndarray) -> list[float]:
        apart, r1, r2 = radii(x)
        return [apart - (r1 + r2) if outside else apart - abs(r1 - r2)]

    return kissing
