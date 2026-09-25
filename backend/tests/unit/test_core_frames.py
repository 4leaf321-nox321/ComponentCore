"""좌표계 — 조건의 `cs` 가 가리킨다. 계산은 서버 한 곳(`core/frames.py`)."""

from __future__ import annotations

import pytest

from app.core import conditions, frames
from app.core.recipe import evaluate, parse
from app.core.recipe.schema import RecipeValidationError

BOX = {"id": "b", "op": "box", "length": "=길이", "width": 50, "height": 10}


def test_회전은_X_Y_Z_순서로_돌린다() -> None:
    row = frames.from_rotation("옆", "cad", [1, 2, 3], [0, 0, 90])
    assert row["origin"] == [1.0, 2.0, 3.0]
    assert (
        row["x"] == [0.0, 1.0, 0.0]
        and row["y"] == [-1.0, 0.0, 0.0]
        and row["z"] == [0.0, 0.0, 1.0]
    )


def test_X_Y_방향으로_정하면_Y_는_X_에_수직으로_맞추고_Z_는_외적이다() -> None:
    row = frames.from_vectors("비스듬", "cad", [0, 0, 0], [0, 2, 0], [-1, 1, 0])
    assert row["x"] == [0.0, 1.0, 0.0]
    assert row["y"] == [-1.0, 0.0, 0.0] and row["z"] == [0.0, 0.0, 1.0]
    with pytest.raises(ValueError, match="나란합니다"):
        frames.from_vectors("나란", "cad", [0, 0, 0], [1, 0, 0], [3, 0, 0])


def test_정의는_벡터_회전_둘_다_읽고_벡터가_먼저다() -> None:
    by_vectors = frames.from_definition(
        "a", "cad", {"x_axis": [0, 1, 0], "y_axis": [-1, 0, 0]}
    )
    by_rotation = frames.from_definition("a", "cad", {"rotate": [0, 0, 90]})
    assert by_vectors == by_rotation
    both = frames.from_definition(
        "a", "cad", {"x_axis": [1, 0, 0], "y_axis": [0, 1, 0], "rotate": [0, 0, 90]}
    )
    assert both["x"] == [1.0, 0.0, 0.0]
    assert frames.from_definition("a", "cad", {})["z"] == [0.0, 0.0, 1.0]


def test_면에_붙이면_Z_가_법선이고_X_는_늘_같은_규칙으로_정한다() -> None:
    위 = frames.from_face("윗면", "conditions", [0, 0, 10], [0, 0, 1])
    assert 위["z"] == [0.0, 0.0, 1.0] and 위["x"] == [1.0, 0.0, 0.0]
    # 법선이 전역 X 와 나란하면 X 를 눕힐 수 없다 — 전역 Y 를 쓴다.
    옆 = frames.from_face("옆면", "conditions", [40, 0, 5], [1, 0, 0])
    assert (
        옆["z"] == [1.0, 0.0, 0.0]
        and 옆["x"] == [0.0, 1.0, 0.0]
        and 옆["y"] == [0.0, 0.0, 1.0]
    )


def test_도면의_좌표계는_치수_식을_따라간다() -> None:
    recipe = {
        "params": {"길이": 80},
        "nodes": [BOX],
        "coordinate_systems": [
            {"name": "끝", "origin": ["=길이/2", 0, 5], "rotate": [0, 90, 0]}
        ],
    }
    for 길이 in (80, 130):
        made = evaluate(parse({**recipe, "params": {"길이": 길이}}))
        assert made.frames[0]["name"] == "끝" and made.frames[0]["origin"] == [
            길이 / 2,
            0.0,
            5.0,
        ]
        assert made.frames[0]["z"] == [1.0, 0.0, 0.0]


def test_도면의_좌표계는_방향_벡터로도_정하고_나란하면_알린다() -> None:
    def frame(x_axis: list[object], y_axis: list[object]) -> dict[str, object]:
        return {"name": "끝", "origin": [0, 0, 0], "x_axis": x_axis, "y_axis": y_axis}

    made = evaluate(
        parse(
            {
                "params": {"길이": 80},
                "nodes": [BOX],
                "coordinate_systems": [frame([0, 0, 1], ["=길이", 0, 0])],
            }
        )
    )
    assert made.frames[0]["x"] == [0.0, 0.0, 1.0] and made.frames[0]["z"] == [0.0, 1.0, 0.0]
    with pytest.raises(ValueError, match="나란합니다"):
        evaluate(
            parse(
                {
                    "params": {"길이": 80},
                    "nodes": [BOX],
                    "coordinate_systems": [frame([1, 0, 0], ["=길이", 0, 0])],
                }
            )
        )


def test_도면의_좌표계_이름은_겹치거나_전역이면_안_된다() -> None:
    for bad in ([{"name": "global"}], [{"name": "a"}, {"name": "a"}]):
        with pytest.raises(RecipeValidationError):
            parse({"params": {"길이": 80}, "nodes": [BOX], "coordinate_systems": bad})


def test_조건의_cs_는_있는_좌표계를_가리켜야_한다() -> None:
    raw = {
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "constraints": [
            {"name": "고정", "type": "displacement", "on": "바닥", "cs": "끝", "x": 0}
        ],
    }
    # 도면에 「끝」 이 있으면 된다.
    conditions.parse(raw, frames=["끝"])
    with pytest.raises(conditions.ConditionError, match="「끝」 라는 좌표계가 없습니다"):
        conditions.parse(raw, frames=[])
    # 조건에서 정한 좌표계도 된다 — 선택 그룹의 면에 붙인 것.
    conditions.parse({**raw, "coordinate_systems": [{"name": "끝", "on": "바닥"}]}, frames=[])
    # 없는 그룹에 붙이거나, 도면의 이름과 겹치면 막는다.
    with pytest.raises(conditions.ConditionError, match="선택 그룹이 없습니다"):
        conditions.parse(
            {**raw, "coordinate_systems": [{"name": "끝", "on": "없는것"}]}, frames=[]
        )
    with pytest.raises(conditions.ConditionError, match="겹칩니다"):
        conditions.parse({**raw, "coordinate_systems": [{"name": "끝"}]}, frames=["끝"])


def test_면에_붙인_좌표계는_그룹을_못_풀면_못_푼_것이다() -> None:
    rows, missing = frames.condition_frames(
        [
            {"name": "바닥 좌표", "on": "바닥"},
            {"name": "수치", "origin": [1, 0, 0], "rotate": [0, 0, 0]},
            {"name": "벡터", "x_axis": [0, 1, 0], "y_axis": [0, 0, 1]},
            {"name": "나란", "x_axis": [0, 1, 0], "y_axis": [0, 2, 0]},
        ],
        {},
    )
    assert missing == ["바닥 좌표", "나란"]
    assert [one["name"] for one in rows] == ["수치", "벡터"]
