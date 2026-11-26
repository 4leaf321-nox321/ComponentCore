"""해석 설정 — 종류 · 라벨 · 안내 · 모델, 정수 칸 · 점검 · 채우기.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.core.conditions.common import (
    Base,
    ConditionError,
    Integer,
    Number,
    _extra,
    _integer_or_expr,
)
from app.core.conditions.registry import ANALYSES, analyses_with

#: 종류 → 화면의 이름 · 안내 — 등록부(`registry.ANALYSES`)의 차례 그대로.
ANALYSIS_LABELS: dict[str, str] = {name: kind.label for name, kind in ANALYSES.items()}

ANALYSIS_NOTES: dict[str, str] = {name: kind.note for name, kind in ANALYSES.items()}

#: 종류 안에서 **다른 칸의 값에 따라** 보이는 칸 — `{종류: {칸: 값}}`. 열 해석의 시간 칸은
#: 과도일 때만 뜻이 있다. 화면이 감추고, 내보낼 때도 뺀다.
_TRANSIENT: dict[str, dict[str, str]] = {"thermal": {"thermal_mode": "transient"}}

#: 해석 설정 창 맨 위의 한두 줄.
_ANALYSIS_INTRO = (
    "해석 종류를 선택합니다. 종류별로 필요한 입력란만 표시되며, 내보낼 때도 해당 "
    "항목만 포함됩니다. 확실하지 않은 항목은 비워 두거나 ‘프로그램 제어’로 "
    "두십시오."
)


class Analysis(Base):
    """무엇을 풀 것인가 — **종류마다 칸이 다르다**(`only_for`). 내보낼 때는 그 종류의 칸만
    기본값을 채워 싣는다(`_filled_analysis`) — 받는 쪽이 「이 칸이 없으면 무엇인가」 를
    짐작하지 않게."""

    type: Literal["modal", "static", "harmonic", "random", "explicit", "thermal"] = Field(
        default="modal", json_schema_extra=_extra({"labels": ANALYSIS_LABELS})
    )
    # ── 모달 · 조화 ────────────────────────────────────────────────────────
    modes: Integer | None = Field(
        default=6,
        title="모드 수",
        description="구할 고유진동 모드의 개수입니다(조화 응답 · 랜덤 진동에서는 겹쳐 쓸 모드 "
        "수). 일반적으로 6~20이며, 랜덤 진동은 PSD 최대 주파수의 1.5배까지의 모드를 "
        "포함하십시오.",
        json_schema_extra=_extra({"only_for": analyses_with("modes"), "integer": True}),
    )
    frequency_range: list[Number] | None = Field(
        default=None,
        title="주파수 범위",
        description=(
            "모달 · 랜덤 진동: 이 범위 안에서 모드를 구합니다(비워 두면 낮은 차수부터). "
            "조화 응답: 계산할 주파수 범위입니다(필수)."
        ),
        json_schema_extra=_extra(
            {"only_for": analyses_with("frequency_range"), "unit": "Hz", "range": True}
        ),
    )
    prestressed: bool = Field(
        default=False,
        title="선응력 반영",
        description="선행 정적 해석의 응력(볼트 체결, 원심력)을 반영하여 계산합니다. "
        "초기조건의 ‘선응력’과 함께 사용합니다.",
        json_schema_extra=_extra({"only_for": analyses_with("prestressed")}),
    )
    # ── 조화 응답 ──────────────────────────────────────────────────────────
    solution_intervals: Integer = Field(
        default=10,
        title="주파수 점 수",
        description="주파수 범위를 나누는 계산점의 개수입니다. 공진 부근을 자세히 확인하려면 "
        "늘리십시오.",
        json_schema_extra=_extra(
            {"only_for": analyses_with("solution_intervals"), "integer": True}
        ),
    )
    method: Literal["mode_superposition", "full"] = Field(
        default="mode_superposition",
        title="풀이 방법",
        description="모드 중첩: 모달 결과를 이용해 빠르게 계산합니다(모드 수 필요). "
        "완전법: 느리지만 정확합니다.",
        json_schema_extra=_extra(
            {
                "only_for": analyses_with("method"),
                "labels": {"mode_superposition": "모드 중첩(빠름)", "full": "완전법(정확)"},
            }
        ),
    )
    damping_ratio: Number | None = Field(
        default=None,
        title="감쇠비",
        description="임계 감쇠에 대한 비율입니다. 강 구조물은 0.01~0.03입니다. 조화 응답에서 "
        "비워 두면 감쇠가 없어 공진에서 응답이 무한히 커집니다. 랜덤 진동에는 반드시 "
        "입력해야 합니다.",
        json_schema_extra=_extra({"only_for": analyses_with("damping_ratio")}),
    )
    # ── 정적 구조 ──────────────────────────────────────────────────────────
    large_deflection: bool = Field(
        default=False,
        title="대변형",
        description=(
            "변형이 커서 형상이 크게 바뀌는 경우 사용합니다(비선형, 계산 시간 증가). "
            "얇은 판, 고무, 큰 처짐이 해당합니다."
        ),
        json_schema_extra=_extra({"only_for": analyses_with("large_deflection")}),
    )
    steps: Integer = Field(
        default=1,
        title="하중 단계 수",
        description="하중을 나누어 적용하는 단계 수입니다. 볼트를 먼저 체결한 뒤 하중을 "
        "적용하면 2입니다.",
        json_schema_extra=_extra({"only_for": analyses_with("steps"), "integer": True}),
    )
    substeps: Integer | None = Field(
        default=None,
        title="초기 부단계 수",
        description=(
            "한 하중 단계를 나누어 계산하는 횟수입니다. 접촉이나 대변형이 수렴하지 않으면 "
            "늘리십시오. 비워 두면 자동으로 결정됩니다."
        ),
        json_schema_extra=_extra({"only_for": analyses_with("substeps"), "integer": True}),
    )
    solver: Literal["program_controlled", "direct", "iterative"] = Field(
        default="program_controlled",
        title="솔버",
        description=(
            "확실하지 않으면 ‘프로그램 제어’를 선택하십시오. 직접법은 메모리 사용량이 "
            "많고, 반복법은 큰 솔리드 모델에서 빠릅니다."
        ),
        json_schema_extra=_extra(
            {
                "only_for": analyses_with("solver"),
                "labels": {
                    "program_controlled": "프로그램 제어",
                    "direct": "직접법",
                    "iterative": "반복법",
                },
            }
        ),
    )
    # ── 열 ────────────────────────────────────────────────────────────────
    thermal_mode: Literal["steady", "transient"] = Field(
        default="steady",
        title="열 해석",
        description="정상 상태: 시간이 충분히 지나 변하지 않는 온도를 계산합니다. "
        "과도: 시간에 따른 변화를 계산합니다(종료 시간 필요).",
        json_schema_extra=_extra(
            {
                "only_for": analyses_with("thermal_mode"),
                "labels": {"steady": "정상 상태", "transient": "과도(시간 이력)"},
            }
        ),
    )
    time_step: Number | None = Field(
        default=None,
        title="초기 시간 간격",
        description="과도 열 해석의 첫 시간 간격입니다. 비워 두면 자동으로 결정됩니다.",
        json_schema_extra=_extra(
            {"only_for": analyses_with("time_step"), "unit": "s", "when": _TRANSIENT}
        ),
    )
    # ── 명시적 · 열 과도 ─────────────────────────────────────────────────
    end_time: Number | None = Field(
        default=None,
        title="종료 시간",
        description="명시적: 충돌·낙하가 끝날 때까지의 시간입니다(일반적으로 수 ms). "
        "열 과도: 관찰할 시간입니다.",
        json_schema_extra=_extra(
            {
                "only_for": analyses_with("end_time"),
                "unit": "s",
                "when": _TRANSIENT,
            }
        ),
    )
    output_count: Integer = Field(
        default=20,
        title="결과 저장 횟수",
        description="종료 시간까지 결과를 저장하는 횟수입니다. 많을수록 파일 크기가 커집니다.",
        json_schema_extra=_extra(
            {
                "only_for": analyses_with("output_count"),
                "integer": True,
                "when": _TRANSIENT,
            }
        ),
    )
    mass_scaling_dt: Number | None = Field(
        default=None,
        title="질량 스케일링 시간 간격",
        description="이보다 작은 시간 간격이 필요한 작은 요소에 질량을 추가하여 계산 "
        "속도를 높입니다. 비워 두면 사용하지 않습니다(정확).",
        json_schema_extra=_extra({"only_for": analyses_with("mass_scaling_dt"), "unit": "s"}),
    )

    @field_validator(
        "modes",
        "solution_intervals",
        "steps",
        "output_count",
        "method",
        "solver",
        "thermal_mode",
        mode="before",
    )
    @classmethod
    def _blank(cls, value: Any, info: Any) -> Any:
        """비운 칸(`None` · `""`)은 기본값 — 화면이 「기본 6」 이라고 보여 준 그대로. 정수 칸의
        글자는 정수로, 식(`=모드수`)은 그대로 둔다."""
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return _integer_or_expr(value) if info.field_name in _INTEGER_FIELDS else value

    @field_validator("substeps", mode="before")
    @classmethod
    def _integer(cls, value: Any) -> Any:
        return _integer_or_expr(value)


def _check_analysis(analysis: Analysis) -> None:
    """해석 설정 — 그 종류가 꼭 필요로 하는 값이 있는가. 없으면 받는 쪽이 짐작하거나 멈춘다."""
    label = ANALYSIS_LABELS[analysis.type]

    def positive(value: Any) -> bool:
        return isinstance(value, str) or (value is not None and value > 0)

    span = analysis.frequency_range
    if span is not None:
        if len(span) != 2:
            raise ConditionError(
                "analysis: 주파수 범위는 최솟값과 최댓값 두 개로 지정해야 합니다."
            )
        low, high = span
        if not isinstance(low, str) and not isinstance(high, str) and not 0 <= low < high:
            raise ConditionError("analysis: 주파수 범위는 0 ≤ 최소 < 최대를 만족해야 합니다.")
    if analysis.type in ("modal", "random") and not positive(analysis.modes):
        raise ConditionError(f"analysis: {label}의 모드 수는 1 이상이어야 합니다.")
    if analysis.type == "harmonic":
        if span is None:
            raise ConditionError(f"analysis: {label}에 주파수 범위가 없습니다.")
        if analysis.method == "mode_superposition" and not positive(analysis.modes):
            raise ConditionError(
                f"analysis: {label}을(를) 모드 중첩으로 계산하려면 모드 수가 1 이상이어야 "
                "합니다."
            )
        if isinstance(analysis.solution_intervals, int) and analysis.solution_intervals < 1:
            raise ConditionError(f"analysis: {label}의 주파수 점 수는 1 이상이어야 합니다.")
    if analysis.type == "static" and isinstance(analysis.steps, int) and analysis.steps < 1:
        raise ConditionError(f"analysis: {label}의 하중 단계 수는 1 이상이어야 합니다.")
    needs_end = analysis.type == "explicit" or (
        analysis.type == "thermal" and analysis.thermal_mode == "transient"
    )
    if needs_end and not positive(analysis.end_time):
        kind = label if analysis.type == "explicit" else "과도 열 해석"
        raise ConditionError(f"analysis: {kind}에 종료 시간이 없습니다.")
    if (
        analysis.type in ("explicit", "thermal")
        and isinstance(analysis.output_count, int)
        and analysis.output_count < 1
    ):
        raise ConditionError("analysis: 결과 저장 횟수는 1 이상이어야 합니다.")


#: 정수 칸 — 식이 풀린 뒤 정수여야 하고, 수 · 단계는 1 이상이어야 한다.
_INTEGER_FIELDS = (
    "modes",
    "solution_intervals",
    "steps",
    "substeps",
    "output_count",
    "inflation_layers",
)


def _integerized(values: dict[str, Any], where: str) -> dict[str, Any]:
    """식이 풀린 정수 칸을 **정수로** — 7.0 은 7, 7.5 는 설계점을 실패로 돌린다(모드 7.5 개는
    없다). 조용히 반올림하면 사람이 준 값과 다른 해석이 돈다."""
    out = dict(values)
    for key in _INTEGER_FIELDS:
        value = out.get(key)
        if isinstance(value, float):
            if not value.is_integer():
                raise ConditionError(f"{where}.{key}: 정수가 아닙니다({value}).")
            out[key] = int(value)
        if isinstance(out.get(key), int) and key != "inflation_layers" and out[key] < 1:
            raise ConditionError(f"{where}.{key}: 1 이상이어야 합니다(현재 {out[key]}).")
    return out


def _filled_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """내보낼 해석 설정 — **그 종류가 쓰는 칸만**, 비운 것은 기본값으로 채워서. 모달에
    `end_time` 이 실려 가면 받는 쪽은 그것이 무슨 뜻인지 짐작해야 한다."""
    kind = str(analysis.get("type") or "modal")
    out: dict[str, Any] = {"type": kind}
    for key, field in Analysis.model_fields.items():
        if key == "type":
            continue
        extra: dict[str, Any] = (
            dict(field.json_schema_extra) if isinstance(field.json_schema_extra, dict) else {}
        )
        only = extra.get("only_for")
        if only is not None and kind not in only:
            continue
        # 다른 칸의 값에 따라 뜻이 있는 칸(열 과도의 시간) — 조건이 안 맞으면 뺀다.
        when = (extra.get("when") or {}).get(kind) or {}
        if any(
            (analysis.get(other) or Analysis.model_fields[other].default) != wanted
            for other, wanted in when.items()
        ):
            continue
        value = analysis.get(key)
        out[key] = field.default if value is None and field.default is not None else value
    return out
