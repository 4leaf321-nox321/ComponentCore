"""시험 시편 — 규격 프리셋으로 시편 · 시험 지그 · 해석 조건을 그리고, 지그 생성기가 같은
규칙으로 굽힘 픽스처를 놓는다.

공개 규격 프리셋은 **전부** 여기서 만들어 본다 — 값을 고치거나 더한 프리셋이 레시피 · 조건에서
깨지면 CI 가 막는다(코드에 둔 까닭, ADR 0006).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core import conditions, pipeline, specimens
from app.core.jig_recipe import recipe_of
from app.core.options import JigOptions
from app.core.recipe import evaluate, parse
from app.core.recipe.params import resolve, resolve_params
from app.core.recipe.topology import bodies, regions
from app.core.specimens import bending
from app.core.specimens.presets import BendingPreset


def _made(recipe: dict[str, Any]) -> Any:
    return evaluate(parse(recipe), resolve_file=None)


#: 굽힘 규격만 — 정하중 · 진동은 시편이 아니라 제품에 건다(`test_core_product_tests.py`).
BENDING = [one for one in specimens.builtin() if isinstance(one, BendingPreset)]


def _bend(preset_id: str) -> BendingPreset:
    preset = specimens.find_builtin(preset_id)
    assert isinstance(preset, BendingPreset)
    return preset


@pytest.mark.parametrize("preset", BENDING, ids=lambda one: one.id)
def test_공개_규격_프리셋은_시편_지그_조건이_모두_맞는다(preset: BendingPreset) -> None:
    made = specimens.build(preset)
    shape = _made(made.recipe)
    names = [one["name"] for one in bodies(shape.shape)]
    nose_names = bending.noses(preset.setup.points)
    assert names == ["시편", "롤러_1", "롤러_2", *nose_names]
    assert made.conditions is not None
    conditions.parse(made.conditions, names)  # 없는 바디 · 강체 규칙을 어기면 여기서 실패
    found, unresolved = regions(shape.shape, made.conditions["named_selections"], shape.tags)
    assert unresolved == []
    assert len(found["지지 롤러"]) == 2 and len(found["로딩 노즈"]) == len(nose_names)
    assert len(found["시편 중앙"]) == 1
    # 롤러는 시편 아랫면에, 노즈는 윗면에 닿는다(축 높이 = 반지름).
    values = resolve_params(made.recipe)
    span = bending.span_at(preset.setup, preset.specimen.thickness)
    assert values["지지_간격"] == pytest.approx(span)
    box = shape.shape.bounding_box()
    low, top = (
        -2 * values["지지_반지름"],
        preset.specimen.thickness + 2 * values["노즈_반지름"],
    )
    assert pytest.approx((low, top), abs=1e-3) == (box.min.Z, box.max.Z)


def test_두께를_바꾸면_지지_간격과_처짐이_따라온다() -> None:
    preset = _bend("astm-d790-16")
    made = specimens.build(preset)
    recipe = {**made.recipe, "params": {**made.recipe["params"], "두께": 4.0}}
    values = resolve_params(recipe)
    assert values["지지_간격"] == pytest.approx(64.0)  # 16 x 4
    assert values["처짐"] == pytest.approx(0.05 * 64.0**2 / (6 * 4.0))
    # 조건의 숫자도 같은 변수로 풀린다 — DOE 의 설계점마다.
    assert made.conditions is not None
    solved = resolve({**made.conditions, "params": recipe["params"]})
    press = next(one for one in solved["constraints"] if one["name"] == "노즈 가압")
    assert press["z"] == pytest.approx(-values["처짐"])


def test_4점_굽힘의_처짐은_하중_간격을_안다() -> None:
    preset = _bend("astm-d6272-16")
    values = resolve_params(specimens.build(preset).recipe)
    span, inner = values["지지_간격"], values["하중_간격"]
    assert inner == pytest.approx(span * 0.3333)
    # 하중 간격 1/3 이면 D6272 의 0.21 rL²/d 와 같다.
    assert values["처짐"] == pytest.approx(0.2130 * 0.05 * span**2 / 3.2, rel=2e-3)


def test_두께에_따라_갈리는_반지름은_만들_때의_두께로_정하고_말한다() -> None:
    preset = _bend("iso-178")
    thin = specimens.build(preset, thickness=2.0)
    assert resolve_params(thin.recipe)["지지_반지름"] == 2.0
    assert any("두께를 바꾸면 반지름을 확인" in one for one in thin.notes)
    assert resolve_params(specimens.build(preset).recipe)["지지_반지름"] == 5.0


def test_지그나_조건_없이_시편만() -> None:
    preset = BENDING[0]
    alone = specimens.build(preset, fixture=False)
    assert alone.conditions is None
    assert [one["id"] for one in alone.recipe["nodes"]] == ["시편"]
    no_conditions = specimens.build(preset, conditions=False)
    assert no_conditions.conditions is None
    assert "처짐" not in no_conditions.recipe["params"]


def test_틀린_프리셋은_어느_칸이_왜인지_말한다() -> None:
    base = _bend("astm-d6272-16")
    raw = base.model_dump()
    with pytest.raises(ValidationError, match="load_span"):
        specimens.parse_preset({**raw, "setup": {**raw["setup"], "load_span": None}})
    with pytest.raises(ValidationError, match="시편 길이"):
        specimens.parse_preset({**raw, "specimen": {**raw["specimen"], "length": 50}})
    rule = [{"max_thickness": 3, "radius": 2}]
    with pytest.raises(ValidationError, match="마지막 줄"):
        specimens.parse_preset({**raw, "setup": {**raw["setup"], "support_radius": rule}})


BAR = {"kind": "box", "length": 127, "width": 12.7, "height": 3.2}


def _setup(preset_id: str) -> dict[str, Any]:
    preset = _bend(preset_id)
    return preset.setup.model_dump()


def test_지그_생성기는_시험_규격의_규칙으로_스팬과_롤러를_정한다() -> None:
    opts = JigOptions(
        kind="bending", bending_preset="astm-d790-16", bending_setup=_setup("astm-d790-16")
    )
    made = pipeline.analyze(BAR, opts)
    rollers, noses = made.plan.rollers, made.plan.noses
    assert sorted(one.position[0] for one in rollers) == [-25.6, 25.6]  # 16 x 3.2 / 2
    assert {one.diameter for one in rollers} == {10.0} and noses[0].diameter == 10.0
    assert any("astm-d790-16" in one and "51.2" in one for one in made.plan.notes)
    assert made.interference.ok, made.interference.summary()


def test_4점_굽힘은_노즈_둘을_하중_간격의_양_끝에_놓는다() -> None:
    opts = JigOptions(
        kind="bending", bending_preset="astm-d6272-16", bending_setup=_setup("astm-d6272-16")
    )
    made = pipeline.analyze(BAR, opts)
    noses = made.plan.noses
    assert [one.label for one in noses] == ["로딩_노즈_1", "로딩_노즈_2"]
    span = 16 * 3.2
    assert [one.position[0] for one in noses] == pytest.approx([-span / 6, span / 6], abs=1e-2)
    assert made.interference.ok, made.interference.summary()
    labels = {str(child.label) for child in made.preview_shape().children}
    assert {"롤러_1", "롤러_2", "로딩_노즈_1", "로딩_노즈_2"} <= labels

    # 레시피도 같은 형상 — 노즈 둘이 변수 하나(하중_간격)로 함께 벌어진다.
    recipe = recipe_of(made.plan, opts)
    assert recipe["params"]["하중_간격"] == pytest.approx(span / 3, abs=1e-2)
    drawn = _made(recipe)
    box = made.jig.bounding_box()
    got = drawn.summary()["bbox"]
    assert [round(v, 1) for v in got["max"]] == [
        round(v, 1) for v in (box.max.X, box.max.Y, box.max.Z)
    ]


def test_규격_없이_4점을_고르면_하중_간격은_스팬의_삼분의_일() -> None:
    made = pipeline.analyze(
        {"kind": "box", "length": 80, "width": 50, "height": 20},
        JigOptions(kind="bending", bending_points=4),
    )
    noses = made.plan.noses
    assert len(noses) == 2
    assert noses[1].position[0] - noses[0].position[0] == pytest.approx(64 / 3, abs=1e-2)
