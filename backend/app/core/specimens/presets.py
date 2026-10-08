"""시험 규격 **프리셋** — 시편 치수 · 시험 지그의 규칙 · 해석 기본값 한 벌.

공개 규격(ASTM · ISO)은 이 패키지의 `data/*.json` 에 있고(저장소 — 모든 서버가 같다), 사내
규격은 DB(`modules/specimens`)에 **같은 모양**으로 있다(ADR 0006). 코어는 DB 를 모르므로 서버가
사내 프리셋을 값(dict)으로 넘기고, 여기서 같은 검사를 지난다.

값의 출처는 `source` 에 적는다. 규격서와 대조하기 전에는 `verified=False` — 화면이
「검토 필요」로 보인다. 모양을 만드는 규칙(묶음 — `bend_bar` …)은 코드이고, 프리셋은 숫자와
규칙의 선택만 든다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

DATA = Path(__file__).parent / "data"

#: 시험 종류 — 화면의 이름(이 순서로 보인다). 종류를 더하면 프리셋 모델과
#: `data/<종류>.json` 을 더한다. 시편 시험은 시편을 그리고(`bending` · `tensile` …), 제품
#: 시험은 **사용자의 제품에** 건다(`product`).
TESTS: dict[str, str] = {
    "bending": "굽힘",
    "tensile": "인장",
    "compressive": "압축",
    "shear": "전단",
    "lap": "접착 이음",
    "fastener": "체결부",
    "force": "정하중",
    "directed": "방향 하중",
    "handle": "손잡이·벽걸이",
    "crush": "압착",
    "compression": "적층 압축",
    "pressure": "수압",
    "torsion": "비틀림",
    "acceleration": "등가 가속도",
    "vibration": "진동",
    "modal": "고유진동수",
}
#: 시편을 그리는 시험.
SPECIMEN_TESTS = ("bending", "tensile", "compressive", "shear", "lap", "fastener")
#: 제품에 거는 시험 — 시편을 그리지 않는다.
PRODUCT_TESTS = (
    "force",
    "directed",
    "handle",
    "crush",
    "compression",
    "pressure",
    "torsion",
    "acceleration",
    "vibration",
    "modal",
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RadiusRule(_Base):
    """두께에 따라 갈리는 반지름 한 줄 — 앞에서부터 처음 맞는 줄을 쓴다."""

    radius: float = Field(gt=0)
    max_thickness: float | None = Field(default=None, gt=0)
    """이 두께(mm) 이하에서. 비우면 나머지 전부."""


Radius = float | list[RadiusRule]


class SpanRule(_Base):
    """지지 간격 — 두께의 배수(`to_thickness`, 간격비 16:1 이면 16) 또는 고정 값(`value`)."""

    to_thickness: float | None = Field(default=None, gt=0)
    value: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one(self) -> SpanRule:
        if (self.to_thickness is None) == (self.value is None):
            raise ValueError("span은 to_thickness와 value 중 하나만 지정하십시오.")
        return self


class LoadSpanRule(_Base):
    """4점 굽힘의 하중 간격(노즈 둘 사이) — 지지 간격의 비(`to_span`) 또는 고정 값."""

    to_span: float | None = Field(default=None, gt=0, lt=1)
    value: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one(self) -> LoadSpanRule:
        if (self.to_span is None) == (self.value is None):
            raise ValueError("load_span은 to_span과 value 중 하나만 지정하십시오.")
        return self


class Overhang(_Base):
    """시편이 지지점 바깥으로 남아야 하는 길이(한쪽) — 지지 간격의 비와 최소 값 중 큰 것.
    규격이 정하지 않으면 둘 다 0 이다."""

    to_span: float = Field(default=0.0, ge=0, lt=1)
    min: float = Field(default=0.0, ge=0)


class BendingSetup(_Base):
    """굽힘 시험의 배치 — 시편 레시피와 지그 생성기(`bending_setup`)가 같은 규칙을 쓴다."""

    points: Literal[3, 4] = 3
    span: SpanRule
    load_span: LoadSpanRule | None = None
    """4점만 — 3점이면 비운다."""
    support_radius: Radius
    nose_radius: Radius
    overhang: Overhang = Field(default_factory=Overhang)

    @model_validator(mode="after")
    def _points(self) -> BendingSetup:
        if self.points == 4 and self.load_span is None:
            raise ValueError("4점 굽힘에는 load_span(하중 간격)이 필요합니다.")
        if self.points == 3 and self.load_span is not None:
            raise ValueError("3점 굽힘에는 load_span을 지정하지 않습니다.")
        for name in ("support_radius", "nose_radius"):
            rule = getattr(self, name)
            if isinstance(rule, list) and (not rule or rule[-1].max_thickness is not None):
                raise ValueError(
                    f"{name}: 마지막 줄은 max_thickness 없이 나머지를 맡아야 합니다."
                )
        return self


class BarSpecimen(_Base):
    """직사각 바 — 길이 X · 폭 Y · 두께 Z(누르는 방향)."""

    length: float = Field(gt=0)
    width: float = Field(gt=0)
    thickness: float = Field(gt=0)


class BendingAnalysis(_Base):
    """해석 조건의 기본값 — **규격의 판정 기준이 아니다.** 사용자가 고친다."""

    strain: float = Field(default=0.05, gt=0, le=0.2)
    """노즈를 내리는 양의 기준 — 바깥 섬유 변형률이 이 값이 되는 하중점 처짐
    (`bending.deflection`)."""
    friction: float = Field(default=0.1, ge=0, le=1)
    """시편과 롤러 · 노즈 사이 마찰계수."""


class BendingPreset(_Base):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,63}$")
    """공개 규격은 `astm-d790-16` 같은 이름, 사내 규격은 DB 의 uuid."""
    test: Literal["bending"] = "bending"
    family: Literal["bend_bar"] = "bend_bar"
    standard: str = Field(min_length=1, max_length=80)
    """규격 번호 — 목록을 묶는다(`ASTM D790`)."""
    name: str = Field(min_length=1, max_length=120)
    specimen: BarSpecimen
    setup: BendingSetup
    analysis: BendingAnalysis = Field(default_factory=BendingAnalysis)
    source: str = Field(default="", max_length=500)
    """값의 근거 — 규격 번호 · 조항 · 표. 검토하는 사람이 대조한다."""
    verified: bool = False
    """규격서와 대조했나. 아니면 화면이 「검토 필요」."""
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _fits(self) -> BendingPreset:
        from app.core.specimens import bending

        span = bending.span_at(self.setup, self.specimen.thickness)
        need = span + 2 * bending.overhang_at(self.setup, span)
        if self.specimen.length < need - 1e-6:
            raise ValueError(
                f"시편 길이({self.specimen.length:g})가 지지 간격({span:g})과 양쪽 돌출을 "
                f"담지 못합니다(최소 {need:g} mm)."
            )
        return self


class _Common(_Base):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,63}$")
    standard: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(default="", max_length=500)
    verified: bool = False
    note: str = Field(default="", max_length=1000)


class ForceSetup(_Base):
    """정하중 — 원형 접촉면으로 제품 윗면을 수직으로 누른다. 받침은 제품의 아랫면."""

    force: float = Field(gt=0)
    """누르는 힘(N)."""
    probe_diameter: float = Field(gt=0)
    """누르는 도구의 접촉 지름(mm) — 그 크기의 원으로 하중 자리를 나눈다."""


class ForceAnalysis(_Base):
    large_deflection: bool = False


class ForcePreset(_Common):
    """정하중 시험(IEC 62368-1 부속서 T 등) — 제품에 건다."""

    test: Literal["force"]
    setup: ForceSetup
    analysis: ForceAnalysis = Field(default_factory=ForceAnalysis)


class VibrationSetup(_Base):
    """정현파 진동 — 아랫면을 가진대에 고정하고 한 축으로 일정 가속도를 준다(주파수 훑기)."""

    freq_min: float = Field(ge=0)
    freq_max: float = Field(gt=0)
    acceleration_g: float = Field(gt=0)
    """가속도 진폭(g = 9.80665 m/s²). 교차 주파수 아래의 변위 일정 구간은 나타내지 않는다."""
    damping_ratio: float = Field(default=0.02, gt=0, lt=1)
    modes: int = Field(default=30, ge=1, le=200)
    """모드 중첩에 쓸 모드 수 — 최대 주파수의 1.5배까지 덮을 만큼."""
    points: int = Field(default=100, ge=1, le=2000)
    """주파수 점 수."""

    @model_validator(mode="after")
    def _range(self) -> VibrationSetup:
        if self.freq_min >= self.freq_max:
            raise ValueError("freq_min은 freq_max보다 작아야 합니다.")
        return self


class VibrationPreset(_Common):
    """정현파 진동 시험(IEC 60068-2-6) — 제품에 건다."""

    test: Literal["vibration"]
    setup: VibrationSetup


# --- 시편: 인장 · 전단 · 접착 이음 -------------------------------------------------


class TensileSpecimen(_Base):
    """인장 시편 — 길이 X · 폭 Y · 두께 Z. 도그본(`dogbone`)은 좁은 평행부와 넓은 그립부를
    반지름으로 잇고(호가 평행부에 접한다), 띠(`strip`)는 폭이 한결같다. 구멍 띠(`open_hole`)는
    띠 한가운데에 구멍이 있다."""

    length: float = Field(gt=0)
    """전체 길이."""
    width: float = Field(gt=0)
    """그립부 폭 — 띠는 그 폭 하나."""
    thickness: float = Field(gt=0)
    gauge_length: float = Field(gt=0)
    """표점 거리 — 신율을 재는 구간. 윗면에 면 나누기로 표시해 결과에서 집는다."""
    grip_length: float = Field(gt=0)
    """한쪽 그립이 무는 길이."""
    gauge_width: float | None = Field(default=None, gt=0)
    """평행부 폭 — 도그본만."""
    parallel_length: float | None = Field(default=None, gt=0)
    """평행부 길이 — 도그본만."""
    radius: float | None = Field(default=None, gt=0)
    """평행부와 그립부를 잇는 반지름 — 도그본만."""
    hole_diameter: float | None = Field(default=None, gt=0)
    """한가운데 구멍의 지름 — 구멍 띠만."""


class TensileAnalysis(_Base):
    """해석 조건의 기본값 — **규격의 판정 기준이 아니다.**"""

    strain: float = Field(default=0.01, gt=0, le=0.5)
    """그립 사이 공칭 변형률 — 당김 그립을 `변형률 x 그립 간격` 만큼 옮긴다."""
    large_deflection: bool = False


class TensilePreset(_Common):
    """인장 시험(ASTM E8 · D638 · D3039 · D5766, ISO 527) — 시편을 그린다."""

    test: Literal["tensile"]
    family: Literal["dogbone", "strip", "open_hole"]
    specimen: TensileSpecimen
    analysis: TensileAnalysis = Field(default_factory=TensileAnalysis)

    @model_validator(mode="after")
    def _fits(self) -> TensilePreset:
        from app.core.specimens import tensile

        tensile.check(self.family, self.specimen)
        return self


class VNotchSpecimen(_Base):
    """V 노치 전단 시편 — 길이 X · 폭 Y · 두께 Z. 폭의 양 가장자리 한가운데에 V 노치."""

    length: float = Field(gt=0)
    width: float = Field(gt=0)
    thickness: float = Field(gt=0)
    notch_depth: float = Field(gt=0)
    """한쪽 노치의 깊이(가장자리에서 뿌리까지)."""
    notch_angle: float = Field(default=90.0, gt=0, lt=180)
    """노치가 벌어진 각(도)."""
    notch_radius: float = Field(default=1.3, gt=0)
    """노치 뿌리의 반지름."""
    grip_gap: float = Field(gt=0)
    """가운데 물리지 않는 길이 — 두 물림 사이."""


class ShearAnalysis(_Base):
    shear_strain: float = Field(default=0.01, gt=0, le=0.5)
    """가압 물림을 `전단 변형률 x 물림 간격` 만큼 폭 방향(Y)으로 옮긴다 — 해석 기본값."""


class ShearPreset(_Common):
    """V 노치 전단 시험(ASTM D5379 · D7078) — 시편을 그린다."""

    test: Literal["shear"]
    family: Literal["v_notch"] = "v_notch"
    specimen: VNotchSpecimen
    analysis: ShearAnalysis = Field(default_factory=ShearAnalysis)

    @model_validator(mode="after")
    def _fits(self) -> ShearPreset:
        from app.core.specimens import shear

        shear.check(self.specimen)
        return self


class LapSpecimen(_Base):
    """단일 겹치기 이음 — 피착재 둘이 `overlap` 만큼 겹쳐 접착층으로 붙는다. 길이 X · 폭 Y ·
    두께 Z."""

    length: float = Field(gt=0)
    """피착재 하나의 길이."""
    width: float = Field(gt=0)
    thickness: float = Field(gt=0)
    """피착재 두께."""
    overlap: float = Field(gt=0)
    """겹친 길이."""
    bondline: float = Field(default=0.2, gt=0)
    """접착층 두께."""
    grip_length: float = Field(gt=0)
    """한쪽 그립이 무는 길이."""


class LapAnalysis(_Base):
    displacement: float = Field(default=0.1, gt=0)
    """당김 그립을 옮기는 양(mm) — 해석 기본값."""
    large_deflection: bool = True
    """겹치기 이음은 당기면 돌아간다(편심) — 대변형이 기본이다."""


class LapPreset(_Common):
    """접착 겹치기 전단(ASTM D1002 · D5868, ISO 4587) — 시편을 그린다."""

    test: Literal["lap"]
    family: Literal["single_lap"] = "single_lap"
    specimen: LapSpecimen
    analysis: LapAnalysis = Field(default_factory=LapAnalysis)

    @model_validator(mode="after")
    def _fits(self) -> LapPreset:
        size = self.specimen
        if size.overlap >= size.length:
            raise ValueError("overlap(겹침)이 피착재 길이보다 짧아야 합니다.")
        if size.grip_length + 1.0 > size.length - size.overlap:
            raise ValueError(
                f"그립 길이({size.grip_length:g})가 겹치지 않은 길이"
                f"({size.length - size.overlap:g} mm)에 들어가지 않습니다."
            )
        return self


# --- 제품: 손잡이 · 적층 압축 · 비틀림 · 고유진동수 ----------------------------------


class HandleSetup(_Base):
    """손잡이 · 벽걸이 — 고른 자리(손잡이 · 고정 브래킷)를 고정하고 제품 무게의 배수가 아래로
    걸리게 한다(가속도 — 밀도가 무게를 정한다)."""

    weight_factor: float = Field(gt=0, le=50)
    """무게의 몇 배인가."""


class HandleAnalysis(_Base):
    large_deflection: bool = False


class HandlePreset(_Common):
    test: Literal["handle"]
    setup: HandleSetup
    analysis: HandleAnalysis = Field(default_factory=HandleAnalysis)


class CompressionSetup(_Base):
    """적층 압축 — 윗면 전체를 누르고 아랫면을 받친다. 하중은 위에 쌓인 무게:

    - 단수(`layers`): 무게 · g · (단수 - 1) · 계수
    - 적재 높이(`stack_height`): 무게 · g · (적재 높이 - 제품 높이) / 제품 높이 · 계수

    무게는 적용할 때 사람이 준다(kg)."""

    layers: int | None = Field(default=None, ge=2, le=200)
    stack_height: float | None = Field(default=None, gt=0)
    """적재 높이(mm)."""
    factor: float = Field(default=1.0, gt=0, le=20)
    """안전 · 보정 계수."""

    @model_validator(mode="after")
    def _one(self) -> CompressionSetup:
        if (self.layers is None) == (self.stack_height is None):
            raise ValueError("layers(단수)와 stack_height(적재 높이) 중 하나만 지정하십시오.")
        return self


class StaticAnalysis(_Base):
    """정적 해석 설정 — 대변형만(적층 압축 · 압착 · 수압 · 등가 가속도 · 방향 하중)."""

    large_deflection: bool = False


class CompressionPreset(_Common):
    test: Literal["compression"]
    setup: CompressionSetup
    analysis: StaticAnalysis = Field(default_factory=StaticAnalysis)


class TorsionSetup(_Base):
    """비틀림 — 긴 축의 한쪽 끝을 고정하고 다른 끝을 그 축으로 돌린다."""

    angle: float = Field(gt=0, le=90)
    """비트는 각(도)."""


class TorsionAnalysis(_Base):
    large_deflection: bool = True


class TorsionPreset(_Common):
    test: Literal["torsion"]
    setup: TorsionSetup
    analysis: TorsionAnalysis = Field(default_factory=TorsionAnalysis)


class ModalSetup(_Base):
    """고유진동수 — 시험 주파수 범위 안의 모드를 구한다(공진 탐색). 받침을 고정하거나
    자유-자유로 둔다."""

    modes: int = Field(default=12, ge=1, le=200)
    freq_min: float = Field(default=0.0, ge=0)
    freq_max: float | None = Field(default=None, gt=0)
    """비우면 범위 없이 낮은 차수부터 `modes` 개."""
    support: Literal["fixed", "free"] = "fixed"

    @model_validator(mode="after")
    def _range(self) -> ModalSetup:
        if self.freq_max is not None and self.freq_min >= self.freq_max:
            raise ValueError("freq_min은 freq_max보다 작아야 합니다.")
        return self


class ModalPreset(_Common):
    test: Literal["modal"]
    setup: ModalSetup


# --- 시편: 압축 · 체결부 ------------------------------------------------------------


class CompressiveSpecimen(_Base):
    """압축 시편 — 각기둥(`prism`) · 원기둥(`cylinder`)은 세워서(길이가 Z) 위아래 가압판으로
    누르고, 띠(`strip`) · 구멍 띠(`open_hole`)는 눕혀서(길이가 X) 양 끝 그립으로 누른다."""

    length: float = Field(gt=0)
    """누르는 방향의 길이."""
    width: float = Field(gt=0)
    """폭 — 원기둥은 지름."""
    thickness: float | None = Field(default=None, gt=0)
    """두께 — 원기둥은 비운다."""
    grip_length: float | None = Field(default=None, gt=0)
    """한쪽 그립이 무는 길이 — 띠 · 구멍 띠만."""
    hole_diameter: float | None = Field(default=None, gt=0)
    """한가운데 구멍의 지름 — 구멍 띠만."""


class CompressiveAnalysis(_Base):
    strain: float = Field(default=0.01, gt=0, le=0.5)
    """공칭 변형률 — 누르는 양 = 변형률 x 자유 길이(가압판이면 전체 길이)."""
    large_deflection: bool = False


class CompressivePreset(_Common):
    """압축 시험(ASTM D695 · D6641 · D6484 · E9, ISO 604 · 14126) — 시편을 그린다."""

    test: Literal["compressive"]
    family: Literal["prism", "cylinder", "strip", "open_hole"]
    specimen: CompressiveSpecimen
    analysis: CompressiveAnalysis = Field(default_factory=CompressiveAnalysis)

    @model_validator(mode="after")
    def _fits(self) -> CompressivePreset:
        from app.core.specimens import compressive

        compressive.check(self.family, self.specimen)
        return self


class FastenerSpecimen(_Base):
    """체결부 시편 — 판(길이 X · 폭 Y · 두께 Z)에 구멍 하나와 핀 · 체결구.

    - 핀 베어링(`bearing`): 구멍이 한쪽 끝에서 `edge_distance` 에 있고, 핀이 그 끝 쪽으로 판을
      민다. 반대쪽 끝을 그립이 문다.
    - 뽑힘(`pull_through`): 판 한가운데 구멍에 머리 달린 체결구, 판 둘레를 받침 고리로 물고
      체결구를 아래로 당긴다(머리가 판을 뚫고 나가려 한다)."""

    length: float = Field(gt=0)
    width: float = Field(gt=0)
    thickness: float = Field(gt=0)
    hole_diameter: float = Field(gt=0)
    edge_distance: float | None = Field(default=None, gt=0)
    """구멍 중심에서 가까운 끝까지 — 핀 베어링만."""
    grip_length: float | None = Field(default=None, gt=0)
    """반대쪽 그립이 무는 길이 — 핀 베어링만."""
    head_diameter: float | None = Field(default=None, gt=0)
    """체결구 머리 지름 — 뽑힘만."""
    head_height: float | None = Field(default=None, gt=0)
    """체결구 머리 높이 — 뽑힘만."""
    support_diameter: float | None = Field(default=None, gt=0)
    """받침 고리의 안지름(그 바깥을 문다) — 뽑힘만."""


class FastenerAnalysis(_Base):
    displacement: float = Field(default=0.2, gt=0)
    """핀 · 체결구를 옮기는 양(mm) — 해석 기본값."""
    friction: float = Field(default=0.1, ge=0, le=1)
    """핀 · 머리와 판 사이 마찰계수."""
    large_deflection: bool = True


class FastenerPreset(_Common):
    """체결부 시험(ASTM D5961 핀 베어링 · D7332 뽑힘) — 시편을 그린다."""

    test: Literal["fastener"]
    family: Literal["bearing", "pull_through"]
    specimen: FastenerSpecimen
    analysis: FastenerAnalysis = Field(default_factory=FastenerAnalysis)

    @model_validator(mode="after")
    def _fits(self) -> FastenerPreset:
        from app.core.specimens import fastener

        fastener.check(self.family, self.specimen)
        return self


# --- 제품: 압착 · 수압 · 등가 가속도 · 방향 하중 ------------------------------------------


class CrushSetup(_Base):
    """압착 — 평판 둘 사이에서 누른다(배터리 압착 등). 받침과 누르는 면은 기본이 아랫면 ·
    윗면, 3D 에서 누를 면을 고르면 그 반대쪽 끝 면이 받침이다."""

    force: float = Field(gt=0)
    """누르는 힘(N)."""


class CrushPreset(_Common):
    test: Literal["crush"]
    setup: CrushSetup
    analysis: StaticAnalysis = Field(default_factory=StaticAnalysis)


class PressureSetup(_Base):
    """수압 — 바깥 면에 물 깊이만큼의 압력(밀도 x g x 깊이)을 고르게. 받침은 강체 운동만
    막는다."""

    depth: float = Field(gt=0, le=1000)
    """물 깊이(m)."""
    factor: float = Field(default=1.0, gt=0, le=20)
    """안전 계수."""


class PressurePreset(_Common):
    test: Literal["pressure"]
    setup: PressureSetup
    analysis: StaticAnalysis = Field(default_factory=StaticAnalysis)


class AccelerationSetup(_Base):
    """등가 정적 가속도 — 충격 · 운송 가속도를 정적으로 근사한다. 받침을 고정하고 한 축으로
    `acceleration_g x factor` 의 가속도. 실제 충격의 응답 배율은 고유진동수와 지속 시간에 따라
    다르다(반정현파는 최대 약 1.7)."""

    acceleration_g: float = Field(gt=0, le=10000)
    duration_ms: float | None = Field(default=None, gt=0)
    """충격 지속 시간(ms) — 메모에만 쓴다(정적 근사는 시간을 모른다)."""
    factor: float = Field(default=1.0, gt=0, le=5)
    """응답 배율."""


class AccelerationPreset(_Common):
    test: Literal["acceleration"]
    setup: AccelerationSetup
    analysis: StaticAnalysis = Field(default_factory=StaticAnalysis)


class DirectedSetup(_Base):
    """방향 하중 — 고른 면에 정한 방향의 힘과 그 축을 도는 모멘트(케이블 당김 · 비틀기,
    커넥터 렌칭). 힘 · 모멘트 중 적어도 하나."""

    force: float | None = Field(default=None, gt=0)
    """힘(N)."""
    torque: float | None = Field(default=None, gt=0)
    """모멘트(N·m) — 방향 축을 도는 오른손 방향."""

    @model_validator(mode="after")
    def _some(self) -> DirectedSetup:
        if self.force is None and self.torque is None:
            raise ValueError("force(힘)와 torque(모멘트) 중 적어도 하나를 지정하십시오.")
        return self


class DirectedPreset(_Common):
    test: Literal["directed"]
    setup: DirectedSetup
    analysis: StaticAnalysis = Field(default_factory=StaticAnalysis)


#: 프리셋 한 벌 — `test` 로 가른다.
Preset = (
    BendingPreset
    | TensilePreset
    | CompressivePreset
    | ShearPreset
    | LapPreset
    | FastenerPreset
    | ForcePreset
    | DirectedPreset
    | HandlePreset
    | CrushPreset
    | CompressionPreset
    | PressurePreset
    | TorsionPreset
    | AccelerationPreset
    | VibrationPreset
    | ModalPreset
)
#: 시편을 그리는 프리셋.
SpecimenTestPreset = (
    BendingPreset
    | TensilePreset
    | CompressivePreset
    | ShearPreset
    | LapPreset
    | FastenerPreset
)
#: 제품에 거는 프리셋.
ProductTestPreset = (
    ForcePreset
    | DirectedPreset
    | HandlePreset
    | CrushPreset
    | CompressionPreset
    | PressurePreset
    | TorsionPreset
    | AccelerationPreset
    | VibrationPreset
    | ModalPreset
)

_ADAPTER: TypeAdapter[Any] = TypeAdapter(Annotated[Preset, Field(discriminator="test")])


def parse_preset(raw: dict[str, Any]) -> Preset:
    """프리셋을 읽어 검사한다 — 틀리면 pydantic 의 `ValidationError`(어느 칸이 왜). `test` 가
    없으면 굽힘이다(처음 형식)."""
    preset: Preset = _ADAPTER.validate_python({"test": "bending", **raw})
    return preset


@lru_cache(maxsize=1)
def builtin() -> tuple[Preset, ...]:
    """공개 규격 프리셋 전부 — `data/*.json`(파일마다 목록). id 가 겹치면 시작부터 실패한다."""
    found: list[Preset] = []
    for path in sorted(DATA.glob("*.json")):
        for raw in json.loads(path.read_text(encoding="utf-8")):
            found.append(parse_preset(raw))
    ids = [one.id for one in found]
    duplicated = sorted({one for one in ids if ids.count(one) > 1})
    if duplicated:
        raise ValueError(f"프리셋 id가 겹칩니다: {', '.join(duplicated)}")
    return tuple(found)


def find_builtin(preset_id: str) -> Preset | None:
    return next((one for one in builtin() if one.id == preset_id), None)
