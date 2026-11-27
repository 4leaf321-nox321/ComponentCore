"""하중 단계 — ② 비선형 정적(`docs/해석-확장-설계.md` 8장, SimEngBay 와 정함 2026-11-27).

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`).

정적 구조 케이스 하나 안의 하중 이력이다. 해석 종류가 바뀌거나 끝 상태에서 다시 시작하는
것은 케이스 사슬(`depends_on`)이 맡고, 한 해석 안에서 하중을 나누어 거는 것은 단계가 맡는다.

- **칸** — 해석 설정의 `load_steps`(끝 시간 · 부단계 수) · `convergence` · `outputs`, 하중의
  `time_table`(시간별 배율, 곡선으로도) · `active_steps`(적용 단계) · `bolt_steps`(조임 ·
  잠금). 대변형은 단계가 아니라 해석 설정(`large_deflection`)이다.
- **해석 케이스에서만** 쓴다(`check_v1`) — 케이스가 없는 조건에 적으면 저장할 때 막는다.
- **v1 으로 나가는 길은 막는다**(`blocked`) — 받는 쪽이 모르는 칸을 말없이 버리고 한 단계로
  풀면 답이 틀린다(SimEngBay 는 조건의 모르는 칸을 버린다). v2(`doe_conditions_v2`)에서는
  케이스가 하나여도 v2 로 낸다(`model.resolve`).
- **기본값이면 내보내지 않는다**(`strip_defaults`) — 지금까지의 내보내기와 바이트로 같다.
- 뜻(두 솔버 공통, SimEngBay 가 번역한다):
  - 배율이 없는 하중은 첫 단계에서 0 → 크기로 오르고 그 뒤 유지한다(정적 기본).
  - `active_steps` — 처음 켜지는 단계 안에서 0 → 크기, 꺼지는 단계 안에서 0 으로 선형으로
    내린다. 받는 쪽이 총 시간의 배율표로 바꾼다. 배율 표와 함께 쓰지 않는다.
  - `time_table` — 양 끝(0 과 마지막 단계의 끝 시간)을 꼭 적는다. 표 밖을 두 솔버가 같게
    읽는지 모른다. 보간은 선형만.
  - `bolt_steps` — 단계 수만큼, 조임(`load`)은 맨 앞에 한 번, 나머지는 잠금(`lock`).
  - v1 의 볼트 정적(`steps: 2`)과 같은 뜻: 단계 둘 · 볼트 [load, lock] · 볼트가 아닌 하중
    `active_steps` [2] · 중력은 모든 단계.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.conditions.analysis import Analysis
from app.core.conditions.common import ConditionError
from app.core.conditions.loads import LOAD_LABELS, TIME_LOADS, Load, _check_table

if TYPE_CHECKING:
    from app.core.conditions.model import Conditions

#: ② 칸 — 기본값이 아니면 「단계를 쓴다」.
STAGED_ANALYSIS = ("load_steps", "convergence", "outputs")
STAGED_LOADS = ("time_table", "active_steps", "bolt_steps")
#: 결과를 바꾸는 칸 — 받는 쪽 능력표의 `fields` 에 없으면 알림이 아니라 막는다(SimEngBay,
#: 2026-11-27). 수렴 · 출력은 답이 같고 과정 · 출력만 달라져 알림이다.
RESULT_CHANGING: dict[str, frozenset[str]] = {
    "analysis": frozenset({"load_steps"}),
    "loads": frozenset({"time_table", "active_steps", "bolt_steps"}),
}

_GRAVITY = "standard_earth_gravity"
_BOLT = "bolt_pretension"


def _default(model: type[Any], key: str) -> Any:
    return model.model_fields[key].get_default(call_default_factory=True)


def _title(model: type[Any], key: str) -> str:
    return str(model.model_fields[key].title or key)


def _label(load: Load) -> str:
    return f"{LOAD_LABELS[load.type]} ‘{load.name}’"


def timed(load: Load, analysis: str) -> bool:
    """곡선이 시간별 배율을 채우는 하중인가 — 정적의 `TIME_LOADS`."""
    return analysis == "static" and load.type in TIME_LOADS


def in_use(view: Conditions) -> list[tuple[str, str]]:
    """쓰고 있는 ② 칸 — `(자리, 이름)`. 곡선을 가리키는 정적 하중은 시간별 배율을 쓴다."""
    out: list[tuple[str, str]] = []
    for key in STAGED_ANALYSIS:
        if getattr(view.analysis, key) != _default(Analysis, key):
            out.append(("analysis", f"해석 설정 ‘{_title(Analysis, key)}’"))
    kind = view.analysis.type
    for index, load in enumerate(view.loads):
        for key in STAGED_LOADS:
            if getattr(load, key) != _default(Load, key):
                out.append((f"loads[{index}]", f"{_label(load)}의 ‘{_title(Load, key)}’"))
        if load.curve and timed(load, kind):
            out.append((f"loads[{index}]", f"{_label(load)}의 시간 곡선 ‘{load.curve}’"))
    return out


def check_v1(conditions: Conditions) -> None:
    """케이스가 없는 조건(v1)에는 ② 칸을 쓰지 않는다 — 해석 케이스에서만."""
    used = in_use(conditions)
    if used:
        at, what = used[0]
        raise ConditionError(
            f"{at}: {what}은(는) 해석 케이스에서 지정합니다. 해석 케이스로 나누어 "
            "지정하십시오."
        )


def blocked(name: str, view: Conditions) -> str:
    """v1 으로 내보낼 때 ② 칸이 있으면 막는 까닭 — 없으면 `""`."""
    used = in_use(view)
    if not used:
        return ""
    what = ", ".join(one for _, one in used[:3]) + (" 등" if len(used) > 3 else "")
    where = f"케이스 ‘{name}’의 " if name else ""
    return (
        f"{where}{what}은(는) 해석 쪽(SimEngBay)이 케이스가 있는 조건(schema_version 2)으로만 "
        "받습니다. 지금은 내보낼 수 없습니다."
    )


def count(analysis: Analysis) -> int:
    """하중 단계 수 — `load_steps` 가 비면 하나."""
    return max(1, len(analysis.load_steps))


def ends(steps: list[Any]) -> list[Any]:
    """단계마다 끝 시간 — 비운 것은 단계 번호. `steps` 는 모델이든 dict 든."""
    out: list[Any] = []
    for index, step in enumerate(steps):
        end = step.get("end_time") if isinstance(step, dict) else step.end_time
        out.append(index + 1 if end is None else end)
    return out or [1]


def step_to_time(points: list[list[Any]], step_ends: list[Any]) -> list[list[Any]]:
    """단계 축의 점(0 ~ N)을 시간으로 — 단계 k 는 k 번째 단계의 끝 시간, 그 사이는 선형. 식이
    남은 칸은 그대로 둔다(설계점마다 풀린 뒤 옮긴다)."""
    marks = [0, *step_ends]
    if any(isinstance(one, str) for one in marks):
        return [list(one) for one in points]
    out: list[list[Any]] = []
    for x, value in points:
        if isinstance(x, str):
            out.append([x, value])
            continue
        whole = min(max(int(x), 0), len(marks) - 1)
        if whole == len(marks) - 1:
            out.append([float(marks[whole]) if x == whole else x, value])
            continue
        part = x - whole
        at = marks[whole] + part * (marks[whole + 1] - marks[whole])
        out.append([float(f"{at:.12g}"), value])
    return out


def check_ends(where: str, table: list[list[Any]], end: Any) -> None:
    """시간별 배율의 양 끝 — 0 에서 시작해 마지막 단계의 끝 시간에서 끝난다."""
    first, last = table[0][0], table[-1][0]
    if isinstance(first, str) or isinstance(last, str) or isinstance(end, str):
        return
    if first != 0 or last != end:
        raise ConditionError(
            f"{where}은(는) 0 s에서 시작해 마지막 하중 단계의 끝 시간({float(end):g} s)에서 "
            f"끝나야 합니다(지금 {float(first):g} ~ {float(last):g} s). 양 끝을 모두 "
            "적으십시오."
        )


def check(view: Conditions) -> None:
    """한 케이스(v1 모양 보기)의 ② 칸 — 정적에서만, 단계 · 하중의 단계 칸이 서로 맞는가.
    곡선이 채운 시간별 배율도 표를 적은 것과 같은 길로 본다(`curves.with_tables` 뒤에
    부른다)."""
    analysis = view.analysis
    if analysis.type != "static":
        for at, what in in_use(view):
            raise ConditionError(f"{at}: {what}은(는) 정적 구조 해석에서만 지정합니다.")
        return
    _check_load_steps(analysis)
    steps = count(analysis)
    end = ends(analysis.load_steps)[-1]
    for index, load in enumerate(view.loads):
        _check_load(f"loads[{index}]", load, steps, end)


def _check_load_steps(analysis: Analysis) -> None:
    if not analysis.load_steps:
        return
    if analysis.steps != 1 or analysis.substeps is not None:
        raise ConditionError(
            "analysis: 하중 단계를 지정하면 ‘하중 단계 수’와 ‘초기 부단계 수’는 비워 "
            "두십시오. 단계마다 지정합니다."
        )
    before: float | None = 0.0
    for index, (step, end) in enumerate(
        zip(analysis.load_steps, ends(analysis.load_steps), strict=True)
    ):
        where = f"analysis.load_steps[{index}]"
        if isinstance(end, str) or before is None:
            before = None
        elif end <= before:
            raise ConditionError(
                f"{where}: 끝 시간({float(end):g} s)은 앞 단계({before:g} s)보다 커야 합니다."
            )
        else:
            before = float(end)
        counts = {
            key: getattr(step.substeps, key)
            for key in ("initial", "minimum", "maximum")
            if isinstance(getattr(step.substeps, key), int)
        }
        if any(one < 1 for one in counts.values()):
            raise ConditionError(f"{where}: 부단계 수는 1 이상이어야 합니다.")
        order = [counts[key] for key in ("minimum", "initial", "maximum") if key in counts]
        if order != sorted(order):
            raise ConditionError(f"{where}: 부단계 수는 최소 ≤ 처음 ≤ 최대여야 합니다.")


def _check_load(where: str, load: Load, steps: int, end: Any) -> None:
    label = _label(load)
    if load.active_steps:
        if load.type == _GRAVITY:
            raise ConditionError(
                f"{where}: 중력은 모든 하중 단계에 같게 걸립니다. ‘적용 단계’를 비워 두십시오."
            )
        if load.type == _BOLT:
            raise ConditionError(
                f"{where}: {label}은(는) ‘단계별 볼트 동작’으로 단계를 정합니다."
            )
        if load.time_table is not None or load.curve:
            raise ConditionError(
                f"{where}: {label}에 ‘시간별 배율’(또는 곡선)과 ‘적용 단계’를 함께 쓸 수 "
                "없습니다. 배율 표에 0을 적으면 같은 뜻입니다."
            )
        outside = [one for one in load.active_steps if not 1 <= one <= steps]
        if outside:
            raise ConditionError(
                f"{where}: {label}의 적용 단계 {', '.join(map(str, outside))}이(가) "
                f"없습니다(하중 단계 {steps}개)."
            )
        if sorted(set(load.active_steps)) != load.active_steps:
            raise ConditionError(
                f"{where}: {label}의 적용 단계는 작은 번호부터 한 번씩 적으십시오."
            )
    if load.time_table is not None:
        if load.type not in TIME_LOADS:
            kinds = ", ".join(LOAD_LABELS[one] for one in TIME_LOADS)
            raise ConditionError(
                f"{where}: ‘시간별 배율’은 {kinds}에만 지정할 수 있습니다({label})."
            )
        what = f"{where}: {label}의 시간별 배율"
        _check_table(what, load.time_table, low=None, signed=True, axis="시간")
        check_ends(what, load.time_table, end)
    if load.bolt_steps:
        if load.type != _BOLT:
            raise ConditionError(
                f"{where}: ‘단계별 볼트 동작’은 볼트 예압에만 지정할 수 있습니다({label})."
            )
        if len(load.bolt_steps) != steps:
            raise ConditionError(
                f"{where}: {label}의 단계별 볼트 동작은 하중 단계 수({steps})만큼 "
                f"적어야 합니다(지금 {len(load.bolt_steps)})."
            )
        if load.bolt_steps[0] != "load" or "load" in load.bolt_steps[1:]:
            raise ConditionError(
                f"{where}: {label}은(는) 첫 단계에서 한 번 조이고(‘조임’) 나머지 단계에서 "
                "잠급니다(‘잠금’)."
            )


def strip_defaults(item: dict[str, Any], keys: tuple[str, ...], model: type[Any]) -> None:
    """내보낼 칸에서 ② 칸 중 기본값인 것을 뺀다 — 단계를 쓰지 않는 한 벌은 지금과 바이트로
    같다."""
    for key in keys:
        if key in item and item[key] == _default(model, key):
            item.pop(key)


def filled_steps(analysis: dict[str, Any]) -> dict[str, Any]:
    """내보낼 하중 단계 — 비운 끝 시간을 단계 번호로 채우고, 부단계 · 반복 · 횟수는 정수로
    (식이 풀린 뒤 7.0 은 7, 7.5 는 설계점을 실패로)."""
    out = dict(analysis)
    steps = out.get("load_steps")
    if steps:
        out["load_steps"] = [
            {
                **step,
                "end_time": end,
                "substeps": _integers(step.get("substeps") or {}, f"load_steps[{index}]"),
            }
            for index, (step, end) in enumerate(zip(steps, ends(steps), strict=True))
        ]
    if isinstance(out.get("convergence"), dict):
        out["convergence"] = _integers(out["convergence"], "convergence")
    at = (out.get("outputs") or {}).get("at") if isinstance(out.get("outputs"), dict) else None
    if isinstance(at, dict):
        out["outputs"] = {**out["outputs"], "at": _integers(at, "outputs.at")}
    return out


def _integers(values: dict[str, Any], where: str) -> dict[str, Any]:
    out = dict(values)
    for key in ("initial", "minimum", "maximum", "max_iterations", "count"):
        value = out.get(key)
        if isinstance(value, float):
            if not value.is_integer():
                raise ConditionError(
                    f"analysis.{where}.{key}: 정수여야 합니다(식의 값 {value:g})."
                )
            out[key] = int(value)
    return out
