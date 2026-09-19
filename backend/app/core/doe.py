"""실험계획(DOE) — 치수 범위에서 **설계점 표**를 만든다.

「연결부는 그대로 두고 두께 · 길이를 바꿔 가며 여러 벌 뽑는다」 가 이 모듈의 일이다. 값은
레시피의 `params` 에 들어가고, 형상 · 파일을 만드는 것은 위층(작업)이 한다 — 여기는 **숫자만**
다룬다(웹 · DB · build123d 를 모른다).

규칙은 MechanicalDesign 의 DOE 엔진에서 가져왔다:

- 인자마다 **고정 / 구간(steps) / 목록** 중 하나. 고정은 조합에 들어가지 않는다.
- **전체 조합**(격자)과 **라틴 하이퍼큐브**(LHS). LHS 는 **시드**를 저장해 같은 표를 다시
  만든다 — 「지난번 그 48개」 를 못 만들면 해석 결과와 형상을 잇지 못한다.
- 값이 없는 칸(계산 실패)은 **조건을 만족한 것으로 세지 않는다.** `Number(null) == 0` 으로
  걸러져 실패한 점이 「무게 5 kg 이하」 에 들어가는 일이 실제로 있었다.
- 값은 인자의 **가공 단위**(`resolution`, 기본 0.1 mm)로 맞춘다. 구간을 셋으로 나누면
  0.333… 이 나오는데 그런 치수는 가공할 수 없다 — 0.3 으로 맞추고, 겹치는 값은 하나로.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

#: 한 번에 만들 수 있는 설계점 수의 **기본값** — 점마다 형상을 만들고 STEP 을 쓰므로 무한정
#: 갈 수 없다. 서버는 설정 `DOE_MAX_POINTS` 로 바꾼다(`config.Settings.doe_max_points`).
MAX_POINTS = 200
#: 조합에 넣을 수 있는 인자 수. 격자는 곱으로 늘어난다(8개면 2단계만 해도 256).
MAX_FACTORS = 8
#: 값을 맞추는 가공 단위의 기본값(mm). 0.1 이면 6.333 은 6.3 이 된다.
DEFAULT_RESOLUTION = 0.1

Method = Literal["factorial", "lhs"]


class DoeError(ValueError):
    """인자 정의가 틀렸다 — 무엇이 왜인지 사람 말로."""


@dataclass(frozen=True)
class Factor:
    """인자 하나. `name` 은 레시피 `params` 의 치수 이름이다."""

    name: str
    mode: Literal["fixed", "range", "list"]
    value: float | None = None
    start: float | None = None
    end: float | None = None
    steps: int = 5
    values: tuple[float, ...] = ()
    resolution: float = DEFAULT_RESOLUTION
    """값을 이 단위의 배수로 맞춘다 — 가공할 수 있는 치수만 내려고."""

    @property
    def varying(self) -> bool:
        return self.mode != "fixed"


def snap(value: float, resolution: float) -> float:
    """`value` 를 `resolution` 의 배수로. 0.1 단위면 6.333 → 6.3, 6.35 → 6.4(반올림)."""
    if resolution <= 0:
        return value
    # 6.35 / 0.1 은 63.4999… 로 나온다 — 자릿수를 한 번 다듬고 **반올림(half-up)** 한다.
    # round() 는 짝수로 가는 은행 반올림이라 6.35 가 6.3 이 된다.
    quotient = round(value / resolution, 9)
    return round(math.floor(quotient + 0.5) * resolution, 10)


def _resolution(one: dict[str, Any], name: str) -> float:
    raw = one.get("resolution")
    if raw is None or raw == "":
        return DEFAULT_RESOLUTION
    try:
        got = float(raw)
    except (TypeError, ValueError) as failure:
        raise DoeError(f"'{name}': 가공 단위가 숫자가 아닙니다") from failure
    if got <= 0:
        raise DoeError(f"'{name}': 가공 단위는 0 보다 커야 합니다")
    return got


def parse_factors(raw: list[dict[str, Any]]) -> list[Factor]:
    """화면 · AI 가 준 인자 정의를 읽는다. 틀린 곳은 이름을 짚어 말한다."""
    if not raw:
        raise DoeError("인자가 없습니다 — 바꿔 볼 치수를 적어도 하나 고르세요")
    out: list[Factor] = []
    seen: set[str] = set()
    for one in raw:
        name = str(one.get("name", "")).strip()
        if not name:
            raise DoeError("이름 없는 인자가 있습니다")
        if name in seen:
            raise DoeError(f"인자 '{name}' 이 두 번 있습니다")
        seen.add(name)
        mode = one.get("mode", "fixed")
        resolution = _resolution(one, name)
        if mode == "fixed":
            out.append(Factor(name=name, mode="fixed", value=_number(one, "value", name)))
        elif mode == "range":
            start = _number(one, "start", name)
            end = _number(one, "end", name)
            steps = int(one.get("steps", 5) or 1)
            if steps < 1:
                raise DoeError(f"'{name}': 단계 수는 1 이상입니다")
            if steps > 1 and start == end:
                raise DoeError(f"'{name}': 시작과 끝이 같은데 단계가 {steps} 입니다")
            out.append(
                Factor(
                    name=name,
                    mode="range",
                    start=start,
                    end=end,
                    steps=steps,
                    resolution=resolution,
                )
            )
        elif mode == "list":
            values = one.get("values") or []
            numbers = tuple(snap(float(v), resolution) for v in values)
            if not numbers:
                raise DoeError(f"'{name}': 값 목록이 비었습니다")
            out.append(Factor(name=name, mode="list", values=numbers, resolution=resolution))
        else:
            raise DoeError(f"'{name}': 모르는 방식입니다 — fixed · range · list 중 하나")
    varying = [f for f in out if f.varying]
    if not varying:
        raise DoeError("모두 고정입니다 — 바꿔 볼 치수를 하나는 두세요")
    if len(varying) > MAX_FACTORS:
        raise DoeError(f"바꿀 인자는 {MAX_FACTORS} 개까지입니다 (지금 {len(varying)} 개)")
    return out


def _number(one: dict[str, Any], key: str, name: str) -> float:
    try:
        return float(one[key])
    except (KeyError, TypeError, ValueError) as failure:
        raise DoeError(f"'{name}': {key} 가 숫자가 아닙니다") from failure


def levels(factor: Factor) -> list[float]:
    """이 인자가 가지는 값들. 고정이면 하나."""
    if factor.mode == "fixed":
        assert factor.value is not None
        return [factor.value]
    if factor.mode == "list":
        return list(factor.values)
    assert factor.start is not None and factor.end is not None
    if factor.steps == 1:
        return [snap(factor.start, factor.resolution)]
    span = (factor.end - factor.start) / (factor.steps - 1)
    out: list[float] = []
    for i in range(factor.steps):
        value = snap(factor.start + span * i, factor.resolution)
        # 단위로 맞추다 보면 이웃이 같은 값이 된다(0.1 단위로 6~6.2 를 5단계) — 하나만 남긴다.
        if not out or out[-1] != value:
            out.append(value)
    return out


def count(factors: list[Factor], method: Method, samples: int) -> int:
    """실행 **전에** 몇 개인지. 격자는 곱으로 늘어나므로 먼저 보여 주고 시작한다."""
    if method == "lhs":
        return max(1, int(samples))
    total = 1
    for factor in factors:
        total *= len(levels(factor))
    return total


def seeded_random(seed: int) -> Callable[[], float]:
    """같은 시드 = 같은 표. 선형 합동 생성기(LCG) — 참조 구현과 같은 수를 낸다."""
    state = seed & 0xFFFFFFFF or 1

    def next_value() -> float:
        nonlocal state
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        return state / 0x100000000

    return next_value


def latin_hypercube(dimensions: int, samples: int, seed: int) -> list[list[float]]:
    """각 인자의 [0,1) 을 표본 수만큼 나눠 칸마다 하나씩 뽑고, 인자별로 섞는다."""
    rng = seeded_random(seed)
    columns: list[list[float]] = []
    for _ in range(dimensions):
        column = [(i + rng()) / samples for i in range(samples)]
        for i in range(len(column) - 1, 0, -1):
            j = int(rng() * (i + 1))
            column[i], column[j] = column[j], column[i]
        columns.append(column)
    return [[columns[d][i] for d in range(dimensions)] for i in range(samples)]


def build_points(
    factors: list[Factor],
    *,
    method: Method = "factorial",
    samples: int = 20,
    seed: int = 1,
    limit: int = MAX_POINTS,
) -> list[dict[str, float]]:
    """설계점 표 — 각 줄은 `{치수 이름: 값}`. `limit` 는 서버 설정(DOE_MAX_POINTS)이 정한다."""
    total = count(factors, method, samples)
    if total > limit:
        raise DoeError(
            f"설계점이 {total} 개입니다 — 한 번에 {limit} 개까지 만듭니다. "
            f"단계를 줄이거나 인자를 빼거나, LHS 로 표본 수를 정하세요."
        )
    fixed = {f.name: levels(f)[0] for f in factors if not f.varying}
    varying = [f for f in factors if f.varying]
    if method == "lhs":
        matrix = latin_hypercube(len(varying), max(1, int(samples)), seed)
        rows = []
        for sample in matrix:
            row = dict(fixed)
            for factor, unit in zip(varying, sample, strict=True):
                row[factor.name] = _map_unit(factor, unit)
            rows.append(row)
        return rows
    rows = [dict(fixed)]
    for factor in varying:
        rows = [{**row, factor.name: value} for row in rows for value in levels(factor)]
    return rows


def _map_unit(factor: Factor, unit: float) -> float:
    """[0,1) 값을 인자의 범위로. 목록 인자는 칸을 고른다."""
    if factor.mode == "list":
        index = min(len(factor.values) - 1, int(unit * len(factor.values)))
        return factor.values[index]
    assert factor.start is not None and factor.end is not None
    return snap(factor.start + unit * (factor.end - factor.start), factor.resolution)


# --- 걸러 보기 -------------------------------------------------------------------

#: 설계 조건은 대개 부등식이다 — 「200 이하」 「안전율 1.5 이상」.
OPERATORS = ("lte", "gte", "between", "eq")
#: `eq` 로 실수를 견줄 때의 허용 오차(크기에 비례) — 격자 값은 곱셈이라 끝자리가 흔들린다.
_RELATIVE_TOLERANCE = 1e-9


def passes(
    values: dict[str, Any], conditions: list[dict[str, Any]]
) -> tuple[bool, str | None]:
    """조건을 모두 만족하나. 아니면 **어느 조건에서 걸렸는지**도 돌려준다.

    값이 없거나 숫자가 아니면 **만족하지 않은 것**으로 본다 — 계산이 실패한 점이 조건을
    통과해 표에 정상처럼 남으면 안 된다."""
    for condition in conditions:
        key = str(condition.get("key", ""))
        operator = condition.get("op", "lte")
        got = _as_number(values.get(key))
        if got is None:
            return False, f"{key}: 값이 없습니다"
        first = _as_number(condition.get("value"))
        if first is None:
            continue  # 비어 있는 줄은 무시한다 — 쓰다 만 조건까지 거르면 표가 사라진다
        if operator == "lte" and got > first:
            return False, f"{key} {got} > {first}"
        if operator == "gte" and got < first:
            return False, f"{key} {got} < {first}"
        if operator == "eq" and abs(got - first) > max(abs(first), 1.0) * _RELATIVE_TOLERANCE:
            return False, f"{key} {got} ≠ {first}"
        if operator == "between":
            second = _as_number(condition.get("value2"))
            if second is None:
                continue
            low, high = min(first, second), max(first, second)
            if not (low <= got <= high):
                return False, f"{key} {got} 이 {low}~{high} 밖"
    return True, None


def _as_number(value: Any) -> float | None:
    """빈 값 · 글자는 **0 이 아니라 없음**이다."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


