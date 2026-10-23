"""전역 요소 크기 제안 — 사람이 메시를 안 정했을 때 해석 쪽이 쓸 값(2026-10-23).

규칙은 셋(벽의 절반 · 가장 긴 변의 1/20 위 한도 · 1/200 아래 한도)이고 깔끔한 수로
내린다 — 받는 쪽이 숫자를 보고 「왜 이 값인가」 를 되짚을 수 있어야 한다(`basis`).
"""

from __future__ import annotations

import pytest

from app.core import conditions as model
from app.core.mesh_suggestion import nice_floor, suggest


def _box(x: float, y: float, z: float, at: float = 0.0) -> dict[str, object]:
    return {"bbox": [[at, 0.0, 0.0], [at + x, y, z]]}


def test_벽이_정하면_가장_얇은_벽에_요소_두_개() -> None:
    got = suggest([_box(40, 30, 2)], {"min_wall": 2.0}, in_conditions=False)
    assert got is not None
    assert got["element_size"] == 1.0  # 2/2 — 위 한도 2(40/20), 아래 0.2
    assert "최소 벽 두께(2 mm)의 절반" in got["basis"]
    # 파트별 벽이 없는 옛 점검이면 전체의 값을 쓴다(어느 파트인지는 모른다).
    assert got["inputs"] == {
        "min_wall": 2.0,
        "wall_body": None,
        "longest": 40.0,
        "skipped": [],
    }
    assert got["in_conditions"] is False and got["rule"]


def test_두꺼운_벽은_위_한도_얇은_벽은_아래_한도() -> None:
    thick = suggest([_box(100, 20, 50)], {"min_wall": 50.0}, in_conditions=False)
    assert thick is not None and thick["element_size"] == 5.0  # 25 → 100/20
    assert "1/20" in thick["basis"]
    thin = suggest([_box(1000, 50, 50)], {"min_wall": 0.2}, in_conditions=True)
    assert thin is not None and thin["element_size"] == 5.0  # 0.1 → 1000/200
    assert "1/200" in thin["basis"] and "국부 메시" in thin["basis"]
    assert thin["in_conditions"] is True


def test_벽을_모르면_가장_긴_변의_스무분의_일() -> None:
    """시트만 있는 셸 모델은 벽 두께가 없다(형상 점검의 `min_wall` 이 None)."""
    sheet = suggest([_box(100, 20, 0)], {"min_wall": None}, in_conditions=False)
    assert sheet is not None and sheet["element_size"] == 5.0
    assert "벽 두께를 모른다" in sheet["basis"]
    off = suggest([_box(100, 20, 10)], None, in_conditions=False)  # 형상 점검을 껐다
    assert off is not None and off["element_size"] == 5.0


def test_여러_바디는_합친_상자로_잰다() -> None:
    """받침(0~20) 과 시트(0~100)를 합치면 가장 긴 변은 100 이다."""
    got = suggest(
        [_box(20, 20, 10), _box(100, 20, 0)], {"min_wall": 10.0}, in_conditions=False
    )
    assert got is not None
    # 10/2 = 5 = 100/20
    assert got["inputs"]["longest"] == 100.0 and got["element_size"] == 5.0
    assert suggest([], {"min_wall": 1.0}, in_conditions=False) is None
    assert suggest([{"name": "전체"}], {"min_wall": 1.0}, in_conditions=False) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2.7, 2.5),
        (0.37, 0.3),
        (12.0, 12.0),
        (0.0123, 0.012),
        (7.9, 6.0),
        (1.0, 1.0),
        (99.0, 80.0),
    ],
)
def test_깔끔한_수로_내린다(value: float, expected: float) -> None:
    assert nice_floor(value) == pytest.approx(expected)


def test_사람이_전역_크기를_적었나() -> None:
    assert model.has_global_mesh({"mesh_hints": [{"on": "전체", "element_size": 3}]})
    # on 의 기본이 「전체」
    assert model.has_global_mesh({"mesh_hints": [{"element_size": 3}]})
    assert model.has_global_mesh({"mesh_hints": [{"on": "전체", "element_size": "=t"}]})
    assert not model.has_global_mesh({"mesh_hints": [{"on": "구멍면", "element_size": 1}]})
    assert not model.has_global_mesh({"mesh_hints": [{"on": "전체", "method": "automatic"}]})
    assert not model.has_global_mesh({})
    assert not model.has_global_mesh(None)


