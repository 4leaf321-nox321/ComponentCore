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
- **제약식**(`constraints`) — `구멍_간격 > 2 * 구멍_지름` 처럼 변수끼리의 조건. 범위만으로는
  말이 안 되는 조합(벽이 구멍보다 얇은 판)이 만들어져, CAD 에서 깨지거나 **멀쩡해 보이는
  이상한 형상**이 해석으로 나간다. 만들기 **전에** 거른다: 격자는 어긋난 줄을 빼고, LHS 는
  표본 수가 찰 때까지 더 큰 표에서 뽑는다(`plan`). 식을 푸는 것(도면의 다른 치수까지)은
  위층이 준다.
- **치수가 아닌 인자** 셋 — 값이 레시피 `params` 로 가지 않는다(형상은 그대로다). 실제로
  조건에 적용하는 것은 위층이 한다(`NON_SHAPE`).
  - 재료(`material`): 바디(`bodies`)에 붙일 재료를 후보(`values`, 조건에 담아 둔 재료의
    이름 · 번호) 중에서.
  - 고르기(`choice`): 조건의 **고르는 칸 하나**(`target` = 묶음 · 항목 · 칸 — 접촉 종류, 구속
    종류, 해석 종류, 선택 그룹 …)를 후보(`values`) 중에서.
  - 배율(`scale`): 바디(`bodies`)에 붙은 재료의 **물성 하나**(`property` — 「탄성계수」 ·
    표준 열쇠 · 밀도 · 푸아송비)에 곱할 수(`values`). 원본 값은 그대로 두고 옮긴 값에만 곱한다.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

#: 한 번에 만들 수 있는 설계점 수의 **기본값** — 점마다 형상을 만들고 STEP 을 쓰므로 무한정
#: 갈 수 없다. 서버는 설정 `DOE_MAX_POINTS` 로 바꾼다(`config.Settings.doe_max_points`).
MAX_POINTS = 200
#: 조합에 넣을 수 있는 인자 수. 격자는 곱으로 늘어난다(8개면 2단계만 해도 256).
MAX_FACTORS = 8
#: 값을 맞추는 가공 단위의 기본값(mm). 0.1 이면 6.333 은 6.3 이 된다.
DEFAULT_RESOLUTION = 0.1
#: 제약식 수의 상한 — 사람이 읽을 수 있는 만큼.
MAX_CONSTRAINTS = 20
#: 제약으로 거를 때 **훑어볼** 격자 줄 수의 상한. 거르려면 다 세어 봐야 해서 끝이 있어야
#: 한다.
GRID_CAP = 100_000
#: LHS 가 표본 수를 채우려고 키워 보는 후보 표의 상한.
LHS_CAP = 20_000
#: 화면이 흩뿌림에 그릴 걸러진 후보의 수 — 다 보내면 무겁다.
REJECTED_SHOWN = 300

Method = Literal["factorial", "lhs", "table", "oat", "ccd", "bbd", "sobol"]
"""- `table` — 설계점을 **직접 준 표**(CSV · 해석 쪽 최적화기가 고른 점)로. 가공 단위로 맞추지
  않는다 — 표의 값이 곧 원하는 값이다.
- `oat` — 하나씩 바꾸기: 가운데 한 점에서 변수마다 제 값들을 하나씩(나머지는 가운데). 어느
  변수가 중요한지 먼저 고를 때.
- `ccd` — 중심 합성(면 중심, CCF): 모서리 2^k + 축 2k + 가운데. 범위 밖으로 안 나간다. 해석
  쪽이 2차 응답면을 만들 때의 표준.
- `bbd` — Box-Behnken: 변수 둘씩 ±1(나머지 가운데) + 가운데. 모서리(모두 끝)를 안 만든다 —
  끝끼리 겹치면 깨지는 형상에 맞다. 변수 셋 이상.
- `sobol` — Sobol 수열(시드로 디지털 이동). 나중에 점을 더해도 **이어서** 뽑아 공간이 고르게
  찬다(LHS 는 다시 뽑아야 한다)."""
#: 수 인자만 받는 방식 — 끝 · 가운데의 뜻이 있어야 한다.
CODED = ("ccd", "bbd")


class DoeError(ValueError):
    """인자 정의가 틀렸다 — 무엇이 왜인지 사람 말로."""