# --- 맞서는 목표 고르기 -----------------------------------------------------------

#: 목표의 방향 — 작을수록 · 클수록 · 목표값에 가까울수록.
GOALS = ("min", "max", "target")


class Objective:
    """무엇을 어느 쪽으로 좋게 볼 것인가.

    지그에서는 목표가 늘 맞선다: 두께를 키우면 공진은 올라가지만 질량이 는다. **한 값으로
    합치지 않는다** — 가중치를 묻는 순간 답이 그 가중치의 것이 되고, 사람은 자기가 무엇을
    골랐는지 모르게 된다. 대신 **아무한테도 지지 않는 점**(파레토)만 남겨 준다.
    """

    __slots__ = ("goal", "key", "target")

    def __init__(self, key: str, goal: str = "min", target: float | None = None) -> None:
        if goal not in GOALS:
            raise DoeError(f"'{key}': 목표는 {' · '.join(GOALS)} 중 하나입니다")
        if goal == "target" and target is None:
            raise DoeError(f"'{key}': 「목표값에 가깝게」 는 목표값이 있어야 합니다")
        self.key = key
        self.goal = goal
        self.target = target

    def cost(self, value: float) -> float:
        """**작을수록 좋은 값**으로 바꾼다 — 방향이 섞이면 견줄 수 없다."""
        if self.goal == "max":
            return -value
        if self.goal == "target":
            assert self.target is not None
            return abs(value - self.target)
        return value


