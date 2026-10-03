"""형상 점검 — 해석이 메시를 못 만들 점(얇은 벽 · 짧은 모서리 · 좁은 면)을 보내기 전에."""

from __future__ import annotations

import pytest
from build123d import Box, Cylinder, Pos

from app.core.quality import DEFAULTS, QualityError, compare, inspect, thresholds


def test_구멍이_가장자리에_붙으면_얇은_벽을_그_자리와_함께_잡는다() -> None:
    thin = Box(50, 50, 10) - Pos(20, 0, 0) * Cylinder(4.8, 20)
    found = inspect(thin)
    assert found["valid"] and found["solids"] == 1
    assert found["min_wall"] == pytest.approx(0.2, abs=1e-3)
    assert found["min_wall_at"][0] == pytest.approx(25.0)
    assert any(one.startswith("벽 두께 0.2 mm (기준 0.5)") for one in found["warnings"])

    fine = Box(50, 50, 10) - Cylinder(4, 20)
    assert inspect(fine)["warnings"] == [] and inspect(fine)["min_wall"] == pytest.approx(10)


def test_짧은_모서리와_좁은_면을_센다() -> None:
    # 위에 0.05 mm 두께 판을 조금 작게 얹으면 턱마다 아주 좁은 띠 면과 짧은 모서리가 생긴다.
    stepped = Box(40, 20, 10) + Pos(0, 0, 5.025) * Box(40, 19.9, 0.05)
    found = inspect(stepped)
    assert found["short_edges"] > 0 and found["shortest_edge"] == pytest.approx(0.05, abs=1e-3)
    assert found["narrow_faces"] > 0
    assert any("짧은 모서리" in one for one in found["warnings"])
    assert any("좁은 면" in one for one in found["warnings"])
    # 기준을 낮추면 통과한다.
    relaxed = inspect(stepped, thresholds({"short_edge": 0.01, "narrow_face": 0.01}))
    assert not any("짧은" in one or "좁은" in one for one in relaxed["warnings"])


def test_기준은_준_것만_바꾸고_틀리면_말한다() -> None:
    assert thresholds(None) == {"enabled": True, **DEFAULTS}
    assert thresholds({"min_wall": 1})["min_wall"] == 1.0
    assert thresholds({"enabled": False})["enabled"] is False
    with pytest.raises(QualityError, match="모르는"):
        thresholds({"wall": 1})
    with pytest.raises(QualityError, match="0 이상"):
        thresholds({"min_wall": -1})


def test_기준_형상과_견줘_바디가_쪼개지면_경고_면_수는_알림() -> None:
    base = {"solids": 1, "faces": 6, "warnings": []}
    split = compare({"solids": 2, "faces": 12, "warnings": []}, base)
    assert split["warnings"] == ["바디 수가 기준과 다릅니다 (1 → 2)"]
    assert split["notes"] == ["면 수 6 → 12"]
    assert compare({"solids": 1, "faces": 6, "warnings": []}, None)["notes"] == []
