"""SimEngBay 에 건넬 **조건 픽스처** — 우리 내보내기 코드가 실제로 쓰는 폴더.

받는 쪽은 시험을 **양쪽이 실제로 낸 파일**로 돌린다(SimEngBay `docs/해석-연동-계획.md`). 손으로
짠 JSON 은 우리 코드가 바뀌어도 그대로라, 어긋난 줄을 아무도 모른다. 그래서 픽스처는 이 시험이
만든다 — 평소에는 내용이 맞는지 보기만 하고, `COMPCORE_FIXTURE_OUT` 을 주면 그 자리에 폴더를
복사한다::

    COMPCORE_FIXTURE_OUT=../fixtures/simengbay \
        .venv/bin/pytest tests/api/test_fixture_export.py

물성은 MatNexus 의 **실제 줄**(`tests/fixtures/matnexus/*.json`, 2026-09-28 스냅샷)을 화면이
싣는 모양 그대로 싣는다 — 시험 환경은 MatNexus 에 닿지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

MATNEXUS = Path(__file__).parents[1] / "fixtures" / "matnexus"


@pytest.fixture(autouse=True)
def export_root(tmp_path: Path) -> Iterator[Path]:
    """공유 폴더는 임시 폴더로 — 진짜 F: 드라이브에 쓰지 않는다."""
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _material(code: str, bodies: list[str]) -> dict[str, Any]:
    """화면(`ConditionsPanel` 의 물성 담기)이 싣는 모양 그대로 — payload 통째로."""
    row = json.loads((MATNEXUS / f"{code}.json").read_text(encoding="utf-8"))
    return {
        "apply_to": bodies,
        "ref": {
            "source": "matnexus",
            "material_id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "fetched_at": "2026-09-28T00:00:00Z",
        },
        "payload": row["payload"],
    }


def _face(name: str, select: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "entity": "face", "select": {"what": "faces", **select}}


#: ① **바디 둘 · 재료 둘** — 강판(SECC) 위에 알루미늄 블록(Al5052)을 본딩. 판 두께를 훑는다.
#: 받는 쪽이 「어느 Mechanical 바디가 어느 파트인가」 를 부피 · 무게중심으로 짝지을 자리.
TWO_BODIES: dict[str, Any] = {
    "name": "조건_두바디_두재료",
    "recipe": {
        "params": {"두께": 5.0},
        "nodes": [
            {
                "id": "받침판",
                "op": "box",
                "length": 100,
                "width": 60,
                "height": "=두께",
                "align": ["center", "center", "min"],
            },
            {
                "id": "블록",
                "op": "box",
                "length": 40,
                "width": 40,
                "height": 20,
                "at": [0, 0, "=두께"],
                "align": ["center", "center", "min"],
            },
            {"id": "조립", "op": "group", "targets": ["받침판", "블록"]},
        ],
    },
    "factors": [{"name": "두께", "mode": "list", "values": [5, 8]}],
    "conditions": {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("바닥", {"role": "bottom"}),
            _face("블록 윗면", {"role": "top", "near": [0, 0, 25]}),
            _face("판 윗면", {"kind": "plane", "normal": [0, 0, 1], "near": [40, 25, 5]}),
            _face("블록 아랫면", {"kind": "plane", "normal": [0, 0, -1], "near": [0, 0, 5]}),
        ],
        "materials": [
            _material("M-000138", ["받침판"]),
            _material("M-000158", ["블록"]),
        ],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
        "loads": [
            {
                "name": "누름",
                "type": "pressure",
                "on": "블록 윗면",
                "magnitude": 1.5,
                "direction": "normal",
            }
        ],
        "contacts": [
            {
                "name": "블록-판",
                "type": "bonded",
                "source": "블록 아랫면",
                "target": "판 윗면",
            }
        ],
        "mesh_hints": [{"on": "전체", "element_size": 4, "order": "quadratic"}],
        "analysis": {"type": "static"},
    },
}

#: ② **SI 로 내보내기 · 원통면** — 구멍에 원통 지지(접선은 풀어 돈다) · 베어링 하중, 모달.
#: 값은 mm · N · t 로 적었고 점 파일에는 SI 로 옮겨져 나간다.
HOLE_SI: dict[str, Any] = {
    "name": "조건_원통_SI",
    "recipe": {
        "params": {"지름": 12.0},
        "nodes": [
            {
                "id": "판",
                "op": "box",
                "length": 80,
                "width": 50,
                "height": 10,
                "align": ["min", "center", "min"],
            },
            {"id": "구멍", "op": "hole", "target": "판", "at": [[20, 0]], "diameter": "=지름"},
        ],
    },
    "factors": [{"name": "지름", "mode": "list", "values": [10, 12]}],
    "conditions": {
        "units": {"system": "si"},
        "named_selections": [
            _face("구멍면", {"kind": "cylinder", "near": [20, 0, 5]}),
            _face("끝면", {"kind": "plane", "normal": [1, 0, 0], "near": [80, 0, 5]}),
        ],
        "materials": [_material("M-000158", ["전체"])],
        "constraints": [
            {
                "name": "핀",
                "type": "cylindrical",
                "on": "구멍면",
                "tangential": "free",
            }
        ],
        "loads": [
            {
                "name": "끝 누름",
                "type": "force",
                "on": "끝면",
                "magnitude": 200,
                "direction": [0, 0, -1],
            },
            {
                "name": "핀 하중",
                "type": "bearing",
                "on": "구멍면",
                "magnitude": 500,
                "direction": [1, 0, 0],
            },
        ],
        # 계가 바뀌면 숫자가 바뀌는 값 — 2 mm 가 점 파일에는 0.002 m 로 나간다.
        "mesh_hints": [{"on": "구멍면", "element_size": 2}],
        "analysis": {"type": "modal", "modes": 8, "frequency_range": [0, 5000]},
    },
}


def _export(client: TestClient, member: Signed, root: Path, study: dict[str, Any]) -> Path:
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    done = client.post(f"/api/doe/{made.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    prefix = study["name"].replace(" ", "_")
    return next(one for one in root.iterdir() if one.name.startswith(prefix))


def _points(folder: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((folder / "points").glob("p*.json"))
    ]


def test_조건_픽스처를_실제_내보내기로_만든다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    two = _export(client, member, export_root, TWO_BODIES)
    hole = _export(client, member, export_root, HOLE_SI)

    # ① 바디마다 재료가 따로 — 받는 쪽이 부피 · 무게중심으로 짝지을 수 있게 둘 다 실린다.
    for point in _points(two):
        bodies = {one["name"]: one for one in point["bodies"]}
        assert set(bodies) == {"받침판", "블록"}
        for one in bodies.values():
            assert one["volume"] > 0 and len(one["centroid"]) == 3
        materials = point["conditions"]["materials"]
        assert [one["apply_to"] for one in materials] == [["받침판"], ["블록"]]
        assert materials[0]["ref"]["code"] == "M-000138"
        assert materials[1]["ref"]["code"] == "M-000158"
        # 접촉 · 구속 · 하중의 선택 그룹이 이 점에서 풀렸다.
        assert point["unresolved"] == []
        assert point["conditions"]["analysis"]["type"] == "static"
    thick = [
        {one["name"]: one["volume"] for one in point["bodies"]}["받침판"]
        for point in _points(two)
    ]
    assert thick == [pytest.approx(30000), pytest.approx(48000)]

    # ② SI 로 옮겨져 나간다 — 베어링 500 N 은 그대로, 모달의 칸만.
    for point in _points(hole):
        conditions = point["conditions"]
        assert conditions["units"]["system"] == "si"
        assert point["unresolved"] == []
        bearing = next(one for one in conditions["loads"] if one["type"] == "bearing")
        assert bearing["magnitude"] == 500 and bearing["unit"] == "N"
        assert conditions["constraints"][0]["tangential"] == "free"
        assert conditions["mesh_hints"][0]["element_size"] == pytest.approx(0.002)
        assert set(conditions["analysis"]) == {
            "type",
            "modes",
            "frequency_range",
            "prestressed",
            "solver",
        }

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        for folder in (two, hole):
            # 폴더 이름의 끝(스터디 id 여덟 자리)은 돌릴 때마다 달라진다 — 이름만 남긴다.
            name = folder.name.rsplit("-", 1)[0]
            shutil.rmtree(target / name, ignore_errors=True)
            shutil.copytree(folder, target / name)