@dataclass(frozen=True)
class Factor:
    """인자 하나. `name` 은 레시피 `params` 의 치수 이름이다."""

    name: str
    mode: Literal["fixed", "range", "list", "material", "choice", "scale"]
    value: float | None = None
    start: float | None = None
    end: float | None = None
    steps: int = 5
    values: tuple[float, ...] = ()
    resolution: float = DEFAULT_RESOLUTION
    """값을 이 단위의 배수로 맞춘다 — 가공할 수 있는 치수만 내려고."""
    bodies: tuple[str, ...] = ()
    """재료 인자 — 재료를 바꿔 끼울 바디 이름들(단품이면 「전체」)."""
    choices: tuple[Any, ...] = ()
    """재료 · 고르기 · 배율 인자의 후보(재료 이름, 칸의 값, 곱할 수)."""
    target: tuple[str, str | int | None, str] | None = None
    """고르기 인자 — (묶음, 항목 이름 또는 1 부터의 번호, 칸)."""
    prop: str = ""
    """배율 인자 — 곱할 물성."""

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
        raise DoeError(f"‘{name}’: 가공 단위가 숫자가 아닙니다.") from failure
    if got <= 0:
        raise DoeError(f"‘{name}’: 가공 단위는 0보다 커야 합니다.")
    return got


def parse_factors(raw: list[dict[str, Any]], *, allow_fixed: bool = False) -> list[Factor]:
    """화면 · AI 가 준 인자 정의를 읽는다. 틀린 곳은 이름을 짚어 말한다. `allow_fixed` 는
    「모두 고정」 을 받는다(점을 더할 때 — 범위는 새 묶음이 준다)."""
    if not raw:
        raise DoeError("인자가 없습니다. 변경할 치수를 하나 이상 선택하십시오.")
    out: list[Factor] = []
    seen: set[str] = set()
    for one in raw:
        name = str(one.get("name", "")).strip()
        if not name:
            raise DoeError("이름이 없는 인자가 있습니다.")
        if name in seen:
            raise DoeError(f"인자 ‘{name}’이(가) 두 번 지정되었습니다.")
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
                raise DoeError(f"‘{name}’: 단계 수는 1 이상이어야 합니다.")
            if steps > 1 and start == end:
                raise DoeError(f"‘{name}’: 시작값과 끝값이 같은데 단계 수가 {steps}입니다.")
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
        elif mode == "material":
            choices = tuple(str(v).strip() for v in one.get("values") or [] if str(v).strip())
            bodies = tuple(str(v).strip() for v in one.get("bodies") or [] if str(v).strip())
            if not choices:
                raise DoeError(f"‘{name}’: 후보 재료가 없습니다.")
            if len(set(choices)) != len(choices):
                raise DoeError(f"‘{name}’: 같은 재료가 두 번 지정되었습니다.")
            if not bodies:
                raise DoeError(
                    f"‘{name}’: 재료를 교체할 바디가 없습니다(단일 부품이면 ‘전체’를 "
                    "지정하십시오)."
                )
            out.append(Factor(name=name, mode="material", bodies=bodies, choices=choices))
        elif mode == "choice":
            out.append(_choice_factor(one, name))
        elif mode == "scale":
            out.append(_scale_factor(one, name))
        elif mode == "list":
            values = one.get("values") or []
            numbers = tuple(snap(float(v), resolution) for v in values)
            if not numbers:
                raise DoeError(f"‘{name}’: 값 목록이 비어 있습니다.")
            out.append(Factor(name=name, mode="list", values=numbers, resolution=resolution))
        else:
            raise DoeError(
                f"‘{name}’: 알 수 없는 방식입니다. fixed, range, list, material, choice, "
                "scale 중 하나를 지정하십시오."
            )
    varying = [f for f in out if f.varying]
    if not varying and not allow_fixed:
        raise DoeError("모든 인자가 고정되어 있습니다. 변경할 치수를 하나 이상 지정하십시오.")
    if len(varying) > MAX_FACTORS:
        raise DoeError(
            f"변경할 인자는 최대 {MAX_FACTORS}개까지 지정할 수 있습니다"
            f"(현재 {len(varying)}개)."
        )
    return out


#: 고르기 인자가 가리킬 수 있는 조건 묶음. 해석 설정은 한 벌이라 항목이 없다.
CHOICE_GROUPS = ("constraints", "loads", "contacts", "initial", "mesh_hints", "analysis")


