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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATA = Path(__file__).parent / "data"

#: 시험 종류 — 화면의 이름. 종류를 더하면 프리셋 모델과 `data/<종류>.json` 을 더한다.
TESTS: dict[str, str] = {"bending": "굽힘"}


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
    """노즈를 내리는 양 — 바깥 섬유 변형률이 이 값이 되는 중앙 처짐."""
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


#: 프리셋 한 벌 — 시험 종류를 더하면 여기에 합친다(`test` 로 가른다).
Preset = BendingPreset


def parse_preset(raw: dict[str, object]) -> Preset:
    """프리셋을 읽어 검사한다 — 틀리면 pydantic 의 `ValidationError`(어느 칸이 왜)."""
    return BendingPreset.model_validate(raw)


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
