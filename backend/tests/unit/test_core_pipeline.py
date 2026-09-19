"""코어를 서버 없이 돌린다 — 기하 알고리즘은 여기서 본다."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import features, geometry, pipeline, planning, primitives
from app.core.options import JigOptions


def test_정규화는_바닥을_0_으로(tmp_path: Path) -> None:
    geom = geometry.understand(
        primitives.build({"kind": "box", "length": 10, "width": 20, "height": 30})
    )
    assert geom.bbox.min == (-5.0, -10.0, 0.0)
    assert geom.bbox.size == (10.0, 20.0, 30.0)


def test_구멍과_평면을_알아본다() -> None:
    geom = geometry.understand(
        primitives.build(
            {"kind": "plate_with_holes", "length": 100, "width": 60, "thickness": 12}
        )
    )
    found = features.recognize(geom)
    holes = [one for one in found if one.kind == "hole"]
    assert len(holes) == 4
    assert all(one.role == "through" for one in holes)
    assert features.largest(found, "plane", "bottom") is not None
    assert features.largest(found, "plane", "top") is not None


def test_핀은_가장_먼_두_구멍(tmp_path: Path) -> None:
    result = pipeline.run(
        {"kind": "plate_with_holes", "length": 100, "width": 60, "thickness": 12},
        JigOptions(export_gltf=False),
        tmp_path,
    )
    pins = [one for one in result.plan.locators if one.kind == "pin"]
    assert len(pins) == 2
    (x0, y0, _), (x1, y1, _) = pins[0].position, pins[1].position
    assert (x0 * x1 < 0) and (y0 * y1 < 0)  # 대각선
    assert result.interference.ok, result.interference.summary()


def test_구멍_없는_상자는_옆면_레스트(tmp_path: Path) -> None:
    result = pipeline.run(
        {"kind": "box", "length": 60, "width": 40, "height": 20},
        JigOptions(export_gltf=False),
        tmp_path,
    )
    kinds = [one.kind for one in result.plan.locators]
    assert kinds == ["rest", "rest", "rest"]
    assert result.interference.ok, result.interference.summary()
    assert (tmp_path / "jig.step").exists()


def test_시연_제품은_늘_된다(tmp_path: Path) -> None:
    result = pipeline.run(None, JigOptions(), tmp_path)
    assert result.interference.ok, result.interference.summary()
    assert len(result.plan.clamps) == 2
    assert {"jig_glb", "product_glb", "jig_step", "assembly_step"} <= set(result.files)
    assert all(path.stat().st_size > 100 for path in result.files.values())


def test_너무_좁은_바닥은_계획에서_거절() -> None:
    geom = geometry.understand(
        primitives.build({"kind": "box", "length": 8, "width": 8, "height": 30})
    )
    with pytest.raises(planning.PlanningError):
        planning.plan(geom, features.recognize(geom), JigOptions())


def test_옵션은_모르는_키를_버린다() -> None:
    opts = JigOptions.from_dict({"support_count": 3, "nonsense": 1})
    assert opts.support_count == 3
    assert "nonsense" not in opts.to_dict()


def test_모서리마다_구멍이_있어도_클램프_자리를_찾는다(tmp_path: Path) -> None:
    """모서리 후보가 전부 구멍에 걸리면 변의 중점이 받는다. 적게 놓이면 말한다."""
    result = pipeline.run(
        {
            "kind": "plate_with_holes",
            "length": 100,
            "width": 60,
            "thickness": 12,
            "hole_margin": 12,
        },
        JigOptions(export_gltf=False, clamp_count=2),
        tmp_path,
    )
    assert len(result.plan.clamps) == 2, result.plan.notes
    tiny = pipeline.run(
        {
            "kind": "plate_with_holes",
            "length": 50,
            "width": 40,
            "thickness": 8,
            "hole_margin": 10,
        },
        JigOptions(export_gltf=False, clamp_count=2),
        tmp_path / "tiny",
    )
    if len(tiny.plan.clamps) < 2:
        assert any("클램프를" in n for n in tiny.plan.notes)  # 어느 쪽이든 이유를 말한다


def test_클램프_팔은_벽을_지나지_않는다(tmp_path: Path) -> None:
    """벽 앞의 바닥판을 누르는 클램프 — 기둥이 벽 뒤에 서면 팔이 벽을 뚫는다(실측)."""
    result = pipeline.run(
        {"kind": "bracket", "length": 90, "width": 60, "height": 45, "thickness": 8},
        JigOptions(export_gltf=False, clamp_count=2),
        tmp_path,
    )
    assert result.interference.ok, result.interference.summary()
    for clamp in result.plan.clamps:
        # 벽은 -Y 쪽(y < -22). 패드가 벽 앞(y > -22)이면 기둥도 벽 뒤(-Y 변)에 서면 안 된다.
        if clamp.pad_position[1] > -22:
            assert clamp.post_position[1] > -30, clamp


PLATE = {
    "kind": "plate_with_holes",
    "length": 100,
    "width": 60,
    "thickness": 12,
    "hole_diameter": 8.5,
}
BOX = {"kind": "box", "length": 80, "width": 50, "height": 20}


def _labels(made: pipeline.JigBuild) -> set[str]:
    return {str(child.label) for child in made.preview_shape().children}


def test_볼트_고정은_관통_구멍으로_조이고_판에_탭_구멍을_낸다() -> None:
    made = pipeline.analyze(PLATE, JigOptions(kind="bolted", bolt_max_count=4))
    assert made.plan.kind == "bolted"
    assert len(made.plan.bolts) == 4 and not made.plan.supports and not made.plan.clamps
    # 8.5 구멍 → M8, 판에는 호칭 지름의 탭 구멍.
    nominals = {bolt.nominal for bolt in made.plan.bolts}
    assert nominals == {8.0}
    assert len(made.plan.base_plate.holes) == 4
    assert made.plan.product_lift == 0  # 스페이서 없이 판에 바로 앉는다
    assert made.interference.ok, made.interference.summary()
    assert {"볼트 1", "볼트 4", "바닥판", "제품"} <= _labels(made)

    # 스페이서를 주면 볼트마다 하나씩 서고 부품이 그만큼 뜬다.
    lifted = pipeline.analyze(
        PLATE, JigOptions(kind="bolted", bolt_spacer_height=8, bolt_head="socket")
    )
    assert lifted.plan.product_lift == 8
    assert {"스페이서 1", "스페이서 4"} <= _labels(lifted)
    assert lifted.interference.ok, lifted.interference.summary()

    # 구멍 없는 상자는 볼트 고정을 못 한다 — 이유를 말한다.
    with pytest.raises(planning.PlanningError, match="관통 구멍"):
        pipeline.analyze(BOX, JigOptions(kind="bolted"))


def test_3점_굽힘은_긴_변으로_스팬을_잡는다() -> None:
    made = pipeline.analyze(BOX, JigOptions(kind="bending"))
    assert made.plan.kind == "bending"
    rollers = made.plan.rollers
    assert len(rollers) == 2 and made.plan.nose is not None
    # 긴 변이 X 라 롤러는 X 로 ±스팬/2, 축은 Y 를 따라 눕는다. 스팬 = 80 x 0.8.
    assert sorted(r.position[0] for r in rollers) == [-32.0, 32.0]
    assert {r.along for r in rollers} == {"y"}
    assert rollers[0].length == 50 + 2 * 5  # 폭 + 여유
    assert made.plan.nose.position[2] == 20 + 5  # 윗면 + 반지름
    assert made.interference.ok, made.interference.summary()
    assert {"롤러 1", "롤러 2", "로딩 노즈"} <= _labels(made)
    # 스팬이 길이를 넘으면 거절.
    with pytest.raises(planning.PlanningError, match="스팬"):
        pipeline.analyze(BOX, JigOptions(kind="bending", bending_span=90))


def test_낙하_자세는_고른_면이_아래를_본다() -> None:
    edge = pipeline.analyze(
        BOX, JigOptions(kind="drop", drop_orientation="edge", drop_impactor="ball")
    )
    assert edge.plan.kind == "drop"
    # 모서리가 아래면 폭은 그대로, 높이 · 길이는 45° 돌아 같아진다.
    sx, sy, sz = edge.geometry.bbox.size
    assert sy == 50 and abs(sx - sz) < 0.01 and sx > 70
    assert edge.plan.impactor is not None and edge.plan.impactor.kind == "ball"
    assert edge.plan.product_lift == 1.0
    assert not edge.plan.base_plate.holes and edge.plan.base_plate.mount_hole_diameter == 0
    assert {"바닥", "임팩터", "제품"} == _labels(edge)
    assert edge.interference.ok, edge.interference.summary()

    side = pipeline.analyze(BOX, JigOptions(kind="drop", drop_orientation="+x"))
    assert side.geometry.bbox.size[2] == 80  # 긴 변이 세로로 선다
    assert side.plan.impactor is None
    with pytest.raises(geometry.GeometryError, match="낙하 자세"):
        pipeline.analyze(BOX, JigOptions(kind="drop", drop_orientation="sideways"))
