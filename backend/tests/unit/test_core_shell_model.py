"""셸 모델 — **시트 바디(두께 없는 면) STEP 을 해석용으로 받는다**(2026-10-15).

예전에는 솔리드가 없는 STEP 을 가져오기에서 거절했다(「STEP 파일에 솔리드가 없습니다」). 해석용
셸 모델은 형상이 이미 중간면이고 두께는 사람이 정한다 — 그 둘을 받는 길이 여기서 서나:
가져오기 → 셸 모델 → 파트 목록(`kind="sheet"`) → 중간면(형상 그대로 · 두께는 조건) → 영역(같은
면 그대로).
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from build123d import Box, Compound, Face, Vector

from app.core import export, views
from app.core.recipe import RecipeError, evaluate, parse, topology
from app.core.recipe.midsurface import MidSurfaceError, attach, midsurface


def _sheet() -> Face:
    """굽은 판 하나 — B-스플라인 곡면, 40 x 30 mm."""
    points = [
        [Vector(x, y, 3.0 * ((x - 20) / 20) ** 2) for x in (0, 10, 20, 30, 40)]
        for y in (0, 10, 20, 30)
    ]
    return Face.make_surface_from_array_of_points(points)


def _imported(path: Path) -> object:
    recipe = parse({"nodes": [{"id": "s", "op": "import_step", "file": path.name}]})
    return evaluate(recipe, resolve_file=lambda key: path.parent / key)


def test_시트만_든_STEP_이_셸_모델이_된다(tmp_path: Path) -> None:
    path = export.write_step(_sheet(), tmp_path / "sheet.step")
    made = _imported(path)
    assert made.is_shell  # type: ignore[attr-defined]
    summary = made.summary()  # type: ignore[attr-defined]
    assert summary["is_shell"] is True and summary["solid_count"] == 0
    assert summary["surface_area"] > 40 * 30  # 휘었으니 평면보다 넓다
    assert any("셸 모델" in one for one in summary["warnings"])

    # 저장 작업이 쓰는 셋 — STEP · glTF · 그림 — 이 다 나온다.
    shape = made.shape  # type: ignore[attr-defined]
    assert export.write_step(shape, tmp_path / "out.step").stat().st_size > 0
    assert export.write_gltf(shape, tmp_path / "out.glb").stat().st_size > 0
    assert views.views(shape, ("iso",), width=200)["iso"]["png_base64"]

    # 파트 목록 — 부피 0 이라 넓이와 종류로 짝짓는다.
    (body,) = topology.bodies(shape)
    assert body["kind"] == "sheet" and body["volume"] == 0 and body["area"] > 40 * 30


def test_솔리드도_면도_없는_STEP_은_거절한다(tmp_path: Path) -> None:
    from build123d import Edge

    path = tmp_path / "edge.step"
    from build123d import export_step

    export_step(Compound(children=[Edge.make_line((0, 0, 0), (10, 0, 0))]), str(path))
    with pytest.raises(RecipeError, match="솔리드도 면도"):
        _imported(path)


def test_시트의_중간면은_형상_그대로이고_두께는_조건이_준다(tmp_path: Path) -> None:
    path = export.write_step(_sheet(), tmp_path / "sheet.step")
    shape = _imported(path).shape  # type: ignore[attr-defined]

    surface = midsurface(shape, single_name="전체", thicknesses={"전체": 1.5})
    (body,) = surface.bodies
    assert body.thickness == 1.5 and body.area == pytest.approx(shape.area, rel=1e-6)
    assert surface.summary()["bodies"][0]["source"] == "sheet"

    # 두께가 없으면 — 잴 수 없으니 말한다(엄격하면 오류, 아니면 그 파트만 실패로).
    with pytest.raises(MidSurfaceError, match="두께가 없습니다"):
        midsurface(shape, single_name="전체")
    loose = midsurface(shape, strict=False, single_name="전체")
    assert loose.bodies == [] and loose.failed[0][0] == "전체"

    # 영역은 **같은 면 그대로** 중간면의 영역이 된다(겉면 → t/2 안쪽이 아니다).
    definitions = [{"name": "판", "select": {"what": "faces"}}]
    regions, unresolved = topology.regions(shape, definitions)
    assert not unresolved
    attach(regions, shape, surface, definitions)
    (print_,) = regions["판"]
    mid = print_["mid"]
    assert len(mid) == 1 and mid[0]["face"]["area"] == pytest.approx(shape.area, rel=1e-3)


def test_솔리드와_시트가_섞인_조립은_시트만_두께를_받는다() -> None:
    plate = copy.copy(Box(40, 30, 2))
    plate.label = "받침"
    skin = Compound(_sheet().wrapped)
    skin.label = "덮개"
    shape = Compound(children=[plate, skin])
    surface = midsurface(shape, [], strict=False, thicknesses={"덮개": 0.8})
    names = {one.name: one for one in surface.bodies}
    # 받침(솔리드)은 쉘로 고르지 않았으니 없고, 덮개(시트)는 늘 든다.
    assert set(names) == {"덮개"} and names["덮개"].thickness == 0.8
    assert {row["name"]: row["kind"] for row in topology.bodies(shape)} == {
        "받침": "solid",
        "덮개": "sheet",
    }


def test_시트_구성품의_무게중심은_넓이로_잰다() -> None:
    """조립에서 가져온 시트 구성품은 `Shell` 이고, build123d 의 `Shell.center()` 는 엣지 길이
    무게중심이다 — 넓이가 다른 두 면이면 어긋난다(2026-10-15, x 45.714 ↔ 50)."""
    from build123d import Shell, Wire

    def rect(x0: float, x1: float) -> Face:
        corners = [(x0, 0, 0), (x1, 0, 0), (x1, 20, 0), (x0, 20, 0)]
        return Face(Wire.make_polygon(corners, close=True))

    skin = Shell([rect(0, 20), rect(20, 100)])  # 400 mm² @ x 10 · 1600 mm² @ x 60
    skin.label = "skin"
    plate = copy.copy(Box(10, 10, 10))
    plate.label = "plate"
    rows = {row["name"]: row for row in topology.bodies(Compound(children=[plate, skin]))}
    assert rows["skin"]["centroid"] == [50.0, 10.0, 0.0]
    assert rows["plate"]["centroid"] == [0.0, 0.0, 0.0]


def test_파트_설정은_형상의_종류와_맞아야_한다() -> None:
    """시트는 변형체 쉘로만, 솔리드를 쉘로 풀 때 두께는 형상에서(2026-10-16, SimEngBay 의
    부탁). 받는 쪽은 시트가 솔리드 · 강체면 작업을 만들 때 막는다 — 그때는 이미 내보낸 뒤다.
    솔리드에 적은 두께는 쓰이지 않아 점 파일의 두 두께가 갈렸다."""
    from app.core import conditions as model

    bodies, sheets = ["덮개", "받침"], {"덮개"}

    def parse(*rows: dict[str, object]) -> object:
        return model.parse({"body_settings": list(rows)}, bodies, None, sheets)

    # 표현을 안 적은 시트 줄은 쉘이다 — 두께만 적어도 된다.
    got = parse({"name": "덮개", "thickness": 1.2})
    assert got.body_settings[0].representation == "shell"  # type: ignore[attr-defined]
    with pytest.raises(model.ConditionError, match="쉘로만 풀 수"):
        parse({"name": "덮개", "representation": "solid"})
    with pytest.raises(model.ConditionError, match="강체로 둘 수"):
        parse({"name": "덮개", "behavior": "rigid"})
    parse({"name": "덮개", "suppressed": True, "representation": "solid"})  # 제외면 상관없다
    with pytest.raises(model.ConditionError, match="형상에서 잽니다"):
        parse({"name": "받침", "representation": "shell", "thickness": 2})
    parse({"name": "받침", "representation": "shell"})
    # 형상을 모르는 자리(종류를 안 준다)는 예전 그대로 — 저장을 막지 않는다.
    model.parse(
        {"body_settings": [{"name": "받침", "representation": "shell", "thickness": 2}]}
    )


def test_내보내는_조건에서_시트는_늘_쉘이다() -> None:
    from app.core import conditions as model

    # 줄이 없으면 기본 줄을 쉘로 더한다(두께는 없다 — 중간면이 실패로 말한다).
    out = model.sheets_as_shell({"body_settings": [{"name": "받침"}]}, ["덮개"])
    names = [row["name"] for row in out["body_settings"]]
    assert names == ["받침", "덮개"]
    added = out["body_settings"][1]
    assert added["representation"] == "shell" and added["behavior"] == "deformable"
    assert added["thickness"] is None and added["suppressed"] is False
    # 해석 제외한 줄은 그대로, 시트가 없으면 아무것도 안 바꾼다.
    off = {"body_settings": [{"name": "덮개", "representation": "solid", "suppressed": True}]}
    assert model.sheets_as_shell(off, ["덮개"]) == off
    assert model.sheets_as_shell(off, []) is off


def test_SI_로_내보내면_쉘_두께도_계를_따른다() -> None:
    """점 파일의 조건은 선언한 계다 — 두께 칸만 mm 로 남아 있었다(옮기는 목록에서 빠졌다).
    중간면 요약의 두께는 계와 상관없이 mm 다(`length_units.midsurface`)."""
    from app.core import conditions as model

    raw = {
        "units": {"system": "si"},
        "body_settings": [
            {"name": "덮개", "representation": "shell", "thickness": 1.2,
             "mesh": {"element_size": 2}},
            {"name": "받침"},
        ],
    }  # fmt: skip
    shell, base = model.resolve(raw, {})["body_settings"]
    assert shell["thickness"] == pytest.approx(0.0012)
    assert shell["mesh"]["element_size"] == pytest.approx(0.002)
    assert base["thickness"] is None