def _choice_factor(one: dict[str, Any], name: str) -> Factor:
    import json

    target = one.get("target") or {}
    if not isinstance(target, dict):
        raise DoeError(f"‘{name}’: target은 {{group, item, field}} 형식이어야 합니다.")
    group = str(target.get("group") or "")
    item = target.get("item")
    field = str(target.get("field") or "")
    if group not in CHOICE_GROUPS:
        raise DoeError(
            f"‘{name}’: 그룹(group)은 {', '.join(CHOICE_GROUPS)} 중 하나여야 합니다."
        )
    if not field or field == "name":
        raise DoeError(f"‘{name}’: 변경할 필드(field)가 없습니다.")
    if group != "analysis" and (item is None or item == ""):
        raise DoeError(
            f"‘{name}’: 대상 항목(item: 이름 또는 1부터 시작하는 번호)이 지정되지 않았습니다."
        )
    values = one.get("values") or []
    if not values:
        raise DoeError(f"‘{name}’: 후보 값이 없습니다.")
    if any(isinstance(v, dict | list) for v in values):
        raise DoeError(f"‘{name}’: 후보 값은 문자열, 숫자, 불리언, null 중 하나여야 합니다.")
    if len({json.dumps(v, ensure_ascii=False) for v in values}) != len(values):
        raise DoeError(f"‘{name}’: 같은 값이 두 번 지정되었습니다.")
    return Factor(
        name=name,
        mode="choice",
        choices=tuple(values),
        target=(group, None if group == "analysis" else item, field),
    )


def _scale_factor(one: dict[str, Any], name: str) -> Factor:
    prop = str(one.get("property") or "").strip()
    bodies = tuple(str(v).strip() for v in one.get("bodies") or [] if str(v).strip())
    if not prop:
        raise DoeError(f"‘{name}’: 배율을 적용할 물성(property)이 없습니다.")
    if not bodies:
        raise DoeError(
            f"‘{name}’: 물성을 변경할 바디가 없습니다(단일 부품이면 ‘전체’를 지정하십시오)."
        )
    try:
        values = tuple(float(v) for v in one.get("values") or [])
    except (TypeError, ValueError) as failure:
        raise DoeError(f"‘{name}’: 배율은 숫자여야 합니다.") from failure
    if not values:
        raise DoeError(f"‘{name}’: 배율이 없습니다.")
    if any(v <= 0 for v in values):
        raise DoeError(f"‘{name}’: 배율은 0보다 커야 합니다.")
    if len(set(values)) != len(values):
        raise DoeError(f"‘{name}’: 같은 배율이 두 번 지정되었습니다.")
    return Factor(name=name, mode="scale", bodies=bodies, choices=values, prop=prop)


def _number(one: dict[str, Any], key: str, name: str) -> float:
    try:
        return float(one[key])
    except (KeyError, TypeError, ValueError) as failure:
        raise DoeError(f"‘{name}’: {key} 값이 숫자가 아닙니다.") from failure


def levels(factor: Factor) -> list[float | str]:
    """이 인자가 가지는 값들. 고정이면 하나, 재료 인자면 후보 재료들."""
    if factor.mode in NON_SHAPE:
        return list(factor.choices)
    if factor.mode == "fixed":
        assert factor.value is not None
        return [factor.value]
    if factor.mode == "list":
        return list(factor.values)
    assert factor.start is not None and factor.end is not None
    if factor.steps == 1:
        return [snap(factor.start, factor.resolution)]
    span = (factor.end - factor.start) / (factor.steps - 1)
    out: list[float | str] = []
    for i in range(factor.steps):
        value = snap(factor.start + span * i, factor.resolution)
        # 단위로 맞추다 보면 이웃이 같은 값이 된다(0.1 단위로 6~6.2 를 5단계) — 하나만 남긴다.
        if not out or out[-1] != value:
            out.append(value)
    return out


def count(factors: list[Factor], method: Method, samples: int) -> int:
    """실행 **전에** 몇 개인지. 격자는 곱으로 늘어나므로 먼저 보여 주고 시작한다."""
    if method in ("lhs", "sobol"):
        return max(1, int(samples))
    if method in ("oat", *CODED):
        return len(designed_points(factors, method))
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
) -> list[dict[str, float | str]]:
    """설계점 표 — 각 줄은 `{치수 이름: 값}`(재료 인자는 재료 이름). `limit` 는 서버
    설정(DOE_MAX_POINTS)이 정한다."""
    total = count(factors, method, samples)
    if total > limit:
        raise DoeError(
            f"설계점이 {total}개입니다. 한 번에 최대 {limit}개까지 생성할 수 있습니다. "
            "단계 수를 줄이거나 인자를 제외하거나, LHS로 표본 수를 지정하십시오."
        )
    fixed: dict[str, float | str] = {f.name: levels(f)[0] for f in factors if not f.varying}
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


