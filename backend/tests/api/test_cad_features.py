"""새 연산을 **섞은** 지그를 앱이 하는 그대로 — 검사 · 미리보기 · 저장(STEP) · 그림 · DOE 폴더.

기능마다의 시험(`tests/unit/test_core_*.py`)은 작은 상자로 본다. 섞으면 다른 것이 드러난다
(실측 2026-10-02): 핀 · 블록을 합친 큰 판의 면을 나누면 부피가 1조분의 5 달라져 「형상이
달라졌다」 고 거절했고, 형상에서 뽑은 기준면의 원점이 면의 무게중심이라 DOE 가 구멍을 옮기면
그 위의 스케치가 0.15 mm 밀렸다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

TOP = 220.0  # 판 아랫면 — 프레임 윗면(200 + 20)


def _recipe() -> dict[str, Any]:
    # 판 윗면의 높이는 식으로 — 위치로 고른 엣지가 두께를 훑어도 그 자리를 따라간다.
    top = f"={TOP} + 판_두께"
    return {
        "params": {"구멍_x": 0.0, "판_두께": 12.0},
        "nodes": [
            # 구조 프레임 — 각관 틀과 다리 넷(틀과 겹치지 않게 180 까지)
            {"id": "틀", "op": "frame", "profile": {"type": "square_tube", "width": 40,
             "thickness": 2}, "corner": "butt",
             "paths": [[[-200, -150, 200], [200, -150, 200], [200, 150, 200], [-200, 150, 200],
                        [-200, -150, 200]],
                       [[-200, -150, 0], [-200, -150, 180]],
                       [[200, -150, 0], [200, -150, 180]],
                       [[200, 150, 0], [200, 150, 180]], [[-200, 150, 0], [-200, 150, 180]]]},
            {"id": "판", "op": "box", "length": 440, "width": 340, "height": "=판_두께",
             "at": [0, 0, TOP], "align": ["center", "center", "min"]},
            # 비대칭 모따기 — 판 윗면 긴 모서리 둘
            {"id": "모따기", "op": "chamfer", "target": "판", "length": 2, "length2": 4,
             "edges": {"near": [[0, -170, top], [0, 170, top]], "tolerance": 1}},
            {"id": "구멍", "op": "hole", "target": "모따기", "at": [["=구멍_x", 0]],
             "diameter": 30},
            {"id": "작은구멍", "op": "hole", "target": "구멍",
             "at": [[-180, -130], [180, 130]],
             "diameter": 4},
            # 기준축 — 가운데 구멍의 축. 그 둘레로 핀 여섯
            {"id": "구멍축", "op": "datum_axis", "target": "작은구멍",
             "select": {"what": "faces", "kind": "cylinder", "radius": 15}},
            {"id": "핀", "op": "pin", "at": ["=구멍_x + 45", 0, top], "diameter": 8,
             "length": 20},
            {"id": "핀들", "op": "pattern", "source": "핀", "kind": "circular", "count": 6,
             "axis": "구멍축"},
            # 기준면 — 판 윗면. 그 위에 받침 블록, 반지름이 변하는 필렛
            {"id": "윗면", "op": "datum_plane", "target": "작은구멍",
             "select": {"kind": "plane", "normal": [0, 0, 1], "near": [100, 100, 232]}},
            {"id": "블록모양", "op": "sketch", "plane": {"datum": "윗면"},
             "shapes": [{"type": "rect", "width": 60, "height": 40, "at": [120, 80]}]},
            {"id": "블록", "op": "extrude", "sketch": "블록모양", "distance": 30},
            {"id": "블록필렛", "op": "fillet", "target": "블록", "radius": 2, "radius_end": 6,
             "start": [150, 100, top],
             "edges": {"near": [[150, 100, f"{top} + 15"]], "tolerance": 3}},
            {"id": "윗판", "op": "union", "targets": ["작은구멍", "핀들", "블록필렛"]},
            # 스케치 모양대로 하중 영역 — 판 윗면 위 ㄱ자(100 x 20 + 20 x 60 = 3200 mm²). 핀이
            # 도는 원(구멍에서 45)에 안 닿게 — 닿으면 핀 자리만큼 면이 줄어든다(형상이 그렇다).
            {"id": "하중모양", "op": "sketch", "plane": {"datum": "윗면"},
             "shapes": [{"type": "polyline", "start": [-170, 60], "segments": [
                 {"to": [-70, 60]}, {"to": [-70, 80]}, {"to": [-150, 80]}, {"to": [-150, 140]},
                 {"to": [-170, 140]}]}]},
            {"id": "하중판", "op": "divide_face", "target": "윗판", "shape": "sketch",
             "sketch": "하중모양", "tag": "하중면"},
            # 펼친 판을 굽힌 브래킷
            {"id": "전개", "op": "sketch",
             "shapes": [{"type": "rect", "width": 100, "height": 60,
                         "align": ["min", "center"]},
                        {"type": "circle", "radius": 4, "at": [25, 0], "mode": "cut"}]},
            {"id": "전개판", "op": "extrude", "sketch": "전개", "distance": 3},
            {"id": "굽힌판", "op": "bend", "target": "전개판",
             "bends": [{"at": 50, "radius": 4, "angle": 90}]},
            {"id": "브래킷", "op": "transform", "target": "굽힌판",
             "translate": [-320, 0, 120]},
            {"id": "조립", "op": "group", "targets": ["틀", "하중판", "브래킷"]},
        ],
    }  # fmt: skip


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def test_섞은_지그를_검사하고_미리보고_그림을_그린다(
    client: TestClient, member: Signed
) -> None:
    recipe = _recipe()
    checked = client.post(
        "/api/cad/recipe/check", json={"recipe": recipe}, headers=member.headers
    )
    assert checked.status_code == 200 and checked.json()["ok"], checked.text

    shown = client.post(
        "/api/cad/recipe/mesh", json={"recipe": recipe}, headers=member.headers
    )
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body["summary"]["solid_count"] == 3 and body["summary"]["warnings"] == []
    assert {one["id"]: one["kind"] for one in body["datums"]} == {
        "구멍축": "axis",
        "윗면": "plane",
    }
    # 구멍 축은 판 곁에 그린다(OCC 가 주는 점은 판에서 멀 수 있다).
    axis = next(one for one in body["datums"] if one["id"] == "구멍축")
    assert TOP <= axis["origin"][2] <= TOP + 12

    pictures = client.post(
        "/api/cad/recipe/views",
        json={"recipe": recipe, "views": ["iso", "top"], "width": 400},
        headers=member.headers,
    )
    assert pictures.status_code == 200, pictures.text
    assert all(one["png_base64"] for one in pictures.json()["views"].values())


def test_섞은_지그를_저장하면_STEP_이_나온다(client: TestClient, member: Signed) -> None:
    made = client.post(
        "/api/works", json={"name": "섞은 지그", "recipe": _recipe()}, headers=member.headers
    )
    assert made.status_code == 201, made.text
    job = made.json()["current"]["job"]
    assert job["status"] == "done", job.get("error")
    assert {one["kind"] for one in job["artifacts"]} == {"model_step", "model_glb"}


def test_DOE_가_구멍과_두께를_바꿔도_스케치_영역은_제자리다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    study = {
        "name": "섞은 지그 훑기",
        "recipe": _recipe(),
        "factors": [
            {"name": "구멍_x", "mode": "list", "values": [0, -60]},
            {"name": "판_두께", "mode": "list", "values": [12, 16]},
        ],
        "conditions": {
            "named_selections": [
                {"name": "하중면", "entity": "face",
                 "select": {"what": "faces", "tag": "하중면"}},
                {"name": "핀", "entity": "face",
                 "select": {"what": "faces", "body": "하중판", "kind": "cylinder",
                            "radius": 4}},
            ],
            "loads": [{"name": "누름", "type": "pressure", "on": "하중면", "magnitude": 1}],
        },
    }  # fmt: skip
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    done = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    folder = next(one for one in export_root.iterdir() if one.name.startswith("섞은_지그"))
    points = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]
    assert len(points) == 4
    for point in points:
        params = point["point"]["params"]
        assert point["unresolved"] == []
        (load,) = point["regions"]["하중면"]
        # ㄱ자의 넓이와 자리는 그대로, 높이만 판 윗면을 따라간다.
        assert load["area"] == pytest.approx(3200)
        assert load["centroid"] == pytest.approx([-135.0, 85.0, TOP + params["판_두께"]])
        # 핀 여섯은 구멍 축 둘레로 — 구멍을 옮기면 같이 옮겨 간다.
        pins = point["regions"]["핀"]
        assert len(pins) == 6
        middle = sum(one["centroid"][0] for one in pins) / 6
        assert middle == pytest.approx(params["구멍_x"], abs=1e-3)


def _assembly() -> dict[str, Any]:
    """각관 틀(기둥은 틀 밑면까지) 위에 판 — 규칙으로 모따기, M6 구멍마다 볼트 · 너트, 귀퉁이
    브래킷, 그리고 판과 틀 · 볼트 · 너트가 닿는 자리를 새긴다."""
    return {
        "params": {"두께": 10.0, "구멍_x": 150.0},
        "nodes": [
            {"id": "틀", "op": "frame", "corner": "miter",
             "profile": {"type": "square_tube", "width": 40, "thickness": 2},
             "paths": [[[-200, -150, 200], [200, -150, 200], [200, 150, 200], [-200, 150, 200],
                        [-200, -150, 200]],
                       [[-200, -150, 0], [-200, -150, 200]],
                       [[200, -150, 0], [200, -150, 200]],
                       [[200, 150, 0], [200, 150, 200]], [[-200, 150, 0], [-200, 150, 200]]]},
            {"id": "판", "op": "box", "length": 440, "width": 340, "height": "=두께",
             "at": [0, 0, 220], "align": ["center", "center", "min"]},
            {"id": "모따기", "op": "chamfer", "target": "판", "length": 2, "length2": 4,
             "edges": {"query": {"axis": "x",
                                 "of_face": {"normal": [0, 0, 1], "near": [0, 0, 1000]}}}},
            {"id": "윗판", "op": "hole", "target": "모따기", "thread": "M6",
             "at": [["=구멍_x", 100], ["=구멍_x", -100], ["=-구멍_x", 100],
                    ["=-구멍_x", -100]]},
            {"id": "볼트", "op": "fasten", "target": "윗판", "part": "bolt", "washer": True,
             "holes": {"kind": "cylinder", "radius": 3.3}, "length": "=두께 + 8"},
            {"id": "너트", "op": "fasten", "target": "윗판", "part": "nut", "side": "bottom",
             "holes": {"kind": "cylinder", "radius": 3.3}},
            {"id": "브래킷", "op": "bracket", "at": [-180, -150, 180], "size": 40,
             "legs": [[1, 0, 0], [0, 0, -1]]},
            {"id": "조립", "op": "group", "targets": ["틀", "윗판", "볼트", "너트", "브래킷"]},
            {"id": "새김", "op": "imprint", "target": "조립"},
        ],
    }  # fmt: skip


def test_새긴_접촉_자리와_체결_부품이_DOE_설계점마다_따라간다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    study = {
        "name": "체결 조립 훑기",
        "recipe": _assembly(),
        "factors": [
            {"name": "두께", "mode": "list", "values": [10, 14]},
            {"name": "구멍_x", "mode": "list", "values": [150, 120]},
        ],
        "conditions": {
            "named_selections": [
                {"name": "판 밑", "entity": "face",
                 "select": {"what": "faces", "tag": "윗판/틀"}},
                {"name": "틀 위", "entity": "face",
                 "select": {"what": "faces", "tag": "틀/윗판"}},
                {"name": "와셔 자리", "entity": "face",
                 "select": {"what": "faces", "tag": "윗판/볼트"}},
            ],
            "contacts": [
                {"name": "판-틀", "type": "bonded", "source": "판 밑", "target": "틀 위"}
            ],
        },
    }  # fmt: skip
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    done = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    folder = next(one for one in export_root.iterdir() if one.name.startswith("체결_조립"))
    points = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]
    assert len(points) == 4
    for point in points:
        params = point["point"]["params"]
        assert point["unresolved"] == []
        assert [one["name"] for one in point["bodies"]] == [
            "틀",
            "윗판",
            "볼트",
            "너트",
            "브래킷",
        ]
        # 판과 틀이 닿는 자리 — 각관 틀 윗면(440 x 340 - 360 x 260)이 양쪽에 같은 짝으로.
        (under,) = point["regions"]["판 밑"]
        (over,) = point["regions"]["틀 위"]
        assert under["area"] == over["area"] == pytest.approx(56000)
        assert under["normal"] == [0.0, 0.0, -1.0] and over["normal"] == [0.0, 0.0, 1.0]
        # 와셔 넷이 앉는 자리 — 구멍을 옮기면 따라간다.
        seats = point["regions"]["와셔 자리"]
        assert len(seats) == 4
        assert sorted({abs(one["centroid"][0]) for one in seats}) == [params["구멍_x"]]
        assert {one["centroid"][2] for one in seats} == {220 + params["두께"]}


SHEET = {
    "nodes": [
        {
            "id": "m",
            "op": "sheet_metal",
            "thickness": 2,
            "width": 40,
            "path": [[0, 30], [0, 0], [40, 0], [40, 25]],
            "bend_radius": 3,
        }
    ]
}


def test_전개도는_요약_DXF_SVG_로_받는다(client: TestClient, member: Signed) -> None:
    got = client.post("/api/cad/recipe/unfold", json={"recipe": SHEET}, headers=member.headers)
    assert got.status_code == 200, got.text
    summary = got.json()
    assert summary["thickness"] == 2 and len(summary["bends"]) == 2
    assert {one["direction"] for one in summary["bends"]} == {"up"}

    dxf = client.post(
        "/api/cad/recipe/unfold?format=dxf", json={"recipe": SHEET}, headers=member.headers
    )
    assert dxf.status_code == 200 and dxf.headers["content-type"].startswith("application/dxf")
    text = dxf.text
    # CAM 이 층으로 가른다 — 외곽 · 굽힘선 · 글씨.
    for layer in ("OUTLINE", "BEND_UP", "BEND_TEXT", "UP 90"):
        assert layer in text, layer
    svg = client.post(
        "/api/cad/recipe/unfold?format=svg",
        json={"recipe": SHEET, "flip": True},
        headers=member.headers,
    )
    assert svg.status_code == 200 and "<svg" in svg.text

    box = {"nodes": [{"id": "b", "op": "box", "length": 10, "width": 10, "height": 10}]}
    bad = client.post("/api/cad/recipe/unfold", json={"recipe": box}, headers=member.headers)
    assert bad.status_code == 400 and "전개할 수 없습니다" in bad.json()["error"]["message"]


def test_도면은_PDF_DXF_SVG_PNG_요약으로_받는다(client: TestClient, member: Signed) -> None:
    plate = {
        "nodes": [
            {"id": "p", "op": "box", "length": 80, "width": 50, "height": 10},
            {
                "id": "h",
                "op": "hole",
                "target": "p",
                "at": [[-30, -15], [30, 15]],
                "diameter": 6.6,
            },
        ]
    }
    body = {"recipe": plate, "title": "받침판", "material": "SS400"}
    summary = client.post(
        "/api/cad/recipe/drawing?format=json", json=body, headers=member.headers
    )
    assert summary.status_code == 200, summary.text
    got = summary.json()
    assert got["sheet"] == "A3" and got["scale"] == "2:1"
    assert [one["spec"] for one in got["holes"]] == ["Ø6.6 관통", "Ø6.6 관통"]
    assert sorted(one["value"] for one in got["dimensions"]) == [10, 50, 80]
    for fmt, head in (
        ("pdf", b"%PDF"),
        ("png", b"\x89PNG"),
        ("svg", b"<svg"),
        ("dxf", b"  0"),
    ):
        made = client.post(
            f"/api/cad/recipe/drawing?format={fmt}", json=body, headers=member.headers
        )
        assert made.status_code == 200, (fmt, made.text[:200])
        assert made.content.startswith(head), fmt
    bad = client.post(
        "/api/cad/recipe/drawing", json={**body, "sheet": "A0"}, headers=member.headers
    )
    assert bad.status_code == 422


def test_중간면_요약과_STEP(client: TestClient, member: Signed, tmp_path: Path) -> None:
    box = {
        "nodes": [
            {"id": "b", "op": "box", "length": 100, "width": 60, "height": 40},
            {"id": "s", "op": "shell", "target": "b", "thickness": 2, "open": "top"},
        ]
    }
    got = client.post(
        "/api/cad/recipe/midsurface", json={"recipe": box}, headers=member.headers
    )
    assert got.status_code == 200, got.text
    assert got.json()["bodies"][0]["thickness"] == 2
    assert got.json()["area"] == pytest.approx(98 * 58 + 2 * (98 + 58) * 39, rel=1e-6)

    step = client.post(
        "/api/cad/recipe/midsurface?format=step", json={"recipe": box}, headers=member.headers
    )
    assert step.status_code == 200 and step.headers["content-type"] == "application/step"
    path = tmp_path / "mid.step"
    path.write_bytes(step.content)
    from build123d import import_step

    shape = import_step(path)
    assert shape.solids() == [] and len(shape.faces()) == 5  # 바닥 + 네 벽, 솔리드가 아니다

    cube = {"nodes": [{"id": "c", "op": "box", "length": 20, "width": 20, "height": 20}]}
    bad = client.post(
        "/api/cad/recipe/midsurface", json={"recipe": cube}, headers=member.headers
    )
    assert bad.status_code == 400 and "판이 아닙니다" in bad.json()["error"]["message"]


def test_구속_윤곽을_풀어_본다(client: TestClient, member: Signed) -> None:
    shape: dict[str, Any] = {
        "type": "constrained",
        "points": {"a": [1, -2], "b": [55, 3], "c": [58, 37], "d": [-3, 44]},
        "segments": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "d"},
            {"from": "d", "to": "a"},
        ],
        "constraints": [
            {"type": "fix", "points": ["a"], "at": [0, 0]},
            {"type": "horizontal", "segments": [0]},
            {"type": "vertical", "segments": [1]},
            {"type": "horizontal", "segments": [2]},
            {"type": "vertical", "segments": [3]},
            {"type": "length", "segments": [0], "value": "=폭"},
        ],
    }
    got = client.post(
        "/api/cad/recipe/sketch-solve",
        json={"shape": shape, "params": {"폭": 70}},
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    assert got.json()["points"]["b"] == [70, 0]
    assert got.json()["free"] == 1  # 높이를 안 정했다

    shape["constraints"].append({"type": "length", "segments": [2], "value": 50})
    bad = client.post(
        "/api/cad/recipe/sketch-solve",
        json={"shape": shape, "params": {"폭": 70}},
        headers=member.headers,
    )
    assert bad.status_code == 400 and "구속 7(길이)" in bad.json()["error"]["message"]
