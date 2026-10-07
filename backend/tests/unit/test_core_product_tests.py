"""제품 시험 — 사용자의 제품에 정하중 · 손잡이·벽걸이 · 적층 압축 · 비틀림 · 정현파 진동 ·
고유진동수를 건다.

공개 규격 프리셋은 **전부** 구멍판 제품에 걸어 본다 — 조건 검증과 선택 그룹이 실제 면을 찾는지.
3D 에서 고른 면(`FacePick`)이 받침 · 누를 면 · 끝 면이 되는지도 본다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core import conditions, specimens
from app.core.recipe import evaluate, parse
from app.core.recipe.params import resolve_params
from app.core.recipe.templates import TEMPLATES
from app.core.recipe.topology import bodies, regions
from app.core.specimens import product
from app.core.specimens.presets import (
    AccelerationPreset,
    CompressionPreset,
    CrushPreset,
    DirectedPreset,
    ForcePreset,
    HandlePreset,
    ModalPreset,
    PressurePreset,
    TorsionPreset,
    VibrationPreset,
)
from app.core.specimens.product import FacePick

PLATE = TEMPLATES["plate_with_holes"]()  # 100 x 60 x 12, 모서리 구멍 넷(Ø8, (±40, ±20))
PRODUCT_PRESETS = [one for one in specimens.builtin() if one.test in specimens.PRODUCT_TESTS]
TOP = FacePick((0.0, 0.0, 12.0), (0.0, 0.0, 1.0))
SIDE = FacePick((50.0, 5.0, 6.0), (1.0, 0.0, 0.0))  # +X 옆면


def _bbox(recipe: dict[str, Any]) -> tuple[list[float], list[float]]:
    box = evaluate(parse(recipe), resolve_file=None).shape.bounding_box()
    return [box.min.X, box.min.Y, box.min.Z], [box.max.X, box.max.Y, box.max.Z]


def _check(made: product.ProductTest) -> dict[str, Any]:
    shape = evaluate(parse(made.recipe), resolve_file=None)
    names = [one["name"] for one in bodies(shape.shape)]
    conditions.parse(made.conditions, names)  # 없는 바디 · 틀린 칸이면 여기서 실패
    found, unresolved = regions(shape.shape, made.conditions["named_selections"], shape.tags)
    assert unresolved == []
    return found


def _needs(preset: specimens.Preset) -> dict[str, Any]:
    """기본으로 걸 수 없는 시험이 꼭 받아야 하는 것 — 손잡이는 고른 자리, 압축은 무게."""
    if isinstance(preset, HandlePreset):
        return {"faces": {"support": [TOP]}}
    if isinstance(preset, CompressionPreset):
        return {"mass": 2.0}
    if isinstance(preset, DirectedPreset):
        return {"faces": {"load": [SIDE]}}
    return {}


@pytest.mark.parametrize("preset", PRODUCT_PRESETS, ids=lambda one: one.id)
def test_공개_규격의_제품_시험은_조건과_자리가_모두_맞는다(preset: specimens.Preset) -> None:
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), **_needs(preset))
    found = _check(made)
    analysis = made.conditions["analysis"]
    if isinstance(preset, ForcePreset):
        assert len(found[product.SUPPORT]) == 1  # 아랫면 하나
        assert len(found[product.PATCH]) == 1
        assert made.conditions["loads"][0]["direction"] == [0, 0, -1]
        assert analysis["type"] == "static"
    elif isinstance(preset, HandlePreset):
        assert found[product.HOLD][0]["centroid"][2] == pytest.approx(12.0)
        load = made.conditions["loads"][0]
        assert (load["type"], load["direction"]) == ("acceleration", [0, 0, 1])
        assert made.recipe["params"]["시험_배수"] == preset.setup.weight_factor
    elif isinstance(preset, CompressionPreset):
        assert len(found[product.SUPPORT]) == 1 and len(found[product.PRESSED]) == 1
        assert made.conditions["loads"][0]["on"] == product.PRESSED
    elif isinstance(preset, TorsionPreset):
        ends = [
            found[name][0]["centroid"][0] for name in (product.FIXED_END, product.TWISTED_END)
        ]
        assert ends == pytest.approx([-50.0, 50.0])  # 가장 긴 축(X)의 양 끝
        twist = made.conditions["constraints"][1]
        assert (twist["rx"], twist["x"]) == ("=시험_각도", None)
    elif isinstance(preset, CrushPreset):
        assert len(found[product.PRESSED]) == 1 and len(found[product.SUPPORT]) == 1
        assert made.conditions["loads"][0]["direction"] == [0.0, 0.0, -1.0]
    elif isinstance(preset, PressurePreset):
        assert len(found[product.WET]) == 10  # 판의 면 여섯 + 구멍 넷 — 상한(60)에 안 잘린다
        load = made.conditions["loads"][0]
        assert (load["type"], load["direction"]) == ("pressure", "normal")
        pressure = resolve_params(made.recipe)["시험_수압"]
        assert pressure == pytest.approx(preset.setup.depth * 0.00980665)
    elif isinstance(preset, AccelerationPreset):
        load = made.conditions["loads"][0]
        assert (load["type"], load["direction"]) == ("acceleration", [0, 0, 1])
        assert resolve_params(made.recipe)["시험_가속도"] == pytest.approx(
            preset.setup.acceleration_g * 9806.65
        )
    elif isinstance(preset, DirectedPreset):
        assert found[product.LOADED][0]["centroid"][0] == pytest.approx(50.0)
        kinds = [one["type"] for one in made.conditions["loads"]]
        assert kinds == ["force"] * (preset.setup.force is not None) + ["moment"] * (
            preset.setup.torque is not None
        )
        assert all(one["direction"] == [1.0, 0.0, 0.0] for one in made.conditions["loads"])
    elif isinstance(preset, VibrationPreset):
        assert len(found[product.SUPPORT]) == 1
        assert analysis["type"] == "harmonic"
        assert analysis["frequency_range"] == [preset.setup.freq_min, preset.setup.freq_max]
    else:
        assert isinstance(preset, ModalPreset)
        assert analysis["type"] == "modal"
        if preset.setup.support == "free":
            assert made.conditions["constraints"] == []
            assert analysis["modes"] == preset.setup.modes + 6  # 강체 모드 여섯을 더한다
        else:
            assert analysis["frequency_range"] == [
                preset.setup.freq_min,
                preset.setup.freq_max,
            ]


def test_누르는_자리는_변수라_DOE_로_옮겨진다() -> None:
    preset = specimens.find_builtin("iec-62368-1-t5")
    assert isinstance(preset, ForcePreset)
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), point=(20.0, -10.0))
    found = _check(made)
    assert made.recipe["params"]["시험_X"] == 20.0
    assert found[product.PATCH][0]["centroid"][:2] == pytest.approx([20.0, -10.0], abs=0.01)
    # 구멍과 겹치지 않는 자리로 — 겹치면 원이 구멍에 잘려 중심이 밀린다(형상으로 맞는 일이다).
    moved = {**made.recipe, "params": {**made.recipe["params"], "시험_X": -15.0}}
    again = _check(product.ProductTest(recipe=moved, conditions=made.conditions))
    assert again[product.PATCH][0]["centroid"][0] == pytest.approx(-15.0, abs=0.01)


def test_제품의_물성은_남기고_구속_하중은_시험의_것으로() -> None:
    preset = specimens.find_builtin("iec-60068-2-6-150-1g")
    assert isinstance(preset, VibrationPreset)
    material = {"apply_to": ["전체"], "ref": {"source": "catalog", "name": "강"}}
    given = {
        "materials": [material],
        "constraints": [{"name": "옛 고정", "type": "fixed_support", "on": "옛 면"}],
        "named_selections": [
            {"name": "옛 면", "entity": "face", "select": {"what": "faces", "role": "top"}}
        ],
    }
    made = product.apply(preset, PLATE, given, bbox=_bbox(PLATE), axis="y")
    assert made.conditions["materials"] == [material]
    assert [one["name"] for one in made.conditions["constraints"]] == ["가진대 고정"]
    assert made.conditions["loads"][0]["direction"] == [0, 1, 0]
    assert any("기존 구속" in one for one in made.notes)
    with pytest.raises(product.ProductTestError, match="진동 방향"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE), axis="w")


def test_이미_시험을_건_제품에는_다시_걸지_않는다() -> None:
    preset = specimens.find_builtin("iec-62368-1-t4")
    assert preset is not None
    once = product.apply(preset, PLATE, None, bbox=_bbox(PLATE))
    with pytest.raises(product.ProductTestError, match="시험_"):
        product.apply(preset, once.recipe, once.conditions, bbox=_bbox(PLATE))


def test_시편_규격은_제품에_걸지_않고_제품_규격은_시편을_그리지_않는다() -> None:
    bend = specimens.find_builtin("astm-d790-16")
    force = specimens.find_builtin("iec-62368-1-t5")
    assert bend is not None and force is not None
    with pytest.raises(product.ProductTestError, match="제품에 거는 시험이 아닙니다"):
        product.apply(bend, PLATE, None, bbox=_bbox(PLATE))
    with pytest.raises(ValueError, match="제품에 적용"):
        specimens.build(force)


def test_고른_면을_누르면_그_면의_반대_방향으로_누른다() -> None:
    preset = specimens.find_builtin("iec-62368-1-t4")
    assert preset is not None
    side = FacePick((50.0, 5.0, 6.0), (1.0, 0.0, 0.0))  # +X 옆면
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [side]})
    found = _check(made)
    assert found[product.PATCH][0]["centroid"] == pytest.approx([50.0, 5.0, 6.0], abs=0.01)
    assert made.conditions["loads"][0]["direction"] == [-1.0, 0.0, 0.0]
    assert made.recipe["params"]["시험_Z"] == 6.0
    # 아랫면을 누르면 받침은 윗면이다.
    under = FacePick((10.0, 5.0, 0.0), (0.0, 0.0, -1.0))
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [under]})
    found = _check(made)
    assert found[product.SUPPORT][0]["centroid"][2] == pytest.approx(12.0)
    assert made.conditions["loads"][0]["direction"] == [0.0, 0.0, 1.0]
    with pytest.raises(product.ProductTestError, match="하나만"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [side, under]})


def test_곡면도_고른다_손잡이_구멍_둘() -> None:
    preset = specimens.find_builtin("iec-62368-1-8.8-handle")
    assert preset is not None
    holes = [
        FacePick((44.0, 20.0, 6.0), (1.0, 0.0, 0.0), "cylinder"),
        FacePick((-44.0, 20.0, 6.0), (-1.0, 0.0, 0.0), "cylinder"),
    ]
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"support": holes})
    found = _check(made)
    centers = sorted(one["centroid"][0] for one in found[product.HOLD])
    assert centers == pytest.approx([-40.0, 40.0], abs=0.01)
    with pytest.raises(product.ProductTestError, match="3D에서 골라야"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE))


def test_비틀림은_축을_고르고_끝_면을_바꿀_수_있다() -> None:
    preset = specimens.find_builtin("twist-example-6deg")
    assert preset is not None
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), axis="y")
    found = _check(made)
    assert found[product.FIXED_END][0]["centroid"][1] == pytest.approx(-30.0)
    assert made.ends == {product.FIXED_END: (1, -30.0), product.TWISTED_END: (1, 30.0)}
    twist = made.conditions["constraints"][1]
    assert (twist["ry"], twist["y"], twist["rx"]) == ("=시험_각도", None, 0)
    # 고른 끝은 「끝에 있어야 한다」 를 확인하지 않는다 — 사람이 고른 것이다.
    picked = FacePick((0.0, 0.0, 12.0), (0.0, 0.0, 1.0))
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"twist": [picked]})
    assert list(made.ends) == [product.FIXED_END]


def test_적층_압축은_무게와_적재_높이로_하중을_정한다() -> None:
    preset = specimens.find_builtin("astm-d642-2700x3")
    assert isinstance(preset, CompressionPreset)
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), mass=2.0)
    values = resolve_params(made.recipe)
    assert values["시험_하중"] == pytest.approx(2.0 * 9.80665 * (2700 - 12) / 12 * 3)
    with pytest.raises(product.ProductTestError, match="무게"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE))
    tall = preset.model_copy(
        update={"setup": preset.setup.model_copy(update={"stack_height": 10})}
    )
    with pytest.raises(product.ProductTestError, match="적재 높이"):
        product.apply(tall, PLATE, None, bbox=_bbox(PLATE), mass=1.0)


def test_시험이_고르지_않는_자리는_막는다() -> None:
    compression = specimens.find_builtin("ista-stack-5x3")
    free = specimens.find_builtin("astm-e1876-free")
    assert compression is not None and free is not None
    with pytest.raises(product.ProductTestError, match="고르지 않습니다"):
        product.apply(
            compression, PLATE, None, bbox=_bbox(PLATE), mass=1.0, faces={"support": [TOP]}
        )
    with pytest.raises(product.ProductTestError, match="자유-자유"):
        product.apply(free, PLATE, None, bbox=_bbox(PLATE), faces={"support": [TOP]})


def test_옆면을_압착하면_반대쪽_끝_면이_받침이다() -> None:
    preset = specimens.find_builtin("iec-62133-2-crush")
    assert preset is not None
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [SIDE]})
    found = _check(made)
    assert found[product.SUPPORT][0]["centroid"][0] == pytest.approx(-50.0)
    assert made.ends == {product.SUPPORT: (0, -50.0)}
    assert made.conditions["loads"][0]["direction"] == [-1.0, 0.0, 0.0]


def test_방향_하중은_고른_면과_방향을_쓴다() -> None:
    preset = specimens.find_builtin("usb-type-c-wrench-updown")
    assert isinstance(preset, DirectedPreset)
    hole = FacePick((44.0, 20.0, 6.0), (1.0, 0.0, 0.0), "cylinder")
    with pytest.raises(product.ProductTestError, match="방향을 정하십시오"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [hole]})
    with pytest.raises(product.ProductTestError, match="3D에서 골라야"):
        product.apply(preset, PLATE, None, bbox=_bbox(PLATE))
    made = product.apply(
        preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [hole]}, direction=(0, 2, 0)
    )
    found = _check(made)
    assert found[product.LOADED][0]["centroid"][:2] == pytest.approx([40.0, 20.0], abs=0.01)
    moment = made.conditions["loads"][0]
    assert (moment["type"], moment["direction"]) == ("moment", [0.0, 1.0, 0.0])
    assert resolve_params(made.recipe)["시험_토크"] == 2.0
    assert moment["magnitude"] == "=시험_토크 * 1000"  # N·m → N·mm


def test_수압은_고른_면에만_걸_수_있다() -> None:
    preset = specimens.find_builtin("iec-60529-ipx7")
    assert preset is not None
    made = product.apply(preset, PLATE, None, bbox=_bbox(PLATE), faces={"load": [TOP]})
    found = _check(made)
    assert len(found[product.WET]) == 1
    assert not any("바깥 면만" in one for one in made.notes)
