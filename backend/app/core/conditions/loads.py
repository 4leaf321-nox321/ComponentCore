"""구속 · 하중 · 초기조건 — 종류 · 라벨 · 안내 · 모델과 그 점검 · 채우기.

`app.core.conditions` 를 나눈 것 — 밖에서는 패키지의 이름으로 부른다(`__init__`)."""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from app.core import units as unit_systems
from app.core.conditions.common import (
    GLOBAL_FRAMES,
    INPUT_SYSTEM,
    Base,
    ConditionError,
    Number,
    _extra,
)
from app.core.conditions.registry import ANALYSES, analyses_using

if TYPE_CHECKING:
    from app.core.conditions.model import Conditions


# ── 조건들 ────────────────────────────────────────────────────────────────────


#: 화면에 주는 표시 — **성분 칸**(방향마다 자유 · 고정(· 변위량) 중 고른다), 그리고 그 칸을
#: 쓰는 종류(`only_for`). 다른 종류면 화면이 그리지 않고, 종류를 바꾸면 기본값으로 되돌린다.
#: `dimension` — 값의 단위가 단위계의 어느 이름인가(화면이 「변위량 (m)」 로 붙인다), `unit` —
#: 계와 상관없는 단위.
_DISPLACEMENT: dict[str, Any] = {
    "component": True,
    "only_for": ["displacement", "remote_displacement"],
    "dimension": "length",
}
_ROTATION: dict[str, Any] = {
    "component": True,
    "only_for": ["remote_displacement"],
    "unit": "도",
}
_CYLINDER: dict[str, Any] = {"component": True, "only_for": ["cylindrical"]}

Hold = Literal["fixed", "free"]

#: 종류가 **스스로 정하는** 방향 — 고칠 수 없지만 화면이 잠긴 칸으로 보여 준다. 어느 방향이
#: 어떻게 잡히는지 모르고 고르면, 풀리지 않는 모델(강체 운동)이나 과구속을 만든다.
IMPLIED_HOLDS: dict[str, list[dict[str, str]]] = {
    "fixed_support": [
        {
            "label": "X",
            "hold": "fixed",
            "hint": "모든 방향의 이동을 구속합니다. 좌표계와 무관합니다.",
        },
        {"label": "Y", "hold": "fixed", "hint": ""},
        {"label": "Z", "hold": "fixed", "hint": ""},
        {
            "label": "회전",
            "hold": "fixed",
            "hint": "셸·빔 요소는 회전도 구속합니다(솔리드 요소에는 회전 자유도가 없습니다).",
        },
    ],
    "frictionless": [
        {
            "label": "법선",
            "hold": "fixed",
            "hint": "면에 수직인 방향입니다. 면을 관통하거나 면에서 분리될 수 없습니다.",
        },
        {
            "label": "접선",
            "hold": "free",
            "hint": "면을 따르는 두 방향입니다. 마찰 없이 미끄러집니다.",
        },
    ],
    "compression_only": [
        {
            "label": "압축 방향",
            "hold": "fixed",
            "hint": "법선 방향으로 면을 관통할 수 없습니다.",
        },
        {
            "label": "분리 방향",
            "hold": "free",
            "hint": "면에서 분리될 수 있습니다(비선형, 반복 계산).",
        },
        {"label": "접선", "hold": "free", "hint": "면을 따라 마찰 없이 미끄러집니다."},
    ],
    "elastic_support": [
        {
            "label": "법선",
            "hold": "spring",
            "hint": "면에 수직인 방향입니다. 기초 강성에 비례하여 저항합니다.",
        },
        {"label": "접선", "hold": "free", "hint": "면을 따르는 방향으로는 지지하지 않습니다."},
    ],
}


CONSTRAINT_LABELS: dict[str, str] = {
    "fixed_support": "고정 지지",
    "displacement": "변위",
    "remote_displacement": "원격 변위",
    "frictionless": "마찰 없는 지지",
    "cylindrical": "원통 지지",
    "compression_only": "압축 전용 지지",
    "elastic_support": "탄성 지지",
}

