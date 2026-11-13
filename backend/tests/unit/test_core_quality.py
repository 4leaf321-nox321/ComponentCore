"""형상 점검 — 해석이 메시를 못 만들 점(얇은 벽 · 짧은 모서리 · 좁은 면)을 보내기 전에."""

from __future__ import annotations

import pytest
from build123d import Box, Cylinder, Part, Pos

from app.core.quality import DEFAULTS, QualityError, compare, inspect, thresholds


def test_구멍이_가장자리에_붙으면_얇은_벽을_그_자리와_함께_잡는다() -> None:
    # 기준은 핸드폰 부품 규모(0.1 mm) — 0.05 mm 벽이 걸린다.
    thin = Box(50, 50, 10) - Pos(20, 0, 0) * Cylinder(4.95, 20)
    found = inspect(thin)
    assert found["valid"] and found["solids"] == 1
    assert found["min_wall"] == pytest.approx(0.05, abs=1e-3)
    assert found["min_wall_at"][0] == pytest.approx(25.0)
    assert any(one.startswith("벽 두께 0.05 mm (기준 0.1)") for one in found["warnings"])
    # 0.2 mm 벽은 핸드폰 부품에서 흔하다 — 경고하지 않는다(예전 기준 0.5 에서는 걸렸다).
    usual = Box(50, 50, 10) - Pos(20, 0, 0) * Cylinder(4.8, 20)
    assert not any(one.startswith("벽 두께") for one in inspect(usual)["warnings"])

    fine = Box(50, 50, 10) - Cylinder(4, 20)
    assert inspect(fine)["warnings"] == [] and inspect(fine)["min_wall"] == pytest.approx(10)


def test_짧은_모서리와_좁은_면을_센다() -> None:
    # 위에 0.005 mm 두께 판을 조금 작게 얹으면 턱마다 아주 좁은 띠 면과 짧은 모서리가 생긴다.
    stepped = Box(40, 20, 10) + Pos(0, 0, 5.0025) * Box(40, 19.9, 0.005)
    found = inspect(stepped)
    assert found["short_edges"] > 0 and found["shortest_edge"] == pytest.approx(
        0.005, abs=1e-4
    )
    assert found["narrow_faces"] > 0
    assert any("짧은 모서리" in one for one in found["warnings"])
    assert any("좁은 면" in one for one in found["warnings"])
    # 기준을 낮추면 통과한다.
    relaxed = inspect(stepped, thresholds({"short_edge": 0.001, "narrow_face": 0.001}))
    assert not any("짧은" in one or "좁은" in one for one in relaxed["warnings"])


def test_기준은_준_것만_바꾸고_틀리면_말한다() -> None:
    assert thresholds(None) == {"enabled": True, **DEFAULTS}
    assert thresholds({"min_wall": 1})["min_wall"] == 1.0
    assert thresholds({"enabled": False})["enabled"] is False
    with pytest.raises(QualityError, match="알 수 없는 점검 기준"):
        thresholds({"wall": 1})
    with pytest.raises(QualityError, match="0 이상"):
        thresholds({"min_wall": -1})


def test_기준_형상과_견줘_바디가_쪼개지면_경고_면_수는_알림() -> None:
    base = {"solids": 1, "faces": 6, "warnings": []}
    split = compare({"solids": 2, "faces": 12, "warnings": []}, base)
    assert split["warnings"] == ["바디 수가 기준과 다릅니다(1 → 2)."]
    assert split["notes"] == ["면 수 6 → 12"]
    assert compare({"solids": 1, "faces": 6, "warnings": []}, None)["notes"] == []


def _two(dz: float) -> Part:
    """큰 판(z 0..20) 위에 작은 블록 — `dz` 만큼 띄우거나(틈) 박는다(겹침)."""

    base = Box(100, 100, 20).moved(Pos(0, 0, 10))
    base.label = "Base"
    block = Box(20, 20, 20).moved(Pos(0, 0, 30 + dz))
    block.label = "Block"
    return Part(children=[base, block])


def test_바디끼리_얇은_겹침과_작은_틈을_그_자리와_함께_잡는다() -> None:
    # 꼭 맞닿은 것은 적지 않는다 — 받는 쪽이 쪼개 절점을 공유하는 정상이다.
    assert inspect(_two(0.0))["contacts"] == []

    # 0.01 mm 겹침 — 받는 쪽 쪼개기가 두께 0.01 조각을 따로 만들던 꼴(gmsh 4.12 실측).
    found = inspect(_two(-0.01))
    (one,) = found["contacts"]
    assert one["kind"] == "overlap" and (one["a"], one["b"]) == ("Base", "Block")
    assert one["size"] == pytest.approx(0.01, abs=1e-4)
    assert one["volume"] == pytest.approx(4.0, abs=1e-3)
    assert one["at"] == pytest.approx([0, 0, 19.995], abs=1e-3)
    assert any("바디 겹침 ‘Base’ · ‘Block’" in line for line in found["warnings"])

    # 0.0005 mm 틈 — CAD 가 남긴 틈(기본 기준 0.001 mm 안). 절점을 하나도 공유하지 않던 꼴.
    # 자리는 마주 본 면의 가운데다.
    found = inspect(_two(0.0005))
    (one,) = found["contacts"]
    assert one["kind"] == "gap" and one["size"] == pytest.approx(0.0005, abs=1e-6)
    assert one["at"] == pytest.approx([0, 0, 20.00025], abs=1e-3)
    assert any("바디 사이 틈" in line for line in found["warnings"])

    # 기준보다 먼 틈은 설계한 틈새로 본다(핸드폰 부품의 0.05~0.2 mm) — 기준을 올리면 잡는다.
    assert inspect(_two(0.005))["contacts"] == []
    (wide,) = inspect(_two(0.005), thresholds({"contact_gap": 0.01}))["contacts"]
    assert wide["size"] == pytest.approx(0.005, abs=1e-5)
    # 0 이면 틈은 안 본다.
    assert inspect(_two(0.0005), thresholds({"contact_gap": 0}))["contacts"] == []