#: 설계점 한 줄 → **어긴 제약의 번호들**(0 부터). 빈 목록이면 통과다.
Check = Callable[[dict[str, float | str]], list[int]]


@dataclass
class Plan:
    """제약을 거친 설계점 표와 **얼마나 걸렀나.**"""

    rows: list[dict[str, float | str]]
    requested: int
    """방식이 낸 수 — 격자면 칸 수, LHS 면 표본 수."""
    kept: int = 0
    """제약을 지난 수 — 상한을 넘어 표를 비웠어도(`too_many`) 이것은 센다."""
    candidates: int = 0
    """실제로 훑어본 후보 수(LHS 는 표본을 채우려고 더 크게 뽑는다)."""
    next_index: int = 0
    """Sobol — 다음에 이어 뽑을 수열 번호(점을 더할 때 여기서 잇는다)."""
    rejected: int = 0
    """제약에 걸린 후보 수."""
    hits: list[int] = field(default_factory=list)
    """제약마다 걸린 후보 수 — 한 줄이 여럿에 걸릴 수 있어 합이 `rejected` 보다 클 수 있다."""
    shortfall: int = 0
    """LHS 가 끝내 못 채운 수. 0 이 아니면 제약이 너무 좁다."""
    too_many: bool = False
    """만들 수 있는 상한을 넘는다 — 표는 비어 있다(격자를 다 펼치지 않는다)."""
    rejected_rows: list[dict[str, float | str]] = field(default_factory=list)
    """걸러진 후보 몇 줄 — 화면이 흩뿌림에 옅게 그린다(`REJECTED_SHOWN` 까지)."""


def parse_constraints(raw: list[Any] | None) -> list[str]:
    """제약식 목록을 다듬는다 — 빈 줄은 버리고, 글자가 아니면 말한다. 이름이 맞는지는 위층이
    (도면의 치수를 알므로) 본다."""
    out: list[str] = []
    for one in raw or []:
        if not isinstance(one, str):
            raise DoeError("제약식은 문자열이어야 합니다(예: 간격 > 2 * 지름).")
        text = one.strip()
        if text:
            out.append(text)
    if len(out) > MAX_CONSTRAINTS:
        raise DoeError(
            f"제약식은 최대 {MAX_CONSTRAINTS}개까지 지정할 수 있습니다(현재 {len(out)}개)."
        )
    return out


def table_points(
    factors: list[Factor], table: list[dict[str, Any]]
) -> list[dict[str, float | str]]:
    """**직접 준 표**를 설계점으로 — 줄마다 바꿀 변수(고정이 아닌 인자)의 값이 다 있어야 한다.

    엑셀로 짠 표나 해석 쪽 최적화기가 「다음엔 이 점들」 이라고 고른 것을 그대로 만든다. 그래서
    **가공 단위로 맞추지 않고**(표의 값이 곧 원하는 값이다) 겹친 줄도 그대로 둔다(번호가 표의
    줄과 같아야 결과를 되짚는다). 재료 · 고르기 · 배율 인자는 후보 중 하나여야 한다."""
    if not table:
        raise DoeError("표가 비어 있습니다. 설계점을 1행 이상 입력하십시오.")
    by_name = {f.name: f for f in factors}
    fixed: dict[str, float | str] = {f.name: levels(f)[0] for f in factors if not f.varying}
    varying = [f for f in factors if f.varying]
    rows: list[dict[str, float | str]] = []
    for number, raw in enumerate(table, start=1):
        if not isinstance(raw, dict):
            raise DoeError(f"표 {number}행: 이름과 값의 쌍이어야 합니다.")
        unknown = sorted(str(k) for k in raw if k not in by_name)
        if unknown:
            raise DoeError(f"표 {number}행: 알 수 없는 변수입니다({', '.join(unknown)}).")
        stuck = sorted(str(k) for k in raw if not by_name[k].varying)
        if stuck:
            raise DoeError(
                f"표 {number}행: {', '.join(stuck)}은(는) 고정 인자입니다. 표의 값으로 "
                "변경하려면 고정을 해제하십시오."
            )
        row = dict(fixed)
        for factor in varying:
            value = raw.get(factor.name)
            if value is None or value == "":
                raise DoeError(f"표 {number}행: ‘{factor.name}’ 값이 없습니다.")
            if factor.mode in NON_SHAPE:
                match = [one for one in factor.choices if _same(one, value)]
                if not match:
                    shown = ", ".join(str(one) for one in factor.choices)
                    raise DoeError(
                        f"표 {number}행: ‘{factor.name}’은(는) {shown} 중 하나여야 "
                        f"합니다({value!r})."
                    )
                row[factor.name] = match[0]
                continue
            try:
                number_value = float(value)
            except (TypeError, ValueError) as failure:
                raise DoeError(
                    f"표 {number}행: ‘{factor.name}’ 값이 숫자가 아닙니다({value!r})."
                ) from failure
            if not math.isfinite(number_value):
                raise DoeError(f"표 {number}행: ‘{factor.name}’ 값이 유한한 숫자가 아닙니다.")
            row[factor.name] = number_value
        rows.append(row)
    return rows