#: 종류마다 한 줄 — 화면이 종류 아래에 보인다.
CONSTRAINT_NOTES: dict[str, str] = {
    "fixed_support": (
        "모든 자유도를 구속합니다. 볼트로 체결된 바닥면이나 용접된 끝단에 사용합니다."
    ),
    "displacement": (
        "방향별로 자유, 고정 또는 변위량을 지정합니다. 한 방향만 지지하거나 "
        "지정한 변위를 부여할 때 사용합니다."
    ),
    "remote_displacement": (
        "면을 한 점에 연결하고 그 점의 이동과 회전을 지정합니다. 축을 중심으로 한 "
        "회전을 허용할 때 사용합니다."
    ),
    "frictionless": (
        "면의 법선 방향만 구속하고 미끄러짐은 허용합니다. 대칭면이나 마찰이 없는 "
        "바닥에 사용합니다."
    ),
    "cylindrical": (
        "구멍이나 축의 반지름, 축, 접선 방향을 각각 구속하거나 해제합니다. 핀이 "
        "끼워진 구멍에 사용합니다."
    ),
    "compression_only": (
        "압축 방향만 지지하고 분리는 허용합니다. 고정 없이 올려 둔 부품에 사용합니다(비선형)."
    ),
    "elastic_support": "면을 스프링으로 지지합니다. 고무 패드나 지반에 사용합니다.",
}


