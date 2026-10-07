"""규격 부품 — 계획이 요구(받침 높이 · 핀 지름 · 패드 자리)에 맞는 받침 · 위치 핀 · 토글
클램프를 골라 놓는다. 맞는 것이 없으면 즉석 도형으로 두고 그렇다고 말한다. 레시피는 그 규격품을
`component` 로 가리키고, 생성된 지그와 같은 형상이다.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core import pipeline
from app.core.jig_recipe import recipe_of
from app.core.options import JigOptions
from app.core.recipe import evaluate, parse
from app.core.standard import LibraryPart

#: 구멍판 — 100 x 60 x 12, 바닥에서 열린 Ø8.5 관통 구멍(위치 핀 자리).
PLATE = {
    "kind": "plate_with_holes",
    "length": 100,
    "width": 60,
    "thickness": 12,
    "hole_diameter": 8.5,
}

SUPPORT = LibraryPart(
    source="part:s@1",
    kind="support",
    part_no="SUP-16",
    name="받침 Ø16",
    spec={
        "top_diameter": 16,
        "height": 25,
        "height_param": "높이",
        "height_min": 10,
        "height_max": 60,
    },
    recipe={
        "params": {"높이": 25},
        "nodes": [
            {
                "id": "몸통",
                "op": "cylinder",
                "radius": 8,
                "height": "=높이",
                "align": ["center", "center", "min"],
            }
        ],
    },
)
FIXED_SUPPORT = LibraryPart(
    source="part:f@2",
    kind="support",
    part_no="SUP-10-30",
    name="받침 Ø10 x 30",
    spec={"top_diameter": 10, "height": 30},
    recipe={
        "nodes": [
            {
                "id": "몸통",
                "op": "cylinder",
                "radius": 5,
                "height": 30,
                "align": ["center", "center", "min"],
            }
        ]
    },
)
PIN = LibraryPart(
    source="part:p@1",
    kind="pin",
    part_no="PIN-8.4",
    name="위치 핀 Ø8.4",
    spec={
        "diameter": 8.4,
        "length": 35,
        "length_param": "길이",
        "length_min": 20,
        "length_max": 60,
    },
    recipe={
        "params": {"길이": 35},
        "nodes": [
            {
                "id": "핀",
                "op": "cylinder",
                "radius": 4.2,
                "height": "=길이",
                "align": ["center", "center", "min"],
            }
        ],
    },
)
#: 토글 클램프 — 베이스 40 x 30, 팔이 +X 로 60 뻗어 누른 상태의 패드 중심이 (60, 0, 30).
CLAMP = LibraryPart(
    source="part:c@1",
    kind="clamp",
    part_no="TC-60",
    name="토글 클램프 60",
    spec={
        "reach": 60,
        "pad_height": 30,
        "pad_diameter": 10,
        "base_length": 40,
        "base_width": 30,
    },
    recipe={
        "nodes": [
            {
                "id": "베이스",
                "op": "box",
                "length": 40,
                "width": 30,
                "height": 8,
                "align": ["center", "center", "min"],
            },
            {
                "id": "기둥",
                "op": "box",
                "length": 12,
                "width": 12,
                "height": 40,
                "at": [-10, 0, 8],
                "align": ["center", "center", "min"],
            },
            {
                "id": "팔",
                "op": "box",
                "length": 76,
                "width": 12,
                "height": 8,
                "at": [-16, 0, 48],
                "align": ["min", "center", "min"],
            },
            {
                "id": "스핀들",
                "op": "cylinder",
                "radius": 5,
                "height": 18,
                "at": [60, 0, 30],
                "align": ["center", "center", "min"],
            },
            {"id": "클램프", "op": "union", "targets": ["베이스", "기둥", "팔", "스핀들"]},
        ]
    },
)


def _same_shape(
    made: pipeline.JigBuild, opts: JigOptions, library: list[LibraryPart]
) -> dict[str, Any]:
    recipe = recipe_of(made.plan, opts)
    by_source = {one.source: one.recipe for one in library}
    drawn = evaluate(
        parse(recipe), resolve_file=None, resolve_component=lambda key: by_source[key]
    )
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


def test_받침_핀_클램프를_규격품으로_골라_놓고_부품표를_붙인다() -> None:
    library = [SUPPORT, PIN, CLAMP]
    opts = JigOptions(kind="clamped")
    made = pipeline.analyze(PLATE, opts, library=library)
    plan = made.plan
    assert plan.product_lift == opts.support_height  # 높이를 변수로 맞춘다
    assert all(
        one.standard is not None and one.standard.part_no == "SUP-16" for one in plan.supports
    )
    assert all(one.diameter == 16 for one in plan.supports)
    pins = [one for one in plan.locators if one.kind == "pin"]
    assert pins and all(one.standard is not None and one.diameter == 8.4 for one in pins)
    assert {one.engagement for one in pins} == {9.6}  # 깊이 12 의 80 %
    assert plan.clamps and all(one.standard is not None for one in plan.clamps)
    for clamp in plan.clamps:
        # 패드 자리(제품 윗면 z=12)에 누르는 높이 30 을 맞추려면 받침 블록 25 + 12 - 30 = 7.
        assert clamp.riser == 7.0 and clamp.base_size == 40
    assert made.interference.ok, [one for one in made.interference.items if not one.ok]

    bom = {row["part_no"]: row["count"] for row in plan.summary()["bom"]}
    assert bom == {
        "SUP-16": len(plan.supports),
        "PIN-8.4": len(pins),
        "TC-60": len(plan.clamps),
    }

    recipe = _same_shape(made, opts, library)
    support = next(one for one in recipe["nodes"] if one["id"] == "받침_1")
    assert support["op"] == "component" and support["source"] == "part:s@1"
    assert support["params"] == {"높이": "=받침_높이"}  # 받침 높이를 따라간다
    pin = next(one for one in recipe["nodes"] if one["id"] == "위치_핀_1")
    assert pin["params"] == {"길이": "=받침_높이 + 9.6"}
    assert {"클램프_1_받침블록", "클램프_1_본체", "클램프_1"} <= {
        one["id"] for one in recipe["nodes"]
    }
    # 사양에 고정 나사 자리가 없으면 판에 탭 구멍을 못 낸다 — 그렇다고 말한다.
    assert any("TC-60" in note and "고정 나사 자리가 없어" in note for note in plan.notes)


def test_고정_높이_받침이면_받침_높이가_그_높이가_된다() -> None:
    made = pipeline.analyze(PLATE, JigOptions(kind="clamped"), library=[FIXED_SUPPORT])
    assert made.plan.product_lift == 30
    assert any("받침 높이를 30 mm로" in note for note in made.plan.notes)
    assert all(one.standard is not None for one in made.plan.supports)
    _same_shape(made, JigOptions(kind="clamped"), [FIXED_SUPPORT])


def test_맞는_것이_없으면_제작품으로_두고_말한다() -> None:
    thin = LibraryPart(
        **{
            **PIN.__dict__,
            "source": "part:t@1",
            "part_no": "PIN-6",
            "spec": {**PIN.spec, "diameter": 6},
        }
    )
    tall = LibraryPart(
        **{
            **CLAMP.__dict__,
            "source": "part:x@1",
            "part_no": "TC-TALL",
            "spec": {**CLAMP.spec, "pad_height": 80},
        }
    )
    made = pipeline.analyze(PLATE, JigOptions(kind="clamped"), library=[thin, tall])
    assert all(one.standard is None for one in made.plan.locators)
    assert all(one.standard is None for one in made.plan.clamps)
    notes = " ".join(made.plan.notes)
    assert "규격 위치 핀이 없어" in notes and "규격 클램프가 없어" in notes
    assert made.plan.summary()["bom"] == []


def test_끄면_즉석_도형이다() -> None:
    made = pipeline.analyze(
        PLATE, JigOptions(kind="clamped", standard_parts=False), library=[SUPPORT, PIN, CLAMP]
    )
    assert made.plan.summary()["bom"] == []
    assert all(one.standard is None for one in made.plan.supports)


#: 고정 나사 자리를 적은 토글 클램프 — 베이스 40 x 30 의 네 귀에 M5.
MOUNTED = LibraryPart(
    **{
        **CLAMP.__dict__,
        "source": "part:m@1",
        "part_no": "TC-60M",
        "spec": {
            **CLAMP.spec,
            "mount_thread": "M5",
            "mount_holes": [[-15, -10], [-15, 10], [15, -10], [15, 10]],
        },
    }
)


@pytest.mark.parametrize(("lift", "riser"), [(25, 7.0), (18, 0.0)])
def test_클램프_고정_나사_자리에_판은_탭_구멍_받침_블록은_여유_구멍(
    lift: float, riser: float
) -> None:
    """받침 높이 25 면 받침 블록(25 + 12 - 30 = 7)에 올라 나사가 블록을 지나고, 18 이면 누르는
    높이가 딱 맞아 판에 바로 선다."""
    library = [SUPPORT, PIN, MOUNTED]
    opts = JigOptions(kind="clamped", support_height=lift)
    made = pipeline.analyze(PLATE, opts, library=library)
    plan = made.plan
    assert plan.clamps and all(one.standard is not None for one in plan.clamps)
    taps: set[tuple[float, float, float]] = set()
    for one in plan.clamps:
        assert one.riser == riser and one.mount_thread == "M5"
        # 판 위 자리를 베이스 자리 · 방향으로 되돌리면 사양의 클램프 좌표다.
        bx, by, _ = one.post_position
        c, s = math.cos(math.radians(one.angle)), math.sin(math.radians(one.angle))
        local = {
            (round(c * (x - bx) + s * (y - by), 2), round(-s * (x - bx) + c * (y - by), 2))
            for x, y in one.mount_holes
        }
        assert local == {(-15, -10), (-15, 10), (15, -10), (15, 10)}
        taps |= {(x, y, 5.0) for x, y in one.mount_holes}
    assert taps <= set(plan.base_plate.holes)  # 탭 구멍 — 호칭 지름(볼트 고정과 같다)
    assert not any("고정 나사 자리가 없어" in note for note in plan.notes)
    assert made.interference.ok, [one for one in made.interference.items if not one.ok]

    screws = next(row for row in plan.summary()["bom"] if row["kind"] == "screw")
    assert screws["part_no"] == "ISO 4762 M5" and screws["count"] == 4 * len(plan.clamps)

    recipe = _same_shape(made, opts, library)  # 블록의 여유 구멍까지 같은 형상
    drilled = next(
        (one for one in recipe["nodes"] if one["id"] == "클램프_1_받침블록_구멍"), None
    )
    if riser:
        assert drilled is not None and drilled["thread"] == "M5"
    else:
        assert drilled is None
