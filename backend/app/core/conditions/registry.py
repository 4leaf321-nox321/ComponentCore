"""해석 종류 등록부 — 종류마다 이름 · 안내 · **쓰는 칸**을 한 곳에(ADR 0013).

해석 설정(`Analysis`)의 칸마다 「어느 종류가 쓰나」(`only_for`)를 손으로 적던 것을 여기서
만든다(`analyses_with`). 종류 하나를 더할 때 칸 열몇 곳을 고치지 않고 여기 한 줄을 더한다 —
사양표(`spec()`)의 모양은 그대로라 화면 · MCP 는 바뀌지 않는다. 받는 항목(구속 · 하중 ·
초기조건 · 접촉의 종류)과 필요한 물성은 다음 차례다.

순서는 화면의 종류 목록 차례다(`ANALYSIS_LABELS`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisKind:
    label: str
    note: str
    #: 이 종류가 쓰는 `Analysis` 의 칸 — 내보낼 때도 이 칸만 싣는다(`_filled_analysis`).
    fields: tuple[str, ...]


ANALYSES: dict[str, AnalysisKind] = {
    "modal": AnalysisKind(
        label="모달(고유진동)",
        note="구조물의 고유진동수와 모드 형상을 구합니다. 하중은 사용하지 않고 "
        "구속 조건과 물성(밀도)만 사용합니다.",
        fields=("modes", "frequency_range", "prestressed", "solver"),
    ),
    "static": AnalysisKind(
        label="정적 구조",
        note="하중이 서서히 가해진 뒤 평형 상태의 변형과 응력을 계산합니다. "
        "접촉이나 대변형이 있으면 비선형으로 계산합니다.",
        fields=("large_deflection", "steps", "substeps", "solver"),
    ),
    "harmonic": AnalysisKind(
        label="조화 응답(주파수 응답)",
        note="지정한 주파수로 가진하는 하중에 대한 응답(진폭, 응력)을 주파수별로 "
        "계산합니다. 공진을 확인할 때 사용합니다. 하중마다 ‘주파수별 배율’로 사인 스윕 "
        "프로파일을 입력할 수 있습니다.",
        fields=(
            "modes",
            "frequency_range",
            "prestressed",
            "solution_intervals",
            "method",
            "damping_ratio",
            "solver",
        ),
    ),
    "random": AnalysisKind(
        label="랜덤 진동(PSD)",
        note="고정 지지가 가속도 PSD로 흔들릴 때의 응답(변위, 응력의 1σ 값)을 모드 중첩으로 "
        "계산합니다. 진동 시험 규격(MIL-STD-810, IEC 60068-2-64)의 랜덤 프로파일을 옮길 때 "
        "사용합니다. 하중 ‘가속도 PSD’가 필요하며, 그 밖의 하중은 사용하지 않습니다.",
        fields=("modes", "frequency_range", "prestressed", "damping_ratio", "solver"),
    ),
    "explicit": AnalysisKind(
        label="명시적 동해석(충돌·낙하)",
        note="매우 짧은 시간(수 ms) 동안의 충돌, 낙하, 파손을 시간에 따라 "
        "계산합니다. 일반적으로 초기 속도가 필요합니다.",
        fields=("end_time", "output_count", "mass_scaling_dt"),
    ),
    "thermal": AnalysisKind(
        label="열",
        note="열 전달에 따른 온도 분포를 계산합니다. 정상 상태 또는 시간에 따른 "
        "과도 상태를 해석합니다.",
        fields=("solver", "thermal_mode", "time_step", "end_time", "output_count"),
    ),
}


def analyses_with(field: str) -> list[str]:
    """그 칸을 쓰는 종류 — 칸의 `only_for`. 등록부에 없는 칸 이름이면 시험이 잡는다."""
    return [name for name, kind in ANALYSES.items() if field in kind.fields]
