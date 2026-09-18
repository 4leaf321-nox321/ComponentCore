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
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

#: 한 번에 만들 수 있는 설계점 수 — 점마다 형상을 만들고 STEP 을 쓰므로 무한정 갈 수 없다.
MAX_POINTS = 200
#: 조합에 넣을 수 있는 인자 수. 격자는 곱으로 늘어난다(8개면 2단계만 해도 256).
MAX_FACTORS = 8

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

    @property
    def varying(self) -> bool:
        return self.mode != "fixed"


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
            out.append(Factor(name=name, mode="range", start=start, end=end, steps=steps))
        elif mode == "list":
            values = one.get("values") or []
            numbers = tuple(float(v) for v in values)
            if not numbers:
                raise DoeError(f"'{name}': 값 목록이 비었습니다")
            out.append(Factor(name=name, mode="list", values=numbers))
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
        return [factor.start]
    span = (factor.end - factor.start) / (factor.steps - 1)
    return [round(factor.start + span * i, 10) for i in range(factor.steps)]


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
    factors: list[Factor], *, method: Method = "factorial", samples: int = 20, seed: int = 1
) -> list[dict[str, float]]:
    """설계점 표 — 각 줄은 `{치수 이름: 값}`."""
    total = count(factors, method, samples)
    if total > MAX_POINTS:
        raise DoeError(
            f"설계점이 {total} 개입니다 — 한 번에 {MAX_POINTS} 개까지 만듭니다. "
            f"단계를 줄이거나 인자를 빼세요."
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
    return round(factor.start + unit * (factor.end - factor.start), 10)


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