def _same(choice: Any, value: Any) -> bool:
    """후보와 표의 값이 같은가 — 표(CSV)는 글자로 오므로 수 후보는 수로 견준다."""
    if isinstance(choice, bool) or choice is None:
        return str(value).strip().lower() == str(choice).lower() or value == choice
    if isinstance(choice, int | float):
        try:
            return float(value) == float(choice)
        except (TypeError, ValueError):
            return False
    return str(value).strip() == str(choice)


def plan(
    factors: list[Factor],
    *,
    method: Method = "factorial",
    samples: int = 20,
    seed: int = 1,
    limit: int = MAX_POINTS,
    check: Check | None = None,
    constraints: int = 0,
    table: list[dict[str, Any]] | None = None,
    offset: int = 0,
) -> Plan:
    """설계점 표를 **제약을 거쳐** 만든다. 제약이 없으면 `build_points` 와 꼭 같은 표다 —
    시드로 다시 만든 표가 예전 것과 같아야 해석 결과와 형상이 이어진다.

    - 격자: 칸을 다 펼쳐 어긋난 줄을 뺀다(`GRID_CAP` 까지).
    - LHS: 표본 수만큼 뽑아 거르고, 모자라면 같은 시드로 **두 배 큰 표**를 뽑아 앞에서부터
      통과한 줄을 채운다(`LHS_CAP` 까지). 큰 표도 라틴 하이퍼큐브라 통과한 영역 안에서 고르게
      흩어진다. 끝내 못 채우면 `shortfall` 로 말한다."""
    hits = [0] * constraints
    rejected_rows: list[dict[str, float | str]] = []

    def keep(rows: list[dict[str, float | str]]) -> tuple[list[dict[str, float | str]], int]:
        if check is None:
            return rows, 0
        kept = []
        dropped = 0
        for row in rows:
            failed = check(row)
            if failed:
                dropped += 1
                for index in failed:
                    if 0 <= index < len(hits):
                        hits[index] += 1
                if len(rejected_rows) < REJECTED_SHOWN:
                    rejected_rows.append(row)
            else:
                kept.append(row)
        return kept, dropped

    if method == "sobol":
        return _sobol_plan(
            factors, samples, seed, limit, check, constraints, offset, hits, keep
        )
    if method in ("oat", *CODED):
        made = designed_points(factors, method)
        kept, dropped = keep(made)
        return Plan(
            rows=kept if len(kept) <= limit else [],
            requested=len(made),
            kept=len(kept),
            candidates=len(made),
            rejected=dropped,
            hits=list(hits),
            too_many=len(kept) > limit,
            rejected_rows=list(rejected_rows),
        )
    if method == "table":
        given = table_points(factors, table or [])
        kept, dropped = keep(given)
        return Plan(
            rows=kept if len(kept) <= limit else [],
            requested=len(given),
            kept=len(kept),
            candidates=len(given),
            rejected=dropped,
            hits=list(hits),
            too_many=len(kept) > limit,
            rejected_rows=list(rejected_rows),
        )
    if method == "lhs":
        wanted = max(1, int(samples))
        size = wanted
        while True:
            hits[:] = [0] * constraints
            rejected_rows.clear()
            kept, dropped = keep(
                build_points(
                    factors, method="lhs", samples=size, seed=seed, limit=max(limit, size)
                )
            )
            if len(kept) >= wanted or size >= LHS_CAP or check is None:
                return Plan(
                    rows=kept[:wanted],
                    requested=wanted,
                    kept=min(wanted, len(kept)),
                    candidates=size,
                    rejected=dropped,
                    hits=list(hits),
                    shortfall=max(0, wanted - len(kept)),
                    too_many=wanted > limit,
                    rejected_rows=list(rejected_rows),
                )
            size = min(LHS_CAP, size * 2)
    total = count(factors, method, samples)
    if check is None:
        if total > limit:
            return Plan(rows=[], requested=total, kept=total, candidates=total, too_many=True)
        return Plan(
            rows=build_points(factors, method=method, samples=samples, seed=seed, limit=limit),
            requested=total,
            kept=total,
            candidates=total,
        )
    if total > GRID_CAP:
        raise DoeError(
            f"격자 조합이 {total}개입니다. 제약식으로 필터링할 때는 최대 {GRID_CAP}개까지만 "
            "탐색합니다. 단계 수를 줄이거나 LHS로 표본 수를 지정하십시오."
        )
    kept, dropped = keep(_grid(factors))
    return Plan(
        rows=kept if len(kept) <= limit else [],
        requested=total,
        kept=len(kept),
        candidates=total,
        rejected=dropped,
        hits=list(hits),
        too_many=len(kept) > limit,
        rejected_rows=list(rejected_rows),
    )


