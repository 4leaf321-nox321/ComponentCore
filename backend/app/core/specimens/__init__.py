"""시험 시편 — 규격 프리셋으로 시편 · 시험 지그 · 해석 조건을 그린다(ADR 0006).

공개 규격의 프리셋은 `data/*.json`, 사내 규격은 서버가 DB 에서 값으로 넘긴다 — 같은 모양
(`presets.Preset`)이고 같은 검사를 지난다. 시험 종류마다 모듈 하나(`bending` · `tensile` ·
`compressive` · `shear` · `lap` · `fastener`), 제품에 거는 시험은 `product` 하나.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.core.specimens import bending, compressive, fastener, lap, product, shear, tensile
from app.core.specimens.bending import SpecimenBuild
from app.core.specimens.presets import (
    PRODUCT_TESTS,
    SPECIMEN_TESTS,
    TESTS,
    BendingPreset,
    CompressivePreset,
    FastenerPreset,
    LapPreset,
    Preset,
    ShearPreset,
    TensilePreset,
    builtin,
    find_builtin,
    parse_preset,
)

__all__ = [
    "PRODUCT_TESTS",
    "SPECIMEN_TESTS",
    "TESTS",
    "Preset",
    "SpecimenBuild",
    "build",
    "builtin",
    "find_builtin",
    "parse_preset",
    "product",
    "resized",
]


def resized(preset: Preset, dimensions: dict[str, float]) -> Preset:
    """시편 치수 일부를 바꾼 프리셋 — 프리셋과 같은 검사를 다시 지난다(평행부가 그립부보다
    넓어지는 따위를 막는다). 틀리면 무엇이 왜인지 `ValueError`."""
    if not dimensions:
        return preset
    specimen = getattr(preset, "specimen", None)
    if specimen is None:
        raise ValueError(f"‘{preset.name}’에는 시편 치수가 없습니다.")
    unknown = sorted(set(dimensions) - set(type(specimen).model_fields))
    if unknown:
        raise ValueError(f"이 시편에 없는 치수입니다: {', '.join(unknown)}")
    raw = preset.model_dump(mode="json")
    raw["specimen"] = {**raw["specimen"], **dimensions}
    try:
        return parse_preset(raw)
    except ValidationError as failure:
        first = failure.errors()[0]
        raise ValueError(str(first["msg"]).removeprefix("Value error, ")) from failure


def build(
    preset: Preset,
    *,
    dimensions: dict[str, float] | None = None,
    length: float | None = None,
    width: float | None = None,
    thickness: float | None = None,
    fixture: bool = True,
    conditions: bool = True,
) -> SpecimenBuild:
    """프리셋의 시험 종류에 맞는 생성기로. 치수는 `dimensions`(시편 칸 이름 → 값)나
    `length` · `width` · `thickness` 로 바꾸고, 비우면 프리셋 값이다."""
    given = {key: float(value) for key, value in (dimensions or {}).items() if value}
    for key, value in (("length", length), ("width", width), ("thickness", thickness)):
        if value:
            given[key] = float(value)
    if preset.test in PRODUCT_TESTS:
        raise ValueError(
            f"‘{preset.name}’은(는) 제품에 거는 시험입니다. 시편 대신 ‘제품에 적용’을 "
            "사용하십시오."
        )
    if isinstance(preset, BendingPreset):
        extra = sorted(set(given) - {"length", "width", "thickness"})
        if extra:
            raise ValueError(f"이 시편에 없는 치수입니다: {', '.join(extra)}")
        return bending.build(
            preset,
            length=given.get("length"),
            width=given.get("width"),
            thickness=given.get("thickness"),
            fixture=fixture,
            conditions=conditions,
        )
    sized = resized(preset, given)
    if isinstance(sized, TensilePreset):
        return tensile.build(sized, fixture=fixture, conditions=conditions)
    if isinstance(sized, ShearPreset):
        return shear.build(sized, fixture=fixture, conditions=conditions)
    if isinstance(sized, LapPreset):
        return lap.build(sized, fixture=fixture, conditions=conditions)
    if isinstance(sized, CompressivePreset):
        return compressive.build(sized, fixture=fixture, conditions=conditions)
    if isinstance(sized, FastenerPreset):
        return fastener.build(sized, fixture=fixture, conditions=conditions)
    raise ValueError(f"아직 만들 수 없는 시험 종류입니다: {preset.test}")
