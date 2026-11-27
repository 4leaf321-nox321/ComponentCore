"""해석 종류 등록부 — 종류마다 이름 · 안내 · 쓰는 칸 · **받는 항목** · 물리를 한 곳에
(ADR 0013).

손으로 흩어 적던 것을 여기서 만든다 — 종류 하나를 더할 때 열몇 곳을 고치지 않고 여기 한 줄을
더한다.

- 해석 설정(`Analysis`)의 칸마다 「어느 종류가 쓰나」(`only_for` — `analyses_with`).
- 하중 칸 중 그 종류에서만 쓰는 것(조화 응답의 주파수별 배율 · 위상 — 칸의 `analysis_only`,
  `analyses_using`).
- 받는 항목(구속 · 하중 · 초기조건 · 접촉의 종류)과 꼭 있어야 하는 항목 — 저장할 때 막는다
  (`conditions.model._check_accepted`). 받는 쪽의 능력표(`analyses.<종류>.loads` …)와 같은
  꼴이라, 대상 솔버가 정해지면 두 표를 겹쳐 거른다(설계 5장).
- 물리 — 필요한 물성(구조: 탄성계수 · 푸아송비 · 밀도)을 가른다(`materials.material_warnings`).
- 접촉을 선형화하는가(모드 · 주파수 영역 — `contact_check.eigen_notes`).

사양표(`spec()`)의 모양은 그대로라 화면 · MCP 는 바뀌지 않는다. **받는 항목은 지금 막는 것
그대로다** — 「모달은 하중을 안 쓴다」 「랜덤 진동은 가속도 PSD 밖의 하중을 안 쓴다」 처럼
안내만 하고 막지 않던 것은 아직 받는다(좁히는 것은 따로 정한다).

순서는 화면의 종류 목록 차례다(`ANALYSIS_LABELS`). 등록부는 조건 모듈을 import 하지 않는다 —
모델 쪽이 등록부로 칸을 만들기 때문이다. 이름이 어긋나면 시험이 잡는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

#: 조건 묶음과 그 이름 — 받는 항목을 적는 묶음.
GROUP_LABELS: dict[str, str] = {
    "constraints": "구속",
    "loads": "하중",
    "contacts": "접촉",
    "initial": "초기조건",
}

#: 묶음마다 있는 종류 — 모델(`Constraint` · `Load` · `Contact` · `Initial`)의 `type` 과 같다.
ITEMS: dict[str, tuple[str, ...]] = {
    "constraints": (
        "fixed_support",
        "displacement",
        "remote_displacement",
        "frictionless",
        "cylindrical",
        "compression_only",
        "elastic_support",
    ),
    "loads": (
        "pressure",
        "force",
        "moment",
        "bearing",
        "bolt_pretension",
        "standard_earth_gravity",
        "acceleration",
        "rotational_velocity",
        "psd_acceleration",
    ),
    "contacts": ("bonded", "no_separation", "frictional", "frictionless", "rough"),
    "initial": ("environment_temperature", "velocity", "temperature", "prestress"),
}

#: 받지 않는 종류를 저장하려 할 때 덧붙이는 까닭 — 없으면 「해석 종류를 바꾸거나 지우라」.
REFUSED_WHY: dict[tuple[str, str], str] = {
    # 바디 온도는 열 해석의 시작 상태다. 구조 해석에 걸면 열 하중이 되는데, 받는 쪽은
    # 열팽창을 넣지 않아 아직 거절한다(SimEngBay, 2026-11-18).
    ("initial", "temperature"): "구조 해석의 바디 온도(열 하중)는 해석 쪽이 아직 받지 "
    "않습니다. 온도에 따른 물성을 쓰려면 ‘환경 온도’를 지정하십시오.",
    # 조화 응답의 선응력은 두 솔버 모두 받지 않는다 — 받는 쪽이 말없이 무시하던 것(SimEngBay,
    # 2026-11-27). 모달 · 랜덤 진동은 받는다.
    ("initial", "prestress"): "조화 응답의 선응력은 해석 쪽이 받지 않습니다(CalculiX, Ansys "
    "모두). 선응력은 모달, 랜덤 진동에서 사용하십시오.",
    # 조화 응답에서 — 가진이 아니라 두 솔버 모두 작업을 만들 때 막는다(SimEngBay, 2026-11-27).
    ("loads", "bolt_pretension"): "조화 응답에서는 볼트 예압을 해석 쪽이 받지 않습니다"
    "(CalculiX, Ansys 모두). 체결 상태의 진동은 모달(선응력)로 확인하십시오.",
    ("loads", "rotational_velocity"): "조화 응답에서는 회전 속도를 해석 쪽이 받지 않습니다"
    "(CalculiX, Ansys 모두).",
    ("loads", "standard_earth_gravity"): "조화 응답에서는 중력을 해석 쪽이 받지 않습니다"
    "(CalculiX, Ansys 모두). 1 g로 가진하려면 가속도 하중을 사용하십시오.",
}


def _all_except(**refused: tuple[str, ...]) -> Mapping[str, tuple[str, ...]]:
    """묶음마다 받는 종류 — `refused` 에 적은 것만 뺀다."""
    unknown = {
        f"{group}.{one}"
        for group, ones in refused.items()
        for one in ones
        if one not in ITEMS.get(group, ())
    }
    if unknown:
        raise ValueError(f"등록부에 없는 종류: {', '.join(sorted(unknown))}")
    return MappingProxyType(
        {
            group: tuple(one for one in kinds if one not in refused.get(group, ()))
            for group, kinds in ITEMS.items()
        }
    )


@dataclass(frozen=True)
class Needed:
    """해석에 **하나 이상 있어야 하는** 항목 — 없으면 저장할 때 막는다."""

    group: str
    type: str
    why: str = ""


@dataclass(frozen=True)
class AnalysisKind:
    label: str
    note: str
    #: 이 종류가 쓰는 `Analysis` 의 칸 — 내보낼 때도 이 칸만 싣는다(`_filled_analysis`).
    fields: tuple[str, ...]
    #: 물리 — 필요한 물성을 가른다. 기구(다물체)는 3단계에서 더한다.
    physics: Literal["structural", "thermal"]
    #: 묶음마다 받는 종류(`_all_except`).
    accepts: Mapping[str, tuple[str, ...]]
    #: 하나 이상 있어야 하는 항목.
    needs: tuple[Needed, ...] = ()
    #: 묶음의 칸 중 **이 종류에서만** 쓰는 것 — 칸의 `analysis_only`(화면이 그때만 그린다).
    item_fields: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    #: 모드 · 주파수 영역 — 비선형 접촉(열림 · 미끄럼)을 풀지 않고 선형화한다.
    linearized: bool = False


_NOT_PSD = _all_except(loads=("psd_acceleration",), initial=("temperature",))

ANALYSES: dict[str, AnalysisKind] = {
    "modal": AnalysisKind(
        label="모달(고유진동)",
        note="구조물의 고유진동수와 모드 형상을 구합니다. 하중은 사용하지 않고 "
        "구속 조건과 물성(밀도)만 사용합니다.",
        fields=("modes", "frequency_range", "prestressed", "solver"),
        physics="structural",
        accepts=_NOT_PSD,
        linearized=True,
    ),
    "static": AnalysisKind(
        label="정적 구조",
        note="하중이 서서히 가해진 뒤 평형 상태의 변형과 응력을 계산합니다. "
        "접촉이나 대변형이 있으면 비선형으로 계산합니다.",
        # 하중 단계 · 수렴 · 출력(② 비선형 정적, SimEngBay 와 정함 2026-11-27) — 해석
        # 케이스에서만 쓰고, 받는 쪽이 받기 전에는 내보내기를 막는다(`steps`).
        fields=(
            "large_deflection",
            "steps",
            "substeps",
            "load_steps",
            "convergence",
            "outputs",
            "solver",
        ),
        physics="structural",
        accepts=_NOT_PSD,
        item_fields=MappingProxyType({"loads": ("time_table", "active_steps", "bolt_steps")}),
    ),
    "harmonic": AnalysisKind(
        label="조화 응답(주파수 응답)",
        note="지정한 주파수로 가진하는 하중에 대한 응답(진폭, 응력)을 주파수별로 "
        "계산합니다. 공진을 확인할 때 사용합니다. 하중마다 ‘주파수별 배율’로 사인 스윕 "
        "프로파일을 입력할 수 있습니다.",
        # 선응력(`prestressed` · 초기조건 `prestress`)은 두 솔버 모두 받지 않는다(SimEngBay,
        # 2026-11-27) — 칸을 내지 않는다. 케이스 사슬(정적 → 조화)로 받는 판에서 연다.
        fields=(
            "modes",
            "frequency_range",
            "solution_intervals",
            "method",
            "damping_ratio",
            "solver",
        ),
        physics="structural",
        # 볼트 예압 · 회전 속도 · 중력은 조화의 가진이 아니다 — 두 솔버 모두 작업을 만들 때
        # 막는다(SimEngBay, 2026-11-27 — 중력은 그쪽 사용자가 정했다. CalculiX 가 1 g 가진으로
        # 흔들던 것을 없앤다). 저장에서 먼저 막는다.
        accepts=_all_except(
            loads=(
                "psd_acceleration",
                "bolt_pretension",
                "rotational_velocity",
                "standard_earth_gravity",
            ),
            initial=("temperature", "prestress"),
        ),
        item_fields=MappingProxyType({"loads": ("frequency_table", "phase")}),
        linearized=True,
    ),
    "random": AnalysisKind(
        label="랜덤 진동(PSD)",
        note="고정 지지가 가속도 PSD로 흔들릴 때의 응답(변위, 응력의 1σ 값)을 모드 중첩으로 "
        "계산합니다. 진동 시험 규격(MIL-STD-810, IEC 60068-2-64)의 랜덤 프로파일을 옮길 때 "
        "사용합니다. 하중 ‘가속도 PSD’가 필요하며, 그 밖의 하중은 사용하지 않습니다.",
        fields=("modes", "frequency_range", "prestressed", "damping_ratio", "solver"),
        physics="structural",
        accepts=_all_except(initial=("temperature",)),
        needs=(
            Needed("loads", "psd_acceleration"),
            # 기저 가진은 선택 그룹이 아니라 고정 지지 전부를 흔든다.
            Needed("constraints", "fixed_support", "기저 가진은 고정 지지를 흔듭니다."),
        ),
        linearized=True,
    ),
    "explicit": AnalysisKind(
        label="명시적 동해석(충돌·낙하)",
        note="매우 짧은 시간(수 ms) 동안의 충돌, 낙하, 파손을 시간에 따라 "
        "계산합니다. 일반적으로 초기 속도가 필요합니다.",
        fields=("end_time", "output_count", "mass_scaling_dt"),
        physics="structural",
        accepts=_NOT_PSD,
    ),
    "thermal": AnalysisKind(
        label="열",
        note="열 전달에 따른 온도 분포를 계산합니다. 정상 상태 또는 시간에 따른 "
        "과도 상태를 해석합니다.",
        fields=("solver", "thermal_mode", "time_step", "end_time", "output_count"),
        physics="thermal",
        accepts=_all_except(loads=("psd_acceleration",)),
    ),
}


def analyses_with(name: str) -> list[str]:
    """해석 설정의 그 칸을 쓰는 종류 — 칸의 `only_for`. 등록부에 없는 칸 이름이면 시험이
    잡는다."""
    return [kind for kind, one in ANALYSES.items() if name in one.fields]


def analyses_using(group: str, name: str) -> list[str]:
    """묶음의 그 칸을 쓰는 종류 — 칸의 `analysis_only`."""
    return [kind for kind, one in ANALYSES.items() if name in one.item_fields.get(group, ())]


def accepting(group: str, type_: str) -> list[str]:
    """그 항목을 받는 종류."""
    return [kind for kind, one in ANALYSES.items() if type_ in one.accepts.get(group, ())]


def structural(kind: str | None) -> bool:
    """구조 해석인가 — 모르는 종류는 구조로 본다(구조 물성이 빠졌다고 말하는 쪽이 안전하다)."""
    one = ANALYSES.get(str(kind or "modal"))
    return one is None or one.physics == "structural"


def linearized() -> frozenset[str]:
    """접촉을 선형화하는 종류."""
    return frozenset(kind for kind, one in ANALYSES.items() if one.linearized)