#: 미리 만들어 볼 점의 상한 — 인자 8개면 가운데 1 + 모두 최소 · 최대 2 + 인자마다 2 = 19.
PROBE_MAX = 2 * MAX_FACTORS + 3


def probe_points(factors: list[Factor]) -> list[tuple[str, dict[str, float | str]]]:
    """**만들기 전에 먼저 만들어 볼 점들** — 깨질 만한 곳은 범위의 끝이다.

    가운데 하나, 형상 인자를 모두 최소 · 모두 최대로 둘, 그리고 인자마다 혼자 최소 · 최대
    (나머지는 가운데). 격자의 모서리(2^k)를 다 만들면 인자 여덟에 256 개라 끝만 고른다.
    재료 · 고르기 · 배율 인자는 형상을 안 바꾸므로 첫 값에 둔다. 같은 줄이 겹치면 이름을
    합쳐 하나로."""
    shape = [f for f in factors if f.varying and f.mode not in NON_SHAPE]

    def low(factor: Factor) -> float:
        return min(float(v) for v in levels(factor))

    def high(factor: Factor) -> float:
        return max(float(v) for v in levels(factor))

    base: dict[str, float | str] = {f.name: levels(f)[0] for f in factors}
    center = {**base, **{f.name: _center(f) for f in shape}}
    wanted: list[tuple[str, dict[str, float | str]]] = [("중심", center)]
    if shape:
        wanted.append(("전체 최소", {**center, **{f.name: low(f) for f in shape}}))
        wanted.append(("전체 최대", {**center, **{f.name: high(f) for f in shape}}))
    for factor in shape:
        wanted.append((f"{factor.name} 최소", {**center, factor.name: low(factor)}))
        wanted.append((f"{factor.name} 최대", {**center, factor.name: high(factor)}))
    out: list[tuple[str, dict[str, float | str]]] = []
    for label, row in wanted:
        same = next((i for i, (_, seen) in enumerate(out) if seen == row), None)
        if same is None:
            out.append((label, row))
        else:
            out[same] = (f"{out[same][0]}, {label}", row)
    return out


def _center(factor: Factor) -> float | str:
    """인자의 가운데 — 구간이면 가운데를 가공 단위로, 값 목록이면 가운데에 가장 가까운
    값(같으면 작은 쪽), 재료 · 고르기 · 배율이면 첫 후보."""
    if factor.mode in NON_SHAPE:
        return levels(factor)[0]
    if factor.mode == "range":
        assert factor.start is not None and factor.end is not None
        return snap((factor.start + factor.end) / 2, factor.resolution)
    values = sorted(float(v) for v in levels(factor))
    middle = (values[0] + values[-1]) / 2
    return min(values, key=lambda v: (abs(v - middle), v))


def _coded(factor: Factor) -> tuple[float, float | str, float]:
    """중심 합성 · Box-Behnken 의 -1 · 0 · +1. 수 인자여야 하고 끝이 둘이어야 한다."""
    if factor.mode in NON_SHAPE:
        raise DoeError(
            f"‘{factor.name}’: 중심 합성 설계와 Box-Behnken 설계에는 수치 변수만 사용할 수 "
            "있습니다. 재료, 선택, 배율 인자는 고정하거나 격자 또는 LHS 방식을 사용하십시오."
        )
    values = [float(v) for v in levels(factor)]
    if min(values) == max(values):
        raise DoeError(f"‘{factor.name}’: 최솟값과 최댓값이 같습니다. 범위를 지정하십시오.")
    return min(values), _center(factor), max(values)


