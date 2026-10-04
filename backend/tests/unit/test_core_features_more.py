"""특징 인식을 넓혔다 — 경사면 · 옆 구멍 · 포켓(2026-10-04). 전에는 조용히 버려져 계획이 「없는
것」 으로 다뤘다.

- 인식: 기운 평면은 `slope_up` / `slope_down`, 축이 X · Y 인 옆 구멍은 `side_through` /
  `side_blind`, 사방이 벽인 바닥은 `pocket`.
- 계획: 바닥 구멍이 모자라면 옆 구멍에 **측면 위치 핀**(블록 + 가로 핀), 받침대는 옆 구멍
  입구를 덮지 않고, 클램프는 포켓 바닥에 내리지 않으며, 경사면은 피했다고 말한다.
- 레시피는 생성된 지그와 같은 형상이다(측면 핀까지).
"""

from __future__ import annotations

from typing import Any

from build123d import Box, Cylinder, Part, Pos, Rot

from app.core import features, geometry, pipeline
from app.core.jig_recipe import recipe_of
from app.core.model import Feature
from app.core.options import JigOptions
from app.core.recipe import evaluate, parse

BLOCK = (100.0, 60.0, 30.0)


def _block() -> Part:
    return Box(*BLOCK)


def _x_hole(part: Part, z: float, radius: float = 5.0, depth: float | None = None) -> Part:
    """X 축 구멍 — `depth` 를 주면 +X 면에서 그 깊이만큼(막힌 구멍), 안 주면 관통."""
    length = depth or BLOCK[0] + 10
    x = BLOCK[0] / 2 - length / 2 if depth else 0.0
    return part - Pos(x, 0, z) * Rot(0, 90, 0) * Cylinder(radius, length)


def _found(shape: Part) -> list[Feature]:
    return features.recognize(geometry.understand(shape))


def _count(found: list[Feature], kind: str, role: str) -> int:
    return sum(1 for one in found if one.kind == kind and one.role == role)


def _same_shape(made: pipeline.JigBuild, opts: JigOptions) -> dict[str, Any]:
    recipe = recipe_of(made.plan, opts)
    drawn = evaluate(parse(recipe), resolve_file=None)
    box = made.jig.bounding_box()
    got = drawn.summary()["bbox"]
    assert [round(v, 1) for v in got["min"]] == [
        round(v, 1) for v in (box.min.X, box.min.Y, box.min.Z)
    ]
    assert [round(v, 1) for v in got["max"]] == [
        round(v, 1) for v in (box.max.X, box.max.Y, box.max.Z)
    ]
    assert abs(float(drawn.shape.volume) - float(made.jig.volume)) < 1.0
    return recipe


def test_옆_구멍을_알아보고_바닥_구멍이_없으면_측면_핀을_꽂는다() -> None:
    shape = _x_hole(_block(), 0.0)  # 높이 30 의 가운데(제품 좌표로 z=15)
    found = _found(shape)
    (hole,) = [one for one in found if one.role == "side_through"]
    assert hole.kind == "hole" and hole.axis == (1.0, 0.0, 0.0)
    assert hole.radius == 5.0 and hole.depth == 100.0

    opts = JigOptions(kind="clamped")
    made = pipeline.analyze(shape, opts)
    kinds = [one.kind for one in made.plan.locators]
    assert kinds[0] == "side_pin"
    pin = made.plan.locators[0]
    assert pin.position == (-50.0, 0.0, 15.0) and pin.direction == (1.0, 0.0, 0.0)
    assert pin.diameter == round(2 * (5.0 - opts.locator_pin_clearance), 3)
    assert any("측면 핀" in note for note in made.plan.notes)
    # 핀은 구멍 안에서 틈을 두고, 블록은 옆면에 닿을 뿐 — 겹침이 없다.
    assert made.interference.ok, [one for one in made.interference.items if not one.ok]
    recipe = _same_shape(made, opts)
    assert {"측면_핀_1", "측면_핀_1_블록", "측면_핀_1_핀"} <= {
        one["id"] for one in recipe["nodes"]
    }


def test_막힌_옆_구멍은_열린_쪽에서_꽂는다() -> None:
    shape = _x_hole(_block(), 0.0, depth=20.0)  # +X 면에서 20 mm
    (hole,) = [one for one in _found(shape) if one.kind == "hole"]
    assert hole.role == "side_blind" and hole.depth == 20.0
    made = pipeline.analyze(shape, JigOptions(kind="clamped"))
    pin = next(one for one in made.plan.locators if one.kind == "side_pin")
    assert pin.position[0] == 50.0 and pin.direction == (-1.0, 0.0, 0.0)
    assert pin.engagement == 15.0  # 깊이의 80 % 와 최대 15 중 작은 것
    assert made.interference.ok


def test_받침대는_옆_구멍_입구를_덮지_않는다() -> None:
    # 낮은 Y 막힌 구멍이 측면 핀을 받고, X 면의 관통 구멍 입구(가운데)는 받침대가 비켜 간다.
    shape = _x_hole(_block(), 0.0)
    shape = shape - Pos(0, -BLOCK[1] / 2 + 6, -7) * Rot(90, 0, 0) * Cylinder(3.0, 12)
    made = pipeline.analyze(shape, JigOptions(kind="clamped"))
    side, *rests = made.plan.locators
    assert side.kind == "side_pin" and side.direction == (0.0, 1.0, 0.0)
    assert [one.kind for one in rests] == ["rest"]
    (rest,) = rests
    assert abs(rest.direction[0]) == 1.0  # 핀 축과 직교하는 옆면(X 면)
    w = JigOptions().locator_rest_size[0]
    assert abs(rest.position[1]) > w / 2 + 5.0  # X 구멍 입구(y=0)를 비켰다
    assert made.interference.ok


def test_포켓을_알아보고_클램프를_그_바닥에_내리지_않는다() -> None:
    shape = _block() - Pos(0, 0, 10) * Box(30, 20, 10.01)  # 윗면 가운데 깊이 10
    found = _found(shape)
    assert _count(found, "pocket", "top") == 1
    pocket = next(one for one in found if one.kind == "pocket")
    assert pocket.depth is not None and round(pocket.depth, 1) == 10.0 and pocket.area == 600.0
    assert _count(found, "plane", "step") == 0  # 전에는 「단차」 였다

    made = pipeline.analyze(shape, JigOptions(kind="clamped", clamp_count=4))
    assert any("포켓 바닥 1곳" in note for note in made.plan.notes)
    for clamp in made.plan.clamps:
        x, y, z = clamp.pad_position
        assert not (abs(x) < 15 and abs(y) < 10), clamp  # 포켓 안에 패드가 없다
        assert z == 30.0
    assert made.interference.ok


def test_턱은_포켓이_아니다() -> None:
    shape = _block() - Pos(40, 0, 10) * Box(20.01, 60.01, 10.01)  # +X 끝을 깎은 턱
    found = _found(shape)
    assert _count(found, "pocket", "top") == 0 and _count(found, "plane", "step") == 1


def test_경사면을_알아보고_피했다고_말한다() -> None:
    shape = _block() - Pos(50, 0, 15) * Rot(0, 45, 0) * Box(20, 70, 20)  # +X 윗모서리를 45°
    found = _found(shape)
    slopes = [one for one in found if one.role == "slope_up"]
    assert len(slopes) == 1 and slopes[0].normal is not None
    nx, _, nz = slopes[0].normal
    assert round(nx, 2) == round(nz, 2) == 0.71
    made = pipeline.analyze(shape, JigOptions(kind="clamped"))
    assert any("경사면 1곳" in note for note in made.plan.notes)
    assert made.interference.ok