class Constraint(Base):
    """구속 — 움직이지 못하게 한다.

    방향을 누가 정하나: `displacement` 는 좌표계(`cs`)의 X · Y · Z 마다, `remote_displacement`
    는 거기에 회전 X · Y · Z 까지, `cylindrical` 은 원통의 반지름 · 축 · 접선마다 사람이
    고른다. 나머지는 종류가 정한다(`IMPLIED_HOLDS`)."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal[
        "fixed_support",
        "displacement",
        "remote_displacement",
        "frictionless",
        "cylindrical",
        "compression_only",
        "elastic_support",
    ] = Field(json_schema_extra=_extra({"labels": CONSTRAINT_LABELS}))
    on: str = Field(title="선택 그룹")
    cs: str = Field(
        "global",
        json_schema_extra=_extra({"only_for": ["displacement", "remote_displacement"]}),
    )
    """성분의 축 — 변위 · 원격 변위만 쓴다(원통 지지는 원통의 축을, 나머지는 면을
    따른다). 원격 변위는 이 좌표계의 **원점**을 원격점으로 쓸 수도 있다(`location`)."""
    location: Literal["centroid", "cs_origin"] = Field(
        "centroid",
        title="원격점",
        description=(
            "면을 연결하는 한 점입니다. 선택한 면의 중심 또는 좌표계의 원점을 사용합니다."
        ),
        json_schema_extra=_extra(
            {
                "only_for": ["remote_displacement"],
                "labels": {"centroid": "선택 그룹의 중심", "cs_origin": "좌표계의 원점"},
            }
        ),
    )
    behavior: Literal["deformable", "rigid"] = Field(
        "deformable",
        title="면의 거동",
        description=(
            "변형체: 면이 하중에 따라 변형됩니다. 강체: 면이 형상을 유지한 채 이동합니다"
            "(강성이 더 높습니다)."
        ),
        json_schema_extra=_extra(
            {
                "only_for": ["remote_displacement"],
                "labels": {"deformable": "변형체", "rigid": "강체"},
            }
        ),
    )
    x: Number | None = Field(
        None, title="X", description="좌표계의 X축 방향", json_schema_extra=_DISPLACEMENT
    )
    y: Number | None = Field(
        None, title="Y", description="좌표계의 Y축 방향", json_schema_extra=_DISPLACEMENT
    )
    z: Number | None = Field(
        None, title="Z", description="좌표계의 Z축 방향", json_schema_extra=_DISPLACEMENT
    )
    """`displacement` · `remote_displacement` 의 이동 성분. **`null` 은 자유, 0 은 고정**, 그
    밖의 값은 그만큼 움직인다.

    화면은 빈칸 · 0 을 묵시적으로 읽게 두지 않고 「자유 · 고정 · 변위량」 을 고르게 한다
    (`component`) — 둘을 헷갈리면 구속이 통째로 바뀐다."""
    rx: Number | None = Field(
        None, title="회전 X", description="X축 기준 회전(도)", json_schema_extra=_ROTATION
    )
    ry: Number | None = Field(
        None, title="회전 Y", description="Y축 기준 회전(도)", json_schema_extra=_ROTATION
    )
    rz: Number | None = Field(
        None, title="회전 Z", description="Z축 기준 회전(도)", json_schema_extra=_ROTATION
    )
    """`remote_displacement` 의 회전 성분(도) — 뜻은 이동과 같다(`null` 자유 · 0 고정)."""
    stiffness: Number | None = Field(
        None,
        title="기초 강성",
        description="법선 방향으로 1 mm 변형시키는 데 필요한 압력입니다(N/mm³ = MPa/mm).",
        json_schema_extra=_extra({"only_for": ["elastic_support"]}),
    )
    """`elastic_support` 의 스프링 — 단위 면적 · 단위 변위당 힘(응력 / 길이)."""
    radial: Hold = Field(
        "fixed",
        title="반지름",
        description=(
            "원통 중심에서 바깥쪽을 향하는 방향으로, 구멍이 커지거나 작아지는 방향입니다."
        ),
        json_schema_extra=_CYLINDER,
    )
    axial: Hold = Field(
        "fixed",
        title="축",
        description="원통 축을 따르는 방향으로, 빠지거나 삽입되는 방향입니다.",
        json_schema_extra=_CYLINDER,
    )
    tangential: Hold = Field(
        "fixed",
        title="접선",
        description=(
            "원통 축을 중심으로 회전하는 방향입니다. 해제하면 핀에 끼워진 상태로 회전합니다."
        ),
        json_schema_extra=_CYLINDER,
    )
    """`cylindrical` 의 방향마다 고정(`fixed`) · 자유(`free`). 기본은 셋 다 고정."""


#: 하중 종류 → 크기의 차원(단위계 이름표의 열쇠). 화면은 「크기 (MPa)」 로 붙이고, 조건을 풀 때
#: `unit` 을 이것으로 채운다 — 사람이 단위를 손으로 적으면 계와 어긋나도 아무도 모른다.
LOAD_DIMENSIONS: dict[str, str] = {
    "pressure": "stress",
    "force": "force",
    "moment": "moment",
    "bearing": "force",
    "acceleration": "acceleration",
    "rotational_velocity": "angular_velocity",
}

#: 몸 전체에 걸리는 하중 — 선택 그룹이 없다.
BODY_LOADS = ("standard_earth_gravity", "acceleration", "rotational_velocity")
#: 선택 그룹이 없는 하중 — 몸 전체, 그리고 기저 가진(고정 지지 전부를 흔든다).
UNTARGETED_LOADS = (*BODY_LOADS, "psd_acceleration")

#: 가속도 PSD 의 단위 — **어느 계로 내보내든 g²/Hz** 다. 진동 시험 규격(MIL-STD-810 ·
#: IEC 60068-2-64)이 이것으로 적고, (mm/s²)²/Hz 로 받으면 사람이 9.6e7 을 곱해 적어야 한다.
#: g = 9.80665 m/s². 값에서 단위를 떼지 않으므로 하중의 `unit` 으로 함께 나간다.
PSD_UNIT = "g^2/Hz"

#: 조화 응답에서 주파수마다 크기를 달리할 수 있는 하중(`frequency_table` · `phase`) — 방향이
#: 있고 크기가 하나인 것. 중력 · 회전 속도는 가진이 아니다.
HARMONIC_LOADS = ["pressure", "force", "moment", "bearing", "acceleration"]

#: DOE 고르기 인자가 하중의 `direction` 칸에 줄 수 있는 **축 이름** → 좌표계(`cs`) 성분.
#: X · Y · Z 를 한 축씩 따로 거는 진동 · 충격 시험(IEC)을 설계점마다 한 축으로 나눈다 — 한
#: 조건의 가진은 동시라 축 셋을 한 조건에 넣으면 합산된다(SimEngBay, 2026-11-17). 점 파일에는
#: 성분으로 나간다.
AXIS_CHOICES: dict[str, list[int]] = {
    "x": [1, 0, 0],
    "y": [0, 1, 0],
    "z": [0, 0, 1],
    "-x": [-1, 0, 0],
    "-y": [0, -1, 0],
    "-z": [0, 0, -1],
}
AXIS_LABELS = {"x": "X축", "y": "Y축", "z": "Z축", "-x": "-X축", "-y": "-Y축", "-z": "-Z축"}

#: 방향이 있는 하중(벡터). 압력만 「면의 법선」 을 고를 수 있다.
DIRECTED_LOADS = [
    "pressure",
    "force",
    "moment",
    "bearing",
    "standard_earth_gravity",
    "acceleration",
    "rotational_velocity",
    "psd_acceleration",
]

#: 종류마다 한 줄 — 화면이 종류 아래에 보인다(무엇이고, 방향이 무엇을 뜻하나).
LOAD_NOTES: dict[str, str] = {
    "pressure": (
        "면에 균일하게 작용하는 힘입니다. 방향이 면의 법선이면 양수가 면을 누르는 방향입니다."
    ),
    "force": (
        "합력입니다. 여러 면에 적용하면 면들이 나누어 받습니다(면마다 이 크기가 "
        "적용되지 않습니다)."
    ),
    "moment": "비틀림 하중입니다. 방향은 회전축이며, 오른손 법칙을 따릅니다.",
    "bearing": (
        "핀이 구멍 안쪽을 미는 힘입니다. 하중 방향 쪽 반원에만 작용하며, 원통면에 적용합니다."
    ),
    "bolt_pretension": (
        "볼트에 예압을 가합니다. 먼저 체결한 뒤 그 길이를 고정한 상태에서 다른 "
        "하중을 적용합니다."
    ),
    "standard_earth_gravity": (
        "모든 바디의 자중입니다(9.80665 m/s²). 밀도가 지정되어야 적용됩니다."
    ),
    "acceleration": (
        "모델이 이 방향으로 가속됩니다. 관성력은 반대 방향으로 작용하며, 밀도가 필요합니다. "
        "조화 응답에서 고정 지지와 함께 사용하면 기저 가진(지지부 기준 상대 응답)과 같습니다."
    ),
    "rotational_velocity": (
        "좌표계 원점을 지나는 축을 중심으로 회전합니다(원심력). 밀도가 필요합니다."
    ),
    "psd_acceleration": (
        "랜덤 진동 해석에서 모든 고정 지지를 이 방향으로 흔듭니다. 주파수(Hz)마다 가속도 "
        "PSD(g²/Hz)를 입력하며, 사이 주파수는 로그-로그로 보간합니다. 축마다 따로 시험하는 "
        "규격이면 축마다 해석을 나누십시오(같은 해석의 여러 PSD는 서로 무관하게 합산됩니다)."
    ),
}

LOAD_LABELS: dict[str, str] = {
    "pressure": "압력",
    "force": "힘",
    "moment": "모멘트",
    "bearing": "베어링 하중",
    "bolt_pretension": "볼트 예압",
    "standard_earth_gravity": "중력",
    "acceleration": "가속도",
    "rotational_velocity": "회전 속도",
    "psd_acceleration": "가속도 PSD(기저 가진)",
}


class Load(Base):
    """하중 — 밀거나 당기거나 조인다.

    크기의 단위는 **단위계가 정한다**(`LOAD_DIMENSIONS`) — 적지 않으면 풀 때 채우고, 적었는데
    계와 다르면 막는다. 볼트만 예압(힘) · 조임량(길이)을 `unit` 으로 고른다."""

    name: str = Field(min_length=1, max_length=60)
    type: Literal[
        "pressure",
        "force",
        "moment",
        "bearing",
        "bolt_pretension",
        "standard_earth_gravity",
        "acceleration",
        "rotational_velocity",
        "psd_acceleration",
    ] = Field(json_schema_extra=_extra({"labels": LOAD_LABELS}))
    on: str = Field(
        "",
        title="선택 그룹",
        json_schema_extra=_extra(
            {"only_for": ["pressure", "force", "moment", "bearing", "bolt_pretension"]}
        ),
    )
    """중력처럼 온 몸에 걸리는 것은 비어 있다."""
    cs: str = Field(
        "global",
        json_schema_extra=_extra({"only_for": [*DIRECTED_LOADS, "bolt_pretension"]}),
    )
    """방향 성분의 축 — 구속과 같다. 회전 속도는 이 좌표계의 원점을 지나는 축으로 돈다.

    **바디에 건 볼트 예압**은 이것이 단면이다 — Z 축이 볼트 축, 원점이 단면 자리(축에 수직인
    평면이 원점을 지난다). Ansys 의 바디 예압과 같은 뜻이라 SimEngBay 의 두 솔버가 그대로
    쓴다(2026-10-28 에 정했다). 원통면에 건 예압은 면이 축과 자리를 정하므로 비운다."""
    magnitude: Number | None = Field(
        None,
        title="크기",
        json_schema_extra=_extra(
            {
                "only_for": [
                    k
                    for k in LOAD_LABELS
                    if k
                    not in ("bolt_pretension", "standard_earth_gravity", "psd_acceleration")
                ],
                "unit_by_type": True,
            }
        ),
    )
    unit: str = Field("", json_schema_extra=_extra({"hidden": True}))
    """`MPa` · `N` · `N*mm` … **단위를 값에서 떼지 않는다** — 물성에서 그것이 10¹² 배로
    틀린 적이 있다(MatNexus 의 실측). 비우면 단위계에서 채운다."""
    direction: list[Number] | Literal["normal"] | None = Field(
        None,
        title="방향",
        json_schema_extra=_extra(
            {
                "direction": True,
                "only_for": DIRECTED_LOADS,
                "normal_for": ["pressure"],
                "axes": AXIS_LABELS,
            }
        ),
    )
    """좌표계(`cs`)의 X · Y · Z 성분(길이는 상관없다), 또는 `"normal"`(면의 법선 — 압력만).
    비우면 압력은 법선, 중력은 -Z 다."""
    preload: Number | None = Field(
        None,
        title="예압",
        json_schema_extra=_extra({"only_for": ["bolt_pretension"], "bolt": True}),
    )
    """`bolt_pretension` — 예압(힘) 또는 조임량(길이), `unit` 이 가른다."""
    frequency_table: list[list[Number]] | None = Field(
        None,
        title="주파수별 배율",
        description="조화 응답에서 주파수마다 ‘크기’에 곱할 배율입니다. 사이 주파수는 선형 "
        "보간하며, 표는 해석의 주파수 범위를 모두 포함해야 합니다. 비워 두면 모든 주파수에서 "
        "배율 1입니다. 예: 가속도 1 g(9806.65 mm/s²)에 200 Hz 0.5, 800 Hz 1.",
        json_schema_extra=_extra(
            {
                "only_for": HARMONIC_LOADS,
                "analysis_only": analyses_using("loads", "frequency_table"),
                "table": {"columns": [{"title": "주파수", "unit": "Hz"}, {"title": "배율"}]},
            }
        ),
    )
    """조화 응답 — `[[주파수(Hz), 배율], …]`, 주파수가 커지는 순서. 크기 * 배율이 그 주파수의
    진폭이다(CalculiX `*AMPLITUDE` 와 같은 뜻, Ansys 는 곱해서 표로). `None` 이면 배율 1."""
    phase: Number | None = Field(
        None,
        title="위상",
        description="조화 응답에서 이 하중의 위상각입니다. 비워 두면 0°입니다.",
        json_schema_extra=_extra(
            {
                "only_for": HARMONIC_LOADS,
                "analysis_only": analyses_using("loads", "phase"),
                "unit": "°",
            }
        ),
    )
    psd_table: list[list[Number]] | None = Field(
        None,
        title="가속도 PSD",
        description="주파수(Hz)마다 가속도 PSD(g²/Hz)입니다. 두 행 이상, 주파수가 커지는 "
        "순서로 입력합니다. 사이 주파수는 로그-로그로 보간하고, 표 밖의 주파수는 가진하지 "
        "않습니다. 엑셀에서 두 열을 복사해 붙여 넣을 수 있습니다.",
        json_schema_extra=_extra(
            {
                "only_for": ["psd_acceleration"],
                "table": {
                    "columns": [
                        {"title": "주파수", "unit": "Hz"},
                        {"title": "PSD", "unit": "g²/Hz"},
                    ],
                    "grms": True,
                },
            }
        ),
    )
    """랜덤 진동 — `[[주파수(Hz), PSD(g²/Hz)], …]`, 로그-로그 보간(규격의 dB/oct 기울기가 곧
    로그-로그 직선이다). 내보낼 때 `grms`(표의 면적, g)를 함께 싣는다 — 받는 쪽이 적분을 맞춰
    본다."""
    curve: str = Field(
        "",
        title="곡선",
        description="주파수별 배율이나 가속도 PSD 를 표 대신 곡선(이름)으로 가리킵니다. "
        "내보낼 때 곡선의 점을 표로 풀어 싣습니다.",
        json_schema_extra=_extra(
            {"only_for": [*HARMONIC_LOADS, "psd_acceleration"], "hidden": True}
        ),
    )
    """곡선 이름(`curves[].name`) — 표 칸(`frequency_table` · `psd_table`)을 대신한다. 둘을
    함께 적지 않는다(`curves.check_uses`). 내보낼 때 풀려 이 칸은 나가지 않는다."""


INITIAL_LABELS: dict[str, str] = {
    "environment_temperature": "환경 온도",
    "temperature": "초기 온도",
    "velocity": "초기 속도",
    "prestress": "선응력(프리스트레스)",
}

INITIAL_NOTES: dict[str, str] = {
    "environment_temperature": (
        "모델 전체의 기준 온도로, 열팽창이 0인 온도입니다(일반적으로 22 °C). 물성에 온도별 "
        "값이 있으면 이 온도에 가장 가까운 값으로 계산합니다(없으면 22 °C)."
    ),
    "temperature": "선택한 바디의 시작 온도입니다. 과도 열 해석의 초기 상태로 사용하며, 열 "
    "해석에서만 지정할 수 있습니다.",
    "velocity": (
        "선택한 바디가 이 속도로 움직이는 상태에서 시작합니다. 낙하·충돌(explicit) "
        "해석에 사용합니다."
    ),
    "prestress": "선행 정적 해석의 응력을 반영한 상태에서 시작합니다. 볼트 체결이나 "
    "원심력이 고유진동수에 영향을 줄 때 사용합니다(모달).",
}


class Initial(Base):
    """초기조건 — 풀기 전의 상태."""

    type: Literal["environment_temperature", "velocity", "temperature", "prestress"] = Field(
        json_schema_extra=_extra({"labels": INITIAL_LABELS})
    )
    on: str = Field(
        "",
        title="바디 선택 그룹",
        json_schema_extra=_extra({"only_for": ["temperature", "velocity"]}),
    )
    value: Number | None = Field(
        None,
        title="온도",
        json_schema_extra=_extra(
            {
                "only_for": ["environment_temperature", "temperature"],
                "unit": "°C",
            }
        ),
    )
    vector: list[Number] | None = Field(
        None,
        title="속도",
        description="전역 X, Y, Z 성분",
        json_schema_extra=_extra(
            {"only_for": ["velocity"], "unit": "mm/s", "components": True}
        ),
    )
    unit: str = Field("", json_schema_extra=_extra({"hidden": True}))
    """내보낼 때 채운다(온도 `C`, 속도 `<길이>/s`)."""
    from_step: str = Field(
        "",
        title="선행 정적 해석",
        description="응력을 가져올 해석의 이름입니다. 비워 두면 해석 프로그램이 이 모델의 "
        "정적 해석을 사용합니다.",
        json_schema_extra=_extra({"only_for": ["prestress"]}),
    )


def _load_units(load_type: str, system: str = INPUT_SYSTEM) -> list[str]:
    """이 하중이 받을 수 있는 크기 단위 — 계가 정한다. 볼트는 예압(힘) · 조임량(길이) 둘."""
    names = unit_systems.system_of(system).names
    if load_type == "bolt_pretension":
        return [names["force"], names["length"]]
    if load_type == "psd_acceleration":
        return [PSD_UNIT]
    dimension = LOAD_DIMENSIONS.get(load_type)
    return [names[dimension]] if dimension else []


def _check_load(where: str, load: Load) -> None:
    """하중 하나 — 빠진 값 · 계와 다른 단위 · 쓸 수 없는 방향을 **저장할 때** 말한다.

    안 그러면 크기 없는 하중이나 0 벡터가 내보내져, 받는 쪽이 하중 없는 해석을 끝까지 돌린다.
    """
    label = f"{LOAD_LABELS[load.type]} ‘{load.name}’"
    if load.type not in UNTARGETED_LOADS and not load.on:
        raise ConditionError(f"{where}: {label}에 선택 그룹이 없습니다.")
    if load.type == "psd_acceleration":
        if not load.psd_table:
            raise ConditionError(f"{where}: {label}에 PSD 표가 없습니다.")
        _check_table(f"{where}: {label}의 PSD 표", load.psd_table, low=0.0, positive=True)
    if load.frequency_table:
        _check_table(f"{where}: {label}의 주파수별 배율", load.frequency_table, low=None)
    if load.type in LOAD_DIMENSIONS and load.magnitude is None:
        raise ConditionError(f"{where}: {label}에 크기가 없습니다.")
    if load.type == "bolt_pretension" and load.preload is None:
        raise ConditionError(f"{where}: {label}에 예압(또는 조임량)이 없습니다.")
    allowed = _load_units(load.type)
    if load.unit and load.unit not in allowed:
        raise ConditionError(
            f"{where}: {label}의 단위 ‘{load.unit}’은(는) 사용할 수 없습니다. 조건 값은 "
            f"mm·N·t 단위로 입력합니다({' 또는 '.join(allowed) or '단위 없음'})."
        )
    direction = load.direction
    if direction == "normal" and load.type != "pressure":
        raise ConditionError(f"{where}: 면의 법선 방향은 압력에만 사용할 수 있습니다.")
    if isinstance(direction, list):
        if len(direction) != 3:
            raise ConditionError(f"{where}: 방향은 X, Y, Z 세 성분으로 지정해야 합니다.")
        numbers = [one for one in direction if not isinstance(one, str)]
        if len(numbers) == 3 and all(one == 0 for one in numbers):
            raise ConditionError(f"{where}: {label}의 방향이 0 벡터입니다.")
    elif (
        direction is None
        and load.type in DIRECTED_LOADS
        and load.type
        not in (
            "pressure",
            "standard_earth_gravity",
        )
    ):
        raise ConditionError(f"{where}: {label}에 방향이 없습니다.")


#: 표의 가로축 이름 — 오류 문구의 조사까지(「주파수와 값」 · 「시간과 값」).
_AXIS_WORDS: dict[str, tuple[str, str]] = {
    "주파수": ("주파수와", "주파수는"),
    "시간": ("시간과", "시간은"),
    "단계": ("단계와", "단계는"),
}


def _topic(word: str) -> str:
    """주제 조사 — 끝 글자에 받침이 있으면 「은」, 없으면 「는」, 한글이 아니면 「은(는)」."""
    last = word[-1:]
    if "가" <= last <= "힣":
        return "은" if (ord(last) - ord("가")) % 28 else "는"
    return "은(는)"


def _check_table(
    label: str,
    table: list[list[Any]],
    *,
    low: float | None,
    positive: bool = False,
    signed: bool = False,
    axis: str = "주파수",
) -> None:
    """표 — 두 열, 두 행 이상, 가로축(`axis`, 기본 주파수)이 커지는 순서. `low` 는 가로축이
    넘어야 할 값(PSD 는 로그라 0 을 못 쓴다), `positive` 면 값도 0 보다 커야 한다(로그-로그
    보간). 배율은 0 이상(음수는 위상으로 준다) — `signed` 면 값의 부호를 보지 않는다(하중
    이력). 식(`"=…"`)인 칸은 설계점마다 풀리므로 여기서는 넘어간다."""
    pair, topic = _AXIS_WORDS[axis]
    if len(table) < 2:
        raise ConditionError(f"{label}{_topic(label)} 두 행 이상이어야 합니다.")
    before: float | None = None
    for row, one in enumerate(table, start=1):
        if len(one) != 2:
            raise ConditionError(f"{label} {row}행은 {pair} 값 두 칸이어야 합니다.")
        where, value = one
        if any(isinstance(cell, str) and not cell.startswith("=") for cell in one):
            raise ConditionError(
                f"{label} {row}행: 빈칸이 있습니다. 수 또는 =식을 입력하십시오."
            )
        if not isinstance(where, str):
            if where < 0 or (low is not None and where <= low):
                floor = "0보다 커야" if low is not None else "0 이상이어야"
                raise ConditionError(f"{label} {row}행: {topic} {floor} 합니다.")
            if before is not None and where <= before:
                raise ConditionError(
                    f"{label} {row}행: {topic} 위 행보다 커야 합니다({before} → {where})."
                )
            before = float(where)
        if signed or isinstance(value, str):
            continue
        if value <= 0 if positive else value < 0:
            what = "0보다 커야" if positive else "0 이상이어야"
            raise ConditionError(f"{label} {row}행: 값은 {what} 합니다.")


def _span_of(table: list[list[Any]]) -> tuple[float, float] | None:
    """표가 덮는 주파수 — 식이 섞이면 모른다(`None`)."""
    ends = [table[0][0], table[-1][0]] if table else []
    if len(ends) != 2 or any(isinstance(one, str) for one in ends):
        return None
    return float(ends[0]), float(ends[1])


def _check_excitation(conditions: Conditions) -> None:
    """가진 — 해석 종류와 하중의 값이 맞물리는가. 받는 항목 · 꼭 있어야 하는 항목(가속도 PSD 는
    랜덤 진동에서만, 랜덤 진동에는 가속도 PSD · 고정 지지)은 등록부가 든다(`_check_accepted`).

    - 랜덤 진동은 **감쇠비**가 있어야 한다 — 감쇠가 없으면 공진에서 응답이 무한하다.
    - 조화 응답의 주파수별 배율은 해석의 주파수 범위를 **다 덮어야** 한다 — 표 밖을 0 으로
      읽을지 끝값으로 읽을지 솔버마다 다르다.
    """
    analysis = conditions.analysis
    if analysis.type == "random":
        damping = analysis.damping_ratio
        if damping is None or (not isinstance(damping, str) and damping <= 0):
            raise ConditionError(
                "analysis: 랜덤 진동에는 감쇠비가 필요합니다(예: 0.02). 감쇠가 없으면 "
                "공진에서 응답이 무한히 커집니다."
            )
    span = analysis.frequency_range
    if analysis.type != "harmonic" or not span or len(span) != 2:
        return
    low, high = span
    if isinstance(low, str) or isinstance(high, str):
        return
    for index, load in enumerate(conditions.loads):
        if not load.frequency_table:
            continue
        covered = _span_of(load.frequency_table)
        if covered and (covered[0] > low or covered[1] < high):
            raise ConditionError(
                f"loads[{index}]: {LOAD_LABELS[load.type]} ‘{load.name}’의 주파수별 배율"
                f"({covered[0]:g}~{covered[1]:g} Hz)이 해석의 주파수 범위"
                f"({float(low):g}~{float(high):g} Hz)를 모두 포함하지 않습니다."
            )


def psd_grms(table: list[list[Any]]) -> float | None:
    """가속도 PSD 표의 **실효값**(g) — 로그-로그 보간한 면적의 제곱근. 규격이 함께 적는
    「Grms 6.06」 과 맞춰 보는 값이다. 식이 섞여 있으면 `None`.

    구간마다 PSD 가 `f^n` 꼴(로그-로그 직선)이므로 면적은 `P1·f1/(n+1)·((f2/f1)^(n+1) - 1)`,
    `n = -1` 이면 `P1·f1·ln(f2/f1)` 이다."""
    rows = [(one[0], one[1]) for one in table]
    if len(rows) < 2 or any(isinstance(x, str) or isinstance(y, str) for x, y in rows):
        return None
    area = 0.0
    for (f1, p1), (f2, p2) in itertools.pairwise(rows):
        f1, p1, f2, p2 = float(f1), float(p1), float(f2), float(p2)
        if f1 <= 0 or f2 <= f1 or p1 <= 0 or p2 <= 0:
            return None
        n = math.log(p2 / p1) / math.log(f2 / f1)
        if abs(n + 1) < 1e-9:
            area += p1 * f1 * math.log(f2 / f1)
        else:
            area += p1 * f1 / (n + 1) * ((f2 / f1) ** (n + 1) - 1)
    return math.sqrt(area)


def _check_section(where: str, load: Load, on_body: bool) -> None:
    """볼트 예압의 **단면을 누가 정하나** — 바디면 좌표계(Z = 볼트 축, 원점 = 단면 자리),
    원통면이면 면. 바디 예압에 좌표계가 없으면 받는 쪽이 축 위 어디를 자를지 모르고(머리 ·
    너트가 한 바디거나 볼트가 짧으면 축도 틀린다 — SimEngBay), 원통면에 좌표계를 함께 주면
    둘 중 무엇을 따를지 모른다."""
    label = f"볼트 예압 ‘{load.name}’"
    if on_body and load.cs in GLOBAL_FRAMES:
        raise ConditionError(
            f"{where}: 바디에 건 {label}에는 좌표계가 있어야 합니다 — Z 축이 볼트 축, 원점이 "
            "단면 자리입니다(축에 수직인 평면이 원점을 지납니다)."
        )
    if not on_body and load.cs not in GLOBAL_FRAMES:
        raise ConditionError(
            f"{where}: 원통면에 건 {label}은(는) 면이 축과 단면 자리를 정합니다 — 좌표계를 "
            "비우십시오."
        )


def _check_initial(where: str, initial: Initial) -> None:
    """초기조건 하나 — 종류에 빠진 값을 **저장할 때** 말한다."""
    label = INITIAL_LABELS[initial.type]
    if initial.type in ("environment_temperature", "temperature") and initial.value is None:
        raise ConditionError(f"{where}: {label}에 온도가 없습니다.")
    if initial.type in ("temperature", "velocity") and not initial.on:
        raise ConditionError(f"{where}: {label}에 바디 선택 그룹이 없습니다.")
    if initial.type == "velocity" and (not initial.vector or len(initial.vector) != 3):
        raise ConditionError(f"{where}: {label}에 속도(X, Y, Z)가 없습니다.")


def _filled_initial(initial: dict[str, Any], system: str) -> dict[str, Any]:
    """내보낼 초기조건 — 단위를 내보내기 계의 이름으로(온도는 어느 계든 °C)."""
    out = dict(initial)
    names = unit_systems.system_of(system).names
    if out.get("type") in ("environment_temperature", "temperature"):
        out["unit"] = names["temperature"]
    elif out.get("type") == "velocity":
        out["unit"] = f"{names['length']}/s"
    return out


def _filled_load(load: dict[str, Any], system: str, analysis: str = "") -> dict[str, Any]:
    """내보낼 하중 — 단위는 **내보내기 계의 이름**으로, 비운 방향은 **뜻대로 채운다.** 받는
    쪽이 기본값을 짐작하지 않게. 볼트는 적힌 단위(입력 계의 N · mm)로 예압 · 조임량을
    가른다. 조화 응답이면 비운 위상을 0 으로, 가속도 PSD 는 표의 실효값(`grms`, g)을 싣는다."""
    out = dict(load)
    registered = ANALYSES.get(analysis)
    if (
        registered is not None
        and "phase" in registered.item_fields.get("loads", ())
        and out.get("type") in HARMONIC_LOADS
        and out.get("phase") is None
    ):
        out["phase"] = 0.0
    if out.get("type") == "psd_acceleration":
        out["grms"] = psd_grms(out.get("psd_table") or [])
    kind = str(out.get("type"))
    target = _load_units(kind, system)
    if kind == "bolt_pretension":
        by_length = out.get("unit") == unit_systems.system_of(INPUT_SYSTEM).names["length"]
        out["unit"] = target[1 if by_length else 0]
    elif target:
        out["unit"] = target[0]
    if out.get("direction") is None:
        if out.get("type") == "pressure":
            out["direction"] = "normal"
        elif out.get("type") == "standard_earth_gravity":
            out["direction"] = [0, 0, -1]
    return out