def designed_points(factors: list[Factor], method: str) -> list[dict[str, float | str]]:
    """정해진 꼴의 설계 — 하나씩 바꾸기 · 중심 합성(면 중심) · Box-Behnken. 겹친 줄은
    하나로."""
    fixed: dict[str, float | str] = {f.name: levels(f)[0] for f in factors if not f.varying}
    varying = [f for f in factors if f.varying]
    rows: list[dict[str, float | str]] = []
    if method == "oat":
        base = {f.name: _center(f) for f in varying}
        rows.append({**fixed, **base})
        for factor in varying:
            for value in levels(factor):
                if value != base[factor.name]:
                    rows.append({**fixed, **base, factor.name: value})
        return rows
    coded = {f.name: _coded(f) for f in varying}
    center = {name: three[1] for name, three in coded.items()}

    def at(signs: dict[str, int]) -> dict[str, float | str]:
        return {
            **fixed,
            **center,
            **{n: coded[n][0 if s < 0 else 2] for n, s in signs.items()},
        }

    names = [f.name for f in varying]
    if method == "ccd":
        for signs in itertools.product((-1, 1), repeat=len(names)):
            rows.append(at(dict(zip(names, signs, strict=True))))
        for name in names:
            rows.extend([at({name: -1}), at({name: 1})])
    elif method == "bbd":
        if len(names) < 3:
            raise DoeError(
                "Box-Behnken 설계는 변경할 변수가 3개 이상이어야 합니다. 변수가 2개이면 "
                "중심 합성 설계를 사용하십시오."
            )
        for first, second in itertools.combinations(names, 2):
            for a, b in itertools.product((-1, 1), repeat=2):
                rows.append(at({first: a, second: b}))
    rows.append({**fixed, **center})
    out: list[dict[str, float | str]] = []
    for row in rows:
        if row not in out:
            out.append(row)
    return out


#: Sobol 수열의 비트 수.
_BITS = 32
#: Joe & Kuo(new-joe-kuo-6.21201)의 2~8 차원 (s, a, m_i). 1 차원은 반 데르 코르풋(m 이 모두 1).
#: scipy.stats.qmc.Sobol(scramble=False) 와 같은 수를 낸다(시험이 견준다).
_JOE_KUO = (
    (1, 0, (1,)),
    (2, 1, (1, 3)),
    (3, 1, (1, 3, 1)),
    (3, 2, (1, 1, 1)),
    (4, 1, (1, 1, 3, 3)),
    (4, 4, (1, 3, 5, 13)),
    (5, 2, (1, 1, 5, 5, 17)),
)


def _directions(dimension: int) -> list[int]:
    if dimension == 0:
        return [1 << (_BITS - 1 - k) for k in range(_BITS)]
    s, a, m = _JOE_KUO[dimension - 1]
    v = [0] * _BITS
    for k in range(s):
        v[k] = m[k] << (_BITS - 1 - k)
    for k in range(s, _BITS):
        value = v[k - s] ^ (v[k - s] >> s)
        for i in range(1, s):
            if (a >> (s - 1 - i)) & 1:
                value ^= v[k - i]
        v[k] = value
    return v


def sobol(dimensions: int, count: int, seed: int = 0, start: int = 0) -> list[list[float]]:
    """Sobol 수열의 `start` 번째부터 `count` 개 — [0,1)^d. `seed` 가 0 이 아니면 **디지털
    이동**(차원마다 시드로 정한 수를 XOR)으로 섞는다 — 고른 분포는 그대로이고, 같은 시드면 같은
    수열이다. 이어 뽑으면(`start`) 앞의 점들과 함께 공간을 고르게 채운다."""
    if dimensions > len(_JOE_KUO) + 1:
        raise DoeError(f"Sobol 수열은 변수를 최대 {len(_JOE_KUO) + 1}개까지 지원합니다.")
    v = [_directions(d) for d in range(dimensions)]
    rng = seeded_random(seed)
    shift = (
        [int(rng() * (1 << _BITS)) for _ in range(dimensions)] if seed else [0] * dimensions
    )
    x = [0] * dimensions
    out: list[list[float]] = []
    for i in range(start + count):
        if i > 0:
            # 그레이 부호 — 앞 번호의 가장 낮은 0 비트 자리의 방향수를 XOR.
            c, j = 0, i - 1
            while j & 1:
                j >>= 1
                c += 1
            x = [x[d] ^ v[d][c] for d in range(dimensions)]
        if i >= start:
            out.append([(x[d] ^ shift[d]) / (1 << _BITS) for d in range(dimensions)])
    return out


