"""인장 · 압축 · 전단 · 겹치기 이음 · 체결부 시편 — 공개 규격 프리셋은 **전부** 그려 보고,
조건 검증과 그립 자리가 실제 면을 찾는지 본다. 모양은 해석식(도그본 넓이, V 노치 넓이, 구멍,
판 · 핀 · 체결구의 부피, 받침 고리 넓이)과 맞춘다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core import conditions, specimens
from app.core.recipe import evaluate, parse
from app.core.recipe.params import resolve_params
from app.core.recipe.topology import bodies, regions
from app.core.specimens import compressive, fastener, lap, shear, tensile
from app.core.specimens.presets import (
    CompressivePreset,
    FastenerPreset,
    LapPreset,
    ShearPreset,
    TensilePreset,
)

COUPONS = [
    one
    for one in specimens.builtin()
    if one.test in ("tensile", "compressive", "shear", "lap", "fastener")
]


def _disc(diameter: float | None) -> float:
    return math.pi * (diameter or 0) ** 2 / 4


def _made(made: specimens.SpecimenBuild) -> tuple[Any, dict[str, list[dict[str, Any]]]]:
    shape = evaluate(parse(made.recipe), resolve_file=None)
    assert made.conditions is not None
    names = [one["name"] for one in bodies(shape.shape)]
    conditions.parse(made.conditions, names)  # 없는 바디 · 틀린 칸이면 여기서 실패
    groups = [
        {"name": one["name"], "select": conditions.selection_query("face", one["select"])}
        for one in made.conditions["named_selections"]
    ]
    found, unresolved = regions(shape.shape, groups, shape.tags)
    assert unresolved == []
    return shape, found


def _dogbone_area(size: Any) -> float:
    """도그본 넓이 — 전체 사각형에서 평행부의 홈과 전이부 넷(호 아래)을 뺀다."""
    rise = (size.width - size.gauge_width) / 2
    run = tensile.transition(size)
    radius = size.radius
    under_arc = (
        (rise - radius) * run
        + run / 2 * (radius - rise)
        + radius**2 / 2 * math.asin(run / radius)
    )
    return float(
        size.length * size.width
        - size.parallel_length * (size.width - size.gauge_width)
        - 4 * under_arc
    )


def _notch_area(size: Any) -> float:
    """V 노치 하나의 넓이 — 빗변 사이 사다리꼴 + 뿌리 호 아래의 활꼴."""
    half = math.radians(size.notch_angle / 2)
    r = size.notch_radius
    touch_x = r * math.cos(half)
    touch_depth = size.notch_depth - r + r * math.sin(half)
    theta = math.pi - 2 * half
    return float(
        (shear.mouth(size) + touch_x) * touch_depth + r**2 / 2 * (theta - math.sin(theta))
    )


@pytest.mark.parametrize("preset", COUPONS, ids=lambda one: one.id)
def test_공개_규격의_시편은_모양과_그립_자리가_맞다(preset: specimens.Preset) -> None:
    made = specimens.build(preset)
    shape, found = _made(made)
    volume = float(shape.shape.volume)
    rules = made.conditions
    assert rules is not None
    if isinstance(preset, TensilePreset):
        bar = preset.specimen
        area = _dogbone_area(bar) if preset.family == "dogbone" else bar.length * bar.width
        hole = _disc(bar.hole_diameter)
        assert volume == pytest.approx((area - hole) * bar.thickness, rel=1e-4)
        assert len(found[tensile.FIXED]) == 2 and len(found[tensile.PULLED]) == 2
        gauge = found[tensile.GAUGE]
        assert len(gauge) == 1
        width = bar.gauge_width or bar.width
        assert gauge[0]["area"] == pytest.approx(
            bar.gauge_length * (width - 1) - hole, rel=1e-3
        )
        assert rules["constraints"][1]["x"] == "=늘림"
    elif isinstance(preset, CompressivePreset):
        block = preset.specimen
        if preset.family == "cylinder":
            assert volume == pytest.approx(_disc(block.width) * block.length, rel=1e-4)
        else:
            area = block.length * block.width - _disc(block.hole_diameter)
            assert volume == pytest.approx(area * (block.thickness or 0), rel=1e-4)
        if preset.family in ("prism", "cylinder"):
            assert len(found[compressive.BASE]) == 1 and len(found[compressive.PRESSED]) == 1
            assert rules["constraints"][1]["z"] == "=-누름"
        else:
            assert len(found[compressive.FIXED]) == 2 and len(found[compressive.PUSHED]) == 2
            assert rules["constraints"][1]["x"] == "=-누름"
    elif isinstance(preset, FastenerPreset):
        plate = preset.specimen
        hole = _disc(plate.hole_diameter)
        base = (plate.length * plate.width - hole) * plate.thickness
        names = [one["name"] for one in bodies(shape.shape)]
        if preset.family == "bearing":
            pin = hole * (plate.thickness + 2 * fastener.PIN_OUT)
            assert volume == pytest.approx(base + pin, rel=1e-4)
            assert names == [fastener.SPECIMEN, fastener.PIN]
            assert len(found["핀 끝면"]) == 2 and len(found["구멍면"]) == 1
            assert rules["body_settings"] == [{"name": fastener.PIN, "behavior": "rigid"}]
        else:
            head = _disc(plate.head_diameter) * (plate.head_height or 0)
            shank = hole * (plate.thickness + fastener.SHANK_OUT)
            assert volume == pytest.approx(base + head + shank, rel=1e-4)
            assert names == [fastener.SPECIMEN, fastener.BOLT]
            outer = min(plate.length, plate.width) - 2
            ring = _disc(outer) - _disc(plate.support_diameter)
            for name in ("받침 고리", "누름 고리"):
                assert found[name][0]["area"] == pytest.approx(ring, rel=1e-3)
            under = _disc(plate.head_diameter) - hole
            assert found["머리 아랫면"][0]["area"] == pytest.approx(under, rel=1e-3)
            assert found["체결구 끝면"][0]["centroid"][2] == pytest.approx(-fastener.SHANK_OUT)
    elif isinstance(preset, ShearPreset):
        notched = preset.specimen
        area = notched.length * notched.width - 2 * _notch_area(notched)
        assert volume == pytest.approx(area * notched.thickness, rel=1e-4)
        assert len(found[shear.FIXED]) == 2 and len(found[shear.MOVED]) == 2
    else:
        assert isinstance(preset, LapPreset)
        size = preset.specimen
        plates = 2 * size.length * size.width * size.thickness
        glue = size.overlap * size.width * size.bondline
        assert volume == pytest.approx(plates + glue, rel=1e-4)
        assert [one["name"] for one in bodies(shape.shape)] == [
            lap.LOWER,
            lap.ADHESIVE,
            lap.UPPER,
        ]
        assert len(found["접착층 아랫면"]) == 1 and len(found["접착층 윗면"]) == 1
        assert {one["type"] for one in rules["contacts"]} == {"bonded"}


def test_도그본의_치수를_바꾸면_전이부가_따라온다() -> None:
    preset = specimens.find_builtin("astm-d638-type-i")
    assert isinstance(preset, TensilePreset)
    made = specimens.build(preset, dimensions={"gauge_width": 10.0, "radius": 50.0})
    values = resolve_params(made.recipe)
    rise = (19 - 10) / 2
    assert values["전이_길이"] == pytest.approx(math.sqrt(2 * 50 * rise - rise**2))
    # DOE 처럼 레시피 변수만 바꿔도 다시 그려진다 — 전이부는 식이다.
    moved = {**made.recipe, "params": {**made.recipe["params"], "평행부_폭": 12.0}}
    shape = evaluate(parse(moved), resolve_file=None)
    size = preset.specimen.model_copy(update={"gauge_width": 12.0, "radius": 50.0})
    assert float(shape.shape.volume) == pytest.approx(_dogbone_area(size) * 3.2, rel=1e-4)


def test_틀린_치수는_무엇이_왜인지_말한다() -> None:
    preset = specimens.find_builtin("astm-d638-type-i")
    assert preset is not None
    with pytest.raises(ValueError, match="평행부 폭"):
        specimens.build(preset, dimensions={"gauge_width": 25.0})
    with pytest.raises(ValueError, match="전이부를 물면"):
        specimens.build(preset, dimensions={"grip_length": 40.0})
    with pytest.raises(ValueError, match="없는 치수"):
        specimens.build(preset, dimensions={"span": 10.0})
    bend = specimens.find_builtin("astm-d790-16")
    assert bend is not None
    with pytest.raises(ValueError, match="없는 치수"):
        specimens.build(bend, dimensions={"radius": 1.0})
    notch = specimens.find_builtin("astm-d5379")
    assert notch is not None
    with pytest.raises(ValueError, match="노치를 물면"):
        specimens.build(notch, dimensions={"grip_gap": 6.0})


def test_압축_체결부_구멍_시편의_틀린_치수() -> None:
    cylinder = specimens.find_builtin("astm-e9-short")
    strip = specimens.find_builtin("astm-d6641")
    bearing = specimens.find_builtin("astm-d5961-a")
    pull = specimens.find_builtin("astm-d7332-example")
    holed = specimens.find_builtin("astm-d5766")
    assert cylinder and strip and bearing and pull and holed
    with pytest.raises(ValueError, match="thickness"):
        specimens.build(cylinder, dimensions={"thickness": 3.0})
    with pytest.raises(ValueError, match="다 덮습니다"):
        specimens.build(strip, dimensions={"grip_length": 70.0})
    with pytest.raises(ValueError, match="끝 거리"):
        specimens.build(bearing, dimensions={"edge_distance": 3.0})
    with pytest.raises(ValueError, match="구멍까지"):
        specimens.build(bearing, dimensions={"grip_length": 120.0})
    with pytest.raises(ValueError, match="받침 고리"):
        specimens.build(pull, dimensions={"support_diameter": 12.0})
    with pytest.raises(ValueError, match="표점 거리"):
        specimens.build(holed, dimensions={"gauge_length": 6.0})


def test_띠에_도그본_치수를_주면_막는다() -> None:
    raw = specimens.find_builtin("astm-d3039-0deg")
    assert raw is not None
    body = {**raw.model_dump(mode="json"), "specimen": {**raw.model_dump()["specimen"]}}
    body["specimen"]["radius"] = 10
    with pytest.raises(ValueError, match="띠 시편"):
        specimens.parse_preset(body)


def test_그립_없이_시편만() -> None:
    for preset_id in (
        "iso-527-2-1a",
        "astm-d7078",
        "iso-4587",
        "astm-d6484",
        "astm-e9-medium",
        "astm-d5961-a",
        "astm-d7332-example",
    ):
        preset = specimens.find_builtin(preset_id)
        assert preset is not None
        made = specimens.build(preset, fixture=False)
        assert made.conditions is None
        assert not [one for one in made.recipe["nodes"] if one["op"] == "divide_face"]
        evaluate(parse(made.recipe), resolve_file=None)
