"""점(꼭짓점) · 엣지 선택 그룹이 DOE 내보내기의 모든 길을 지나는가 — 지문 · 좌표 따라가기 ·
드리프트 · 좌표계 · 하중. SimEngBay 가 2026-09-28 에 점 그룹에서 KeyError 를 짚었다(그때 점
지문을 엣지 지문으로 보냈다). 같은 일이 다른 길에서 다시 나지 않게 끝까지 돌려 본다."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def test_점_엣지_그룹이_설계점마다_풀려_나간다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    recipe = {
        "params": {"길이": 80.0},
        "nodes": [
            {"id": "판", "op": "box", "length": "=길이", "width": 40, "height": 10,
             "align": ["min", "center", "min"]},
        ],
    }  # fmt: skip
    study = {
        "name": "점 그룹 훑기",
        "recipe": recipe,
        "factors": [{"name": "길이", "mode": "list", "values": [80, 120]}],
        "conditions": {
            "named_selections": [
                {"name": "바닥", "entity": "face",
                 "select": {"what": "faces", "role": "bottom"}},
                # 3D 에서 고른 것과 같은 모양 — 엣지 3 개가 모이는 점 중 이 자리의 것.
                {"name": "끝점", "entity": "vertex",
                 "select": {"what": "vertices", "edges": 3, "near": [80, 20, 10], "limit": 1}},
                {"name": "끝 모서리", "entity": "edge",
                 "select": {"what": "edges", "kind": "line", "axis": "y",
                            "near": [80, 0, 10], "limit": 1}},
                {"name": "윗 꼭짓점들", "entity": "vertex",
                 "select": {"what": "vertices", "of_face": {"normal": [0, 0, 1]}}},
            ],
            "coordinate_systems": [{"name": "끝", "on": "끝점"}],
            "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
            "loads": [
                {"name": "점 힘", "type": "force", "on": "끝점", "magnitude": 10,
                 "direction": [0, 0, -1]},
                {"name": "선 힘", "type": "force", "on": "끝 모서리", "magnitude": 5,
                 "direction": [0, 0, -1]},
            ],
        },
    }  # fmt: skip
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    done = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    folder = next(one for one in export_root.iterdir() if one.name.startswith("점_그룹"))
    manifest = (folder / "manifest.csv").read_text(encoding="utf-8")
    points = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]
    assert len(points) == 2, manifest
    for point in points:
        length = point["point"]["params"]["길이"]
        regions = point["regions"]
        # 끝점은 길이를 따라 옮겨 간다(좌표 따라가기) — 점 지문은 자리 하나.
        assert regions["끝점"] == [{"point": [length, 20.0, 10.0]}]
        (edge,) = regions["끝 모서리"]
        assert edge["midpoint"] == [length, 0.0, 10.0] and edge["length"] == 40.0
        assert len(regions["윗 꼭짓점들"]) == 4
        assert point["unresolved"] == []
        # 점 그룹에 붙인 좌표계 — 원점은 그 점, 방향은 전역.
        (frame,) = [one for one in point["coordinate_systems"] if one["name"] == "끝"]
        assert frame["origin"] == [length, 20.0, 10.0]
        assert (frame["x"], frame["z"]) == ([1.0, 0.0, 0.0], [0.0, 0.0, 1.0])


def test_선택_규칙의_식은_설계점마다_풀린다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """「반지름 =지름/2 인 원통면」 — 구멍 지름을 훑어도 그 구멍을 잡는다. 전에는 저장된 식을
    그대로 찾다가 DOE 작업 전체가 「could not convert string to float」 로 죽었다."""
    recipe = {
        "params": {"지름": 8.0},
        "nodes": [
            {"id": "판", "op": "box", "length": 60, "width": 40, "height": 10},
            {"id": "구멍", "op": "hole", "target": "판", "at": [[10, 0], [-10, 0]],
             "diameter": "=지름"},
            {"id": "작은", "op": "hole", "target": "구멍", "at": [[0, 12]], "diameter": 3},
        ],
    }  # fmt: skip
    rule = {"what": "faces", "kind": "cylinder", "radius": "=지름 / 2"}
    preview = client.post(
        "/api/cad/recipe/find", json={"recipe": recipe, "query": rule}, headers=member.headers
    )
    assert preview.status_code == 200 and preview.json()["total"] == 2, preview.text

    study = {
        "name": "식 규칙 훑기",
        "recipe": recipe,
        "factors": [{"name": "지름", "mode": "list", "values": [8, 12]}],
        "conditions": {
            "named_selections": [{"name": "구멍들", "entity": "face", "select": rule}],
        },
    }
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    done = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    folder = next(one for one in export_root.iterdir() if one.name.startswith("식_규칙"))
    for path in sorted((folder / "points").glob("p*.json")):
        point = json.loads(path.read_text(encoding="utf-8"))
        radius = point["point"]["params"]["지름"] / 2
        holes = point["regions"]["구멍들"]
        assert [one["radius"] for one in holes] == [radius, radius]
