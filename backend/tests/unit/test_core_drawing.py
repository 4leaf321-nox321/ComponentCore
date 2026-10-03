"""도면 — 3각법 세 뷰 · 전체 치수 · 구멍표 · 표제란. 치수 글씨는 축척과 무관하게 실제
크기다."""

from __future__ import annotations

import io

import pytest
from build123d import Align, Axis, Box, Cylinder, Pos, Rot, fillet

from app.core import drawing


def _plate() -> object:
    """80 x 50 x 12 판 — 관통 넷 · 카운터보어 하나 · 옆에서 막힌 구멍 하나, 모서리 필렛."""
    part = Box(80, 50, 12, align=(Align.MIN, Align.MIN, Align.MIN))
    for x, y in ((10, 10), (70, 10), (70, 40), (10, 40)):
        part -= Pos(x, y, 0) * Cylinder(3.3, 40)
    part -= Pos(40, 25, 12) * Cylinder(5.5, 6.4, align=(Align.CENTER, Align.CENTER, Align.MAX))
    part -= Pos(40, 25, 0) * Cylinder(3.3, 40)
    part -= (
        Pos(40, 0, 6)
        * Rot(90, 0, 0)
        * Cylinder(2.5, 16, align=(Align.CENTER, Align.CENTER, Align.MAX))
    )
    return fillet(part.edges().filter_by(Axis.Z), 4)


def test_구멍은_관통_막힘_자리파기를_가르고_보스_필렛은_구멍이_아니다() -> None:
    found = drawing.holes(_plate())
    specs = sorted((one["diameter"], one["depth"]) for one in found)
    assert specs == [
        (5.0, 16.0),
        (6.6, None),
        (6.6, None),
        (6.6, None),
        (6.6, None),
        (6.6, None),
        (11.0, 6.4),
    ]
    # 기둥(보스)은 볼록하고, 주머니 안 모서리 필렛은 오목해도 한 바퀴가 아니다.
    boss = Box(40, 40, 5) + Pos(0, 0, 5) * Cylinder(6, 10)
    assert drawing.holes(boss) == []
    pocket = Box(40, 40, 20) - Pos(0, 0, 5) * Box(30, 30, 20)
    corners = pocket.edges().filter_by(Axis.Z).filter_by_position(Axis.Z, 0, 20)
    inner = [one for one in corners if abs(one.center().X) < 16]
    rounded = fillet(inner, 3)
    assert drawing.holes(rounded) == []


def test_도면_한_장_축척_치수_구멍표() -> None:
    sheet = drawing.make_sheet(_plate(), title="시험 판", material="AL6061")
    assert sheet.scale_text == "2:1"
    dims = sorted(one.value for one in sheet.items if isinstance(one, drawing.Dim))
    assert dims == pytest.approx([12, 50, 80])
    table = {one["label"]: one for one in sheet.holes}
    assert table["A1"] == {
        "label": "A1",
        "spec": "Ø6.6 관통",
        "view": "평면도",
        "x": 10.0,
        "y": 40.0,
    }
    assert table["B1"]["spec"] == "Ø6.6 관통 / 자리파기 Ø11 깊이 6.4"
    assert table["C1"]["view"] == "정면도" and table["C1"]["spec"] == "Ø5 깊이 16"
    assert "축척 2:1" in sheet.notes[0]

    # 큰 것은 줄여 그린다 — 표준 축척으로.
    big = drawing.make_sheet(Box(1200, 600, 300))
    assert big.scale_text in ("1:5", "1:10")


def test_DXF_는_진짜_치수_객체이고_글씨는_실제_크기다() -> None:
    from ezdxf.entities import Dimension
    from ezdxf.filemanagement import read

    sheet = drawing.make_sheet(_plate(), title="판")
    doc = read(io.StringIO(drawing.write_dxf(sheet)))
    msp = doc.modelspace()
    dims = [one for one in msp if isinstance(one, Dimension)]
    assert len(dims) == 3
    shown = set()
    for dim in dims:
        block = dim.get_geometry_block()
        assert block is not None
        shown |= {one.plain_text() for one in block if one.dxftype() == "MTEXT"}
    assert {"80", "50", "12"} <= shown  # 2:1 로 그렸지만 글씨는 실제 크기
    layers = {one.dxf.layer for one in msp}
    assert {"VISIBLE", "HIDDEN", "CENTER", "BORDER", "TABLE"} <= layers
    texts = [one.dxf.text for one in msp if one.dxftype() == "TEXT"]
    assert "판" in texts and "A1" in texts


def test_SVG_PDF_PNG() -> None:
    sheet = drawing.make_sheet(_plate(), title="판", sheet="A4")
    svg = drawing.write_svg(sheet)
    assert svg.startswith("<svg") and 'width="297mm"' in svg and ">80<" in svg
    assert drawing.write_pdf(sheet).startswith(b"%PDF")
    assert drawing.write_png(sheet, width=400).startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="용지"):
        drawing.make_sheet(Box(1, 1, 1), sheet="A0")