def test_해석_제외_쉘_강체의_벽은_빼고_본다() -> None:
    """해석에서 뺀 1 mm 명판이 80 mm 모델을 0.5 mm 로 제안했다(강체 지그 · 쉘 브래킷 픽스처,
    2026-10-23) — 솔리드로 푸는 파트의 벽만 본다."""
    bodies = [
        {"name": "블록", **_box(80, 40, 20)},
        {"name": "명판", **_box(30, 1, 10)},
    ]
    quality = {"min_wall": 1.0, "min_wall_by_body": {"블록": 5.0, "명판": 1.0}}
    got = suggest(bodies, quality, in_conditions=False, skip_wall=frozenset({"명판"}))
    assert got is not None
    assert got["element_size"] == 2.5  # 블록의 벽 5 의 절반(80/20 = 4 보다 작다)
    assert "「블록」" in got["basis"]
    assert got["inputs"]["wall_body"] == "블록" and got["inputs"]["skipped"] == ["명판"]
    # 안 빼면 명판이 정한다 — 1/200(0.4) 보다 큰 0.5.
    plain = suggest(bodies, quality, in_conditions=False)
    assert plain is not None and plain["element_size"] == 0.5


def test_솔리드로_푸는_파트가_없으면_크기로() -> None:
    bodies = [{"name": "브래킷", **_box(60, 30, 50)}]
    quality = {"min_wall": 2.0, "min_wall_by_body": {"브래킷": 2.0}}
    got = suggest(bodies, quality, in_conditions=False, skip_wall=frozenset({"브래킷"}))
    assert got is not None and got["element_size"] == 3.0  # 60/20
    assert "솔리드로 푸는 파트의 벽이 없다" in got["basis"]


def test_해석_제외한_파트는_크기에서도_뺀다() -> None:
    bodies = [{"name": "판", **_box(40, 30, 4)}, {"name": "긴 띠", **_box(400, 5, 5, at=40)}]
    quality = {"min_wall_by_body": {"판": 4.0, "긴 띠": 5.0}}
    got = suggest(
        bodies,
        quality,
        in_conditions=False,
        skip_wall=frozenset({"긴 띠"}),
        skip_size=frozenset({"긴 띠"}),
    )
    assert got is not None
    assert got["inputs"]["longest"] == 40.0 and got["element_size"] == 2.0


def test_뺄_파트는_파트별_설정에서_읽는다() -> None:
    raw = {
        "body_settings": [
            {"name": "명판", "suppressed": True},
            {"name": "브래킷", "representation": "shell"},
            {"name": "지그블록", "behavior": "rigid"},
            {"name": "블록", "mesh": {"element_size": 4}},
        ]
    }
    wall, size = model.mesh_skips(raw)
    assert wall == {"명판", "브래킷", "지그블록"} and size == {"명판"}
    assert model.mesh_skips(None) == (frozenset(), frozenset())


def test_형상_점검은_파트별_벽을_파트_목록과_같은_이름으로_적는다() -> None:
    import copy

    from build123d import Box, Compound, Pos

    from app.core import quality
    from app.core.recipe import topology

    block = copy.copy(Box(80, 40, 20))
    block.label = "블록"
    plate = Pos(0, 30, 0) * Box(30, 1, 10)
    plate.label = "명판"
    shape = Compound(children=[block, plate])
    found = quality.inspect(shape)
    walls = found["min_wall_by_body"]
    assert set(walls) == {row["name"] for row in topology.bodies(shape)} == {"블록", "명판"}
    assert walls["명판"] == pytest.approx(1.0, abs=0.01)
    assert walls["블록"] == pytest.approx(20.0, abs=0.01)
    assert found["min_wall"] == pytest.approx(1.0, abs=0.01)
