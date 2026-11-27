"""곡선 — 이름 붙은 표 하나를 여러 하중이 가리킨다(ADR 0013, `docs/해석-확장-설계.md` 4장).

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`).

- **공유 칸**이다(`Conditions.curves`) — 케이스마다 같은 곡선을 쓴다.
- 지금 가리키는 자리는 하중 안의 주파수 표 둘이다(`USES`): 조화 응답의 주파수별 배율
  (`frequency_table` — 선형 보간, 단위 없음)과 랜덤 진동의 가속도 PSD(`psd_table` — 로그-로그,
  g^2/Hz). 하중의 `curve` 가 곡선 이름이고 표와 함께 적지 않는다. 보간 · 단위가 그 표의 뜻과
  다르면 막는다 — 받는 쪽은 표를 늘 그 뜻으로 읽는다.
- 시간 · 단계 곡선(하중 이력)은 **정적의 하중**이 가리킨다(② — `TIME_USE`): 크기에 곱하는
  배율(단위 없음, 선형 보간)이고 하중의 `time_table` 로 풀린다. 단계 축(0 ~ N)은 단계 끝
  시간으로 옮겨 시간 표로 낸다(`steps.step_to_time`) — 받는 쪽은 한 모양만 받는다. 양 끝(0 과
  마지막 단계의 끝)을 꼭 적는다(SimEngBay, 2026-11-27).
- **내보낼 때 풀어 하중 안의 표로 싣는다**(`filled`) — 받는 쪽은 바뀌는 것이 없다(v1 · v2
  모두 — 곡선을 그대로 받는 판은 받는 쪽과 ②에서 정한다). 점 · 배율의 `"=식"` 은 설계점마다
  풀린 뒤 곱한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from app.core.conditions import steps
from app.core.conditions.common import Base, ConditionError, Number, _extra
from app.core.conditions.loads import (
    HARMONIC_LOADS,
    LOAD_LABELS,
    PSD_UNIT,
    TIME_LOADS,
    Load,
    _check_table,
)

if TYPE_CHECKING:
    from app.core.conditions.model import Conditions

CURVE_AXES: dict[str, str] = {"time": "시간", "step": "단계", "frequency": "주파수"}
CURVE_INTERPOLATIONS: dict[str, str] = {
    "linear": "선형",
    "loglog": "로그-로그",
    "step": "계단",
}


class Curve(Base):
    """곡선 하나 — 가로축(시간 · 단계 · 주파수)에 따라 바뀌는 값."""

    name: str = Field(min_length=1, max_length=60, title="곡선 이름")
    x: Literal["time", "step", "frequency"] = Field(
        title="가로축", json_schema_extra=_extra({"labels": CURVE_AXES})
    )
    """가로축 — 시간은 s, 주파수는 Hz, 단계는 단위 없는 단계 번호."""
    unit: str = Field(
        "",
        max_length=20,
        title="값의 단위",
        description="세로축 값의 단위입니다. 배율이면 비워 둡니다. 가속도 PSD 는 "
        "g^2/Hz 입니다.",
    )
    interpolation: Literal["linear", "loglog", "step"] = Field(
        "linear",
        title="보간",
        description="점 사이의 값을 읽는 법입니다. 로그-로그는 주파수 곡선에만 씁니다"
        "(규격의 dB/oct 기울기가 로그-로그 직선입니다).",
        json_schema_extra=_extra({"labels": CURVE_INTERPOLATIONS}),
    )
    points: list[list[Number]] = Field(
        default_factory=list,
        title="점",
        description="[가로축, 값] 두 칸씩, 가로축이 커지는 순서로 두 점 이상입니다. "
        "수 또는 =식을 입력합니다.",
    )
    scale: Number = Field(
        1,
        title="배율",
        description="모든 점의 값에 곱합니다. 곡선의 모양은 두고 크기만 실험계획으로 "
        "바꿀 때 =식을 씁니다.",
    )


@dataclass(frozen=True)
class Use:
    """하중 칸이 곡선을 어떻게 읽나 — 그 표의 뜻 그대로(`_check_load` 의 표 점검과 같다)."""

    field: str
    label: str
    interpolation: str
    unit: str
    low: float | None
    positive: bool
    #: 값의 부호를 보지 않는다(하중 이력 — 음의 배율은 방향을 뒤집는다).
    signed: bool = False


#: 곡선을 가리킬 수 있는 하중 — 종류마다 그 곡선이 채우는 표 칸(주파수 곡선).
USES: dict[str, Use] = {
    "psd_acceleration": Use("psd_table", "가속도 PSD", "loglog", PSD_UNIT, 0.0, True),
    **{
        kind: Use("frequency_table", "주파수별 배율", "linear", "", None, False)
        for kind in HARMONIC_LOADS
    },
}
#: 정적 하중의 시간 · 단계 곡선 — 크기에 곱하는 배율(② 비선형 정적, `TIME_LOADS`).
TIME_USE = Use("time_table", "시간별 배율", "linear", "", None, False, signed=True)


def use_of(load_type: str, analysis: str) -> Use | None:
    """그 해석에서 그 하중의 곡선이 채우는 표 — 정적이면 시간별 배율, 아니면 주파수 표."""
    if analysis == "static" and load_type in TIME_LOADS:
        return TIME_USE
    return USES.get(load_type)


def check_curves(curves: list[Curve]) -> None:
    """곡선 하나하나 — 이름 중복 · 점(두 점 이상, 가로축이 커지는 순서) · 로그-로그는 주파수
    곡선에만, 점과 배율이 0 보다 크게(로그를 못 쓴다)."""
    seen: dict[str, int] = {}
    for index, curve in enumerate(curves):
        where = f"curves[{index}]"
        if curve.name in seen:
            raise ConditionError(
                f"{where}: 곡선 이름 ‘{curve.name}’이(가) 중복됩니다"
                f"(curves[{seen[curve.name]}])."
            )
        seen[curve.name] = index
        log = curve.interpolation == "loglog"
        if log and curve.x != "frequency":
            raise ConditionError(
                f"{where}: 곡선 ‘{curve.name}’ — 로그-로그 보간은 주파수 곡선에만 씁니다."
            )
        _check_table(
            f"{where}: 곡선 ‘{curve.name}’의 점",
            curve.points,
            low=0.0 if log else None,
            positive=log,
            signed=not log,
            axis=CURVE_AXES[curve.x],
        )
        scale = curve.scale
        if log and not isinstance(scale, str) and scale <= 0:
            raise ConditionError(
                f"{where}: 곡선 ‘{curve.name}’의 배율은 0보다 커야 합니다(로그-로그 보간)."
            )


def table_of(curve: Curve | dict[str, Any]) -> list[list[Any]]:
    """곡선을 표로 — `[[가로축, 값 * 배율], …]`. 식이 남아 있으면(저장할 때의 점검) 그 칸은
    식 그대로 둔다 — 설계점마다 풀린다."""
    if isinstance(curve, dict):
        points, scale = curve.get("points") or [], curve.get("scale", 1)
    else:
        points, scale = curve.points, curve.scale
    return [[one[0], _scaled(one[1], scale)] for one in points]


def _scaled(value: Any, scale: Any) -> Any:
    if isinstance(value, str) or scale == 1:
        return value
    if isinstance(scale, str):
        return scale
    return float(f"{value * scale:.12g}")


def check_uses(conditions: Conditions) -> None:
    """하중이 가리키는 곡선 — 있나, 표와 함께 적지 않았나, 그 표의 뜻(가로축 · 보간 · 단위 ·
    값의 범위)과 맞나. 정적 하중의 시간 · 단계 곡선은 양 끝도 본다."""
    by_name = {curve.name: curve for curve in conditions.curves}
    kind = conditions.analysis.type
    for index, load in enumerate(conditions.loads):
        if not load.curve:
            continue
        where = f"loads[{index}]"
        label = f"{LOAD_LABELS[load.type]} ‘{load.name}’"
        use = use_of(load.type, kind)
        if use is None:
            raise ConditionError(
                f"{where}: {label}은(는) 곡선을 가리킬 수 없습니다. 곡선은 조화 응답의 "
                "주파수별 배율, 가속도 PSD, 정적 하중의 시간별 배율에 씁니다."
            )
        curve = by_name.get(load.curve)
        if curve is None:
            raise ConditionError(f"{where}: {label}의 곡선 ‘{load.curve}’이(가) 없습니다.")
        named = f"곡선 ‘{curve.name}’"
        if getattr(load, use.field):
            raise ConditionError(
                f"{where}: {label}에 {use.label} 표와 {named}을(를) 함께 적을 수 없습니다. "
                "하나만 적으십시오."
            )
        timed = use is TIME_USE
        if timed and curve.x == "frequency":
            raise ConditionError(
                f"{where}: 정적 해석의 {label}에는 시간 곡선이나 단계 곡선만 쓸 수 있습니다"
                f"({named}은(는) 주파수 곡선)."
            )
        if not timed and curve.x != "frequency":
            raise ConditionError(
                f"{where}: {label}의 {use.label}에는 주파수 곡선만 쓸 수 있습니다"
                f"({named}은(는) {CURVE_AXES[curve.x]} 곡선). 시간 곡선과 단계 곡선은 정적 "
                "해석의 하중에 씁니다."
            )
        if curve.interpolation != use.interpolation:
            raise ConditionError(
                f"{where}: {label}의 {use.label}은(는) "
                f"{CURVE_INTERPOLATIONS[use.interpolation]} 보간입니다({named}: "
                f"{CURVE_INTERPOLATIONS[curve.interpolation]}). 해석 쪽이 그렇게 읽습니다."
            )
        if curve.unit != use.unit:
            raise ConditionError(
                f"{where}: {label}의 {use.label} 단위는 {use.unit or '없음(배율)'}입니다"
                f"({named}: {curve.unit or '없음'})."
            )
        what = f"{where}: {label}의 {named}(배율 곱)"
        table = table_of(curve)
        _check_table(what, table, low=use.low, positive=use.positive, signed=use.signed)
        if timed and curve.x == "time":
            steps.check_ends(what, table, steps.ends(conditions.analysis.load_steps)[-1])
        elif timed:
            count = steps.count(conditions.analysis)
            first, last = table[0][0], table[-1][0]
            numbers = not isinstance(first, str) and not isinstance(last, str)
            if numbers and (first != 0 or last != count):
                raise ConditionError(
                    f"{what}은(는) 단계 0에서 시작해 마지막 단계 {count}에서 끝나야 합니다"
                    f"(지금 {float(first):g} ~ {float(last):g}). 양 끝을 모두 적으십시오."
                )


def _table_for(
    load: Load, curve: Curve, analysis: str, step_ends: list[Any]
) -> list[list[Any]]:
    """하중이 가리키는 곡선의 표 — 정적의 단계 곡선은 시간으로 옮긴다."""
    table = table_of(curve)
    if analysis == "static" and curve.x == "step" and use_of(load.type, analysis) is TIME_USE:
        return steps.step_to_time(table, step_ends)
    return table


def with_tables(conditions: Conditions) -> Conditions:
    """곡선을 가리키는 하중에 그 표를 채운 사본 — 나머지 점검(표 · 해석의 주파수 범위 · 단계의
    양 끝)이 표를 적은 것과 같은 길로 본다. `check_uses` 를 지난 뒤에 부른다."""
    by_name = {curve.name: curve for curve in conditions.curves}
    kind = conditions.analysis.type
    step_ends = steps.ends(conditions.analysis.load_steps)
    loads: list[Load] = []
    for load in conditions.loads:
        use = use_of(load.type, kind)
        if load.curve and use is not None and load.curve in by_name:
            table = _table_for(load, by_name[load.curve], kind, step_ends)
            load = load.model_copy(update={use.field: table})
        loads.append(load)
    return conditions.model_copy(update={"loads": loads})


def filled(out: dict[str, Any]) -> dict[str, Any]:
    """내보낼 한 벌(식이 풀린 v1 모양) — 곡선을 하중 안의 표로 풀고 `curves` · 하중의 `curve`
    칸을 뺀다. 곡선이 없는 한 벌은 지금과 바이트로 같다."""
    by_name = {str(one.get("name")): one for one in out.pop("curves", None) or []}
    analysis = out.get("analysis") or {}
    kind = str(analysis.get("type") or "")
    step_ends = steps.ends(analysis.get("load_steps") or [])
    for load in out.get("loads") or []:
        name = load.pop("curve", "")
        use = use_of(str(load.get("type")), kind)
        if name and use is not None and name in by_name:
            curve = by_name[name]
            table = table_of(curve)
            if use is TIME_USE and curve.get("x") == "step":
                table = steps.step_to_time(table, step_ends)
            load[use.field] = table
    return out