def parse_objectives(raw: list[dict[str, Any]]) -> list[Objective]:
    if not raw:
        raise DoeError("목표가 없습니다 — 무엇을 좋게 볼지 하나는 고르세요")
    if len(raw) > 4:
        raise DoeError("목표는 넷까지입니다 — 그보다 많으면 거의 모든 점이 파레토가 됩니다")
    return [
        Objective(
            key=str(one.get("key", "")),
            goal=str(one.get("goal", "min")),
            target=None if one.get("target") is None else float(one["target"]),
        )
        for one in raw
    ]


def _dominates(a: list[float], b: list[float]) -> bool:
    """a 가 b 를 이긴다 = 모든 목표에서 뒤지지 않고, 적어도 하나에서 낫다."""
    return all(x <= y for x, y in zip(a, b, strict=True)) and any(
        x < y for x, y in zip(a, b, strict=True)
    )


def pareto(rows: list[dict[str, Any]], objectives: list[Objective]) -> list[dict[str, Any]]:
    """설계점마다 **파레토인지**와 목표별 값 · 참고 점수를 붙여 돌려준다.

    파레토(비열등) = 모든 목표에서 이 점보다 나은 점이 없다. 「두께 8이 두께 10보다 가볍고
    공진도 목표에 가깝다」 면 두께 10 은 볼 필요가 없다 — 그런 점을 걸러 내는 일이다.

    값이 없는 점(계산 실패)은 견줄 수 없으므로 **파레토에 들지 않는다**(빠뜨리지도 않는다 —
    `comparable: false` 로 남는다)."""
    costs: list[list[float] | None] = []
    for row in rows:
        values = [_as_number(row.get(one.key)) for one in objectives]
        if any(value is None for value in values):
            costs.append(None)
        else:
            numbers = [value for value in values if value is not None]
            costs.append(
                [one.cost(value) for one, value in zip(objectives, numbers, strict=True)]
            )

    # 점수(참고용) — 목표마다 0~1 로 펴서 더한다. 순위를 **정하는** 값이 아니라 훑는 값이다.
    spans: list[tuple[float, float]] = []
    for index in range(len(objectives)):
        got = [cost[index] for cost in costs if cost is not None]
        spans.append((min(got), max(got)) if got else (0.0, 0.0))

    out: list[dict[str, Any]] = []
    for row, cost in zip(rows, costs, strict=True):
        if cost is None:
            out.append({**row, "comparable": False, "pareto": False, "score": None})
            continue
        beaten = any(
            other is not None and _dominates(other, cost)
            for other in costs
            if other is not cost
        )
        score = 0.0
        for index, value in enumerate(cost):
            low, high = spans[index]
            score += 0.0 if high == low else (value - low) / (high - low)
        out.append(
            {
                **row,
                "comparable": True,
                "pareto": not beaten,
                "score": round(score / len(objectives), 4),
            }
        )
    return out
