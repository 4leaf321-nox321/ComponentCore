"""변수 → 형상 위의 치수 — 값을 조금 바꿔 한 번 더 만들고 견준다(`core/param_dims`)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.core import param_dims
from app.core.recipe import evaluate, parse
from app.core.recipe.mesh import mesh


def _build(raw: dict[str, Any]) -> Any:
    return evaluate(parse(raw)).shape


def _plate(**params: Any) -> dict[str, Any]:
    """왼쪽 끝(x=0)이 고정된 판 — 구멍은 오른쪽 끝에서 `여유` 안쪽, 지름은 변수."""
    return {
        "params": {
            "판_길이": 120,
            "폭": 50,
            "두께": 10,
            "구멍_지름": 6,
            "여유": 15,
            "마찰계수": 0.2,
            **params,
        },
        "nodes": [
            {
                "id": "p",
                "op": "box",
                "length": "=판_길이",
                "width": "=폭",
                "height": "=두께",
                "align": ["min", "center", "min"],
            },
            {
                "id": "h",
                "op": "hole",
                "target": "p",
                "at": [["=판_길이 - 여유", 0]],
                "diameter": "=구멍_지름",
            },
        ],
    }


def _by_name(found: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {one["name"]: one for one in found["dims"]}


def _length(one: dict[str, Any]) -> float:
    return math.dist(one["from"], one["to"])


def test_변수마다_그_값의_치수를_형상에서_찾는다() -> None:
    raw = _plate()
    dims = _by_name(param_dims.find(raw, None, _build))
    assert dims["판_길이"]["status"] == "dimension" and dims["판_길이"]["kind"] == "distance"
    assert dims["폭"]["kind"] == "distance" and dims["두께"]["kind"] == "distance"
    assert dims["구멍_지름"]["kind"] == "diameter"
    # 구멍은 오른쪽 끝면에서 축까지 — 식(`=판_길이 - 여유`)으로 정해도 형상만 본다.
    assert dims["여유"]["kind"] == "axis_plane"
    # 치수선의 길이가 곧 그 값이다.
    for name, value in (
        ("판_길이", 120),
        ("폭", 50),
        ("두께", 10),
        ("구멍_지름", 6),
        ("여유", 15),
    ):
        assert _length(dims[name]) == pytest.approx(value, abs=1e-3), name
        assert dims[name]["value"] == value


def test_형상에_안_쓰는_변수는_그렇다고_말한다() -> None:
    dims = _by_name(param_dims.find(_plate(), ["마찰계수"], _build))
    assert dims["마찰계수"]["status"] == "unused"
    assert dims["마찰계수"]["faces"] == [] and dims["마찰계수"]["from"] is None


def test_칠할_면은_메시의_면_번호다() -> None:
    """화면은 이 번호로 `/recipe/mesh` 의 면을 칠한다 — 순서가 어긋나면 엉뚱한 면이
    칠해진다."""
    raw = _plate()
    shape = _build(raw)
    faces = mesh(shape)["faces"]
    found = param_dims.find(raw, ["두께", "구멍_지름"], _build, base=shape)
    assert found["face_count"] == len(faces)
    dims = _by_name(found)
    # 두께는 윗면 · 아랫면(z=10 · z=0), 지름은 원통 면.
    assert sorted(faces[i]["center"][2] for i in dims["두께"]["faces"]) == [0.0, 10.0]
    assert {faces[i]["kind"] for i in dims["구멍_지름"]["faces"]} == {"cylinder"}


def test_값과_같은_치수가_없으면_움직이는_면을_알린다() -> None:
    """비율은 길이가 아니다 — 그래도 어느 면을 움직이는지는 보인다."""
    raw = {
        "params": {"두께": 4, "간격비": 2},
        "nodes": [
            {"id": "b", "op": "box", "length": 80, "width": 20, "height": "=두께"},
            {
                "id": "c",
                "op": "cylinder",
                "radius": 3,
                "height": 20,
                "at": ["=간격비 * 두께 * 2", 0, 2],
                "axis": "Y",
            },
            {"id": "u", "op": "union", "targets": ["b", "c"]},
        ],
    }
    dims = _by_name(param_dims.find(raw, ["간격비"], _build))
    assert dims["간격비"]["status"] == "moved"
    assert dims["간격비"]["faces"], "움직인 면이 있어야 칠한다"
    assert dims["간격비"]["at"] is not None and dims["간격비"]["message"]


def test_같은_값의_다른_치수에_걸리지_않는다() -> None:
    """폭과 길이가 둘 다 50 이어도, 폭을 바꾸면 폭만 따라 변한다."""
    raw = {
        "params": {"길이": 50, "폭": 50},
        "nodes": [{"id": "b", "op": "box", "length": "=길이", "width": "=폭", "height": 5}],
    }
    dims = _by_name(param_dims.find(raw, None, _build))
    길이, 폭 = dims["길이"], dims["폭"]
    # 길이는 X 방향, 폭은 Y 방향의 치수선이다.
    assert abs(길이["to"][0] - 길이["from"][0]) == pytest.approx(50)
    assert abs(폭["to"][1] - 폭["from"][1]) == pytest.approx(50)


def test_시간이_넘으면_남은_변수는_건너뛴다() -> None:
    ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    found = param_dims.find(
        _plate(), ["두께", "폭"], _build, budget=10, clock=lambda: next(ticks)
    )
    dims = _by_name(found)
    assert dims["두께"]["status"] == "dimension"
    assert dims["폭"]["status"] == "skipped"


def test_없는_변수와_못_만드는_변형은_실패로_말한다() -> None:
    raw = _plate()

    def picky(one: dict[str, Any]) -> Any:
        # 두께만 바꾸면 깨지는 도면 — 지금 형상은 만들어진다.
        if one["params"]["두께"] != 10:
            raise ValueError("깨짐")
        return _build(one)

    dims = _by_name(param_dims.find(raw, ["두께", "없는것"], picky))
    assert dims["두께"]["status"] == "failed"
    assert dims["없는것"]["status"] == "failed" and "없는 변수" in dims["없는것"]["message"]