def _sobol_plan(
    factors: list[Factor],
    samples: int,
    seed: int,
    limit: int,
    check: Check | None,
    constraints: int,
    offset: int,
    hits: list[int],
    keep: Callable[[list[dict[str, float | str]]], tuple[list[dict[str, float | str]], int]],
) -> Plan:
    """Sobol — `offset` 번째부터 차례로 뽑고, 제약에 걸리면 **수열을 이어** 더 뽑는다(다시 뽑지
    않는다 — 그래야 다음에 더할 때도 이어진다). 다음 번호를 `next_index` 로 돌려준다."""
    fixed: dict[str, float | str] = {f.name: levels(f)[0] for f in factors if not f.varying}
    varying = [f for f in factors if f.varying]
    wanted = max(1, int(samples))
    kept: list[dict[str, float | str]] = []
    rejected = 0
    rejected_rows: list[dict[str, float | str]] = []
    index = offset
    while len(kept) < wanted and index - offset < max(wanted, LHS_CAP if check else wanted):
        step = wanted - len(kept)
        batch = [
            {**fixed, **{f.name: _map_unit(f, u) for f, u in zip(varying, unit, strict=True)}}
            for unit in sobol(len(varying), step, seed, index)
        ]
        index += step
        good, dropped = keep(batch)
        rejected += dropped
        rejected_rows.extend(row for row in batch if row not in good)
        kept.extend(good)
        if check is None:
            break
    return Plan(
        rows=kept if wanted <= limit else [],
        requested=wanted,
        kept=len(kept),
        candidates=index - offset,
        rejected=rejected,
        hits=list(hits),
        shortfall=max(0, wanted - len(kept)),
        too_many=wanted > limit,
        rejected_rows=rejected_rows[:REJECTED_SHOWN],
        next_index=index,
    )


def _grid(factors: list[Factor]) -> list[dict[str, float | str]]:
    """전체 조합 — `build_points` 의 격자와 같은 순서(앞 인자가 바깥 고리)."""
    fixed: dict[str, float | str] = {f.name: levels(f)[0] for f in factors if not f.varying}
    varying = [f for f in factors if f.varying]
    return [
        {**fixed, **dict(zip([f.name for f in varying], combo, strict=True))}
        for combo in itertools.product(*(levels(f) for f in varying))
    ]


def _map_unit(factor: Factor, unit: float) -> float | str:
    """[0,1) 값을 인자의 범위로. 목록 · 재료 인자는 칸을 고른다."""
    if factor.mode in NON_SHAPE:
        choice: float | str = factor.choices[
            min(len(factor.choices) - 1, int(unit * len(factor.choices)))
        ]
        return choice
    if factor.mode == "list":
        index = min(len(factor.values) - 1, int(unit * len(factor.values)))
        return factor.values[index]
    assert factor.start is not None and factor.end is not None
    return snap(factor.start + unit * (factor.end - factor.start), factor.resolution)


#: 형상을 안 바꾸는 인자 — 레시피 `params` 로 가지 않는다.
NON_SHAPE = ("material", "choice", "scale")


def non_shape_factors(raw: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """그 방식의 인자 정의들(원문 그대로) — 위층이 조건에 적용할 때 쓴다."""
    return [one for one in raw or [] if one.get("mode") == mode]


def material_factors(raw: list[dict[str, Any]]) -> dict[str, list[str]]:
    """재료 인자 이름 → 바디들. 레시피 `params` 로 보내면 안 되는 이름들이다."""
    return {
        str(one.get("name")): [str(b) for b in one.get("bodies") or []]
        for one in raw or []
        if one.get("mode") == "material"
    }


def shape_values(row: dict[str, Any], raw: list[dict[str, Any]]) -> dict[str, float]:
    """설계점 한 줄에서 **형상을 바꾸는 값만** — 재료 · 고르기 · 배율 인자는 뺀다."""
    skip = {str(one.get("name")) for one in raw or [] if one.get("mode") in NON_SHAPE}
    return {name: value for name, value in row.items() if name not in skip}
