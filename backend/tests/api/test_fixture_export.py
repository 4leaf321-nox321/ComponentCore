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
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from tests.api.conftest import Signed

MATNEXUS = Path(__file__).parents[1] / "fixtures" / "matnexus"


@pytest.fixture(autouse=True)
def property_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """MatNexus 물성 사전(2026-09-29 스냅샷). 시험은 MatNexus 에 닿지 않는데, 사전이 없으면
    물성 줄에 표준 열쇠(`mechanical.youngs_modulus`)가 안 붙어 픽스처가 「탄성계수가 없다」 고
    말했다."""
    from app.shared.clients import matnexus

    table = json.loads((MATNEXUS / "property_keys.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(matnexus, "property_keys", lambda: table)


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
            # **바디와 방향으로** 고른다 — 좌표가 없어 두께를 훑어도 헛집지 않는다. 2026-10-02
            # 까지는 「+Z 평면 중 (40, 25, 5) 의 면」 이었는데 near 가 순서만 정해 판 윗면과
            # 블록 윗면을 둘 다 집었다(SimEngBay 가 받고 알려 줬다).
            _face("바닥", {"body": "받침판", "normal": [0, 0, -1]}),
            _face("블록 윗면", {"body": "블록", "normal": [0, 0, 1]}),
            _face("판 윗면", {"body": "받침판", "normal": [0, 0, 1]}),
            _face("블록 아랫면", {"body": "블록", "normal": [0, 0, -1]}),
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


#: ③ **재료 훑기** — 형상은 그대로, 블록의 재료만 Al5052 ↔ SECC 로 바꿔 끼운다. 두 점이 한
#: 형상(`shapes/<지문>.step`)을 나눠 쓰고, 점 파일의 `conditions.materials` 만 다르다.
MATERIAL_SWEEP: dict[str, Any] = {
    "name": "조건_재료훑기",
    "recipe": TWO_BODIES["recipe"],
    "factors": [
        {
            "name": "블록 재료",
            "mode": "material",
            "bodies": ["블록"],
            "values": ["AL5052H32DEMO_-_-", "SECC-EXAD87-DP_선언물성_0.8"],
        }
    ],
    "conditions": TWO_BODIES["conditions"],
}


#: ④ **조건을 훑는다** — 접촉 종류(본딩 ↔ 마찰)와 블록 탄성계수 배율(0.9 · 1.1)의 조합. 하중은
#: 인자가 아닌 도면 변수(`=압력`)를, 모드 수는 정수 칸의 식(`=모드수`)을 부른다.
CONDITION_SWEEP: dict[str, Any] = {
    "name": "조건_조건훑기",
    "recipe": {
        **TWO_BODIES["recipe"],
        "params": {**TWO_BODIES["recipe"]["params"], "압력": 1.5, "모드수": 10},
    },
    "factors": [
        {
            "name": "접촉 종류",
            "mode": "choice",
            "target": {"group": "contacts", "item": "블록-판", "field": "type"},
            "values": ["bonded", "frictional"],
        },
        {
            "name": "블록 탄성계수 배율",
            "mode": "scale",
            "bodies": ["블록"],
            "property": "탄성계수",
            "values": [0.9, 1.1],
        },
    ],
    "conditions": {
        **TWO_BODIES["conditions"],
        "loads": [{**TWO_BODIES["conditions"]["loads"][0], "magnitude": "=압력"}],
        # 마찰로 바꿔 볼 것이므로 마찰계수를 미리 적어 둔다(본딩에서는 쓰이지 않는다).
        "contacts": [{**TWO_BODIES["conditions"]["contacts"][0], "friction": 0.2}],
        "analysis": {"type": "modal", "modes": "=모드수"},
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


#: ⑤ **측면 가진 · 조화 응답** — 강판 위의 알루미늄 기둥 끝을 X 로 흔든다. 기둥 높이를 훑으면
#: 첫 굽힘 모드(외팔보 어림 80 → 약 1290 Hz, 100 → 약 830 Hz)가 200 ~ 2000 Hz 창 안에서
#: 움직인다 — 블록 윗면 Z 압력(29 ~ 31 kHz, 준정적)으로는 못 보던 공진 증폭이 보인다
#: (SimEngBay 의 부탁, 2026-10-02). 기둥 끝 꼭짓점을 「측정점」 점 그룹으로 싣는다.
LATERAL: dict[str, Any] = {
    "name": "조건_측면가진",
    "recipe": {
        "params": {"기둥_높이": 100.0},
        "nodes": [
            {"id": "받침판", "op": "box", "length": 80, "width": 80, "height": 10,
             "align": ["center", "center", "min"]},
            {"id": "기둥", "op": "box", "length": 10, "width": 10, "height": "=기둥_높이",
             "at": [0, 0, 10], "align": ["center", "center", "min"]},
            {"id": "조립", "op": "group", "targets": ["받침판", "기둥"]},
            # 닿는 자리를 새긴다 — 본딩 접촉의 두 면이 넓이 · 자리까지 같아진다.
            {"id": "새김", "op": "imprint", "target": "조립"},
        ],
    },
    "factors": [{"name": "기둥_높이", "mode": "list", "values": [80, 100]}],
    "conditions": {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("바닥", {"body": "받침판", "normal": [0, 0, -1]}),
            _face("기둥 끝", {"body": "기둥", "normal": [0, 0, 1]}),
            _face("접합 판쪽", {"tag": "받침판/기둥"}),
            _face("접합 기둥쪽", {"tag": "기둥/받침판"}),
            {"name": "측정점", "entity": "vertex",
             "select": {"what": "vertices", "of_face": {"body": "기둥", "normal": [0, 0, 1]},
                        "near": [5, 5, "=10 + 기둥_높이"], "limit": 1}},
        ],
        "materials": [
            _material("M-000138", ["받침판"]),
            _material("M-000158", ["기둥"]),
        ],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
        "loads": [
            {"name": "측면 가진", "type": "force", "on": "기둥 끝", "magnitude": 10,
             "direction": [1, 0, 0]}
        ],
        "contacts": [
            {"name": "기둥-판", "type": "bonded", "source": "접합 기둥쪽",
             "target": "접합 판쪽"}
        ],
        "mesh_hints": [{"on": "전체", "element_size": 2, "order": "quadratic"}],
        "analysis": {
            "type": "harmonic",
            "frequency_range": [200, 2000],
            "method": "mode_superposition",
            "modes": 6,
            "solution_intervals": 90,
            "damping_ratio": 0.02,
        },
    },
}  # fmt: skip


def test_측면_가진_픽스처_공진이_창_안에서_움직인다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    folder = _export(client, member, export_root, LATERAL)
    points = _points(folder)
    assert [point["point"]["params"]["기둥_높이"] for point in points] == [80, 100]
    for point in points:
        height = point["point"]["params"]["기둥_높이"]
        assert point["unresolved"] == []
        regions = point["regions"]
        # 측정점 — 기둥 끝 꼭짓점 하나, 점 지문은 자리(`point`)뿐이다.
        assert regions["측정점"] == [{"point": [5.0, 5.0, 10.0 + height], "body": "기둥"}]
        # 새긴 접합면 — 양쪽이 같은 넓이 · 자리, 법선만 반대.
        (plate,) = regions["접합 판쪽"]
        (post,) = regions["접합 기둥쪽"]
        assert plate["area"] == post["area"] == pytest.approx(100)
        assert plate["centroid"] == post["centroid"] == [0.0, 0.0, 10.0]
        assert (plate["normal"], post["normal"]) == ([0.0, 0.0, 1.0], [0.0, 0.0, -1.0])
        conditions = point["conditions"]
        assert conditions["loads"][0]["direction"] == [1, 0, 0]
        assert conditions["analysis"]["type"] == "harmonic"
        assert conditions["analysis"]["frequency_range"] == [200, 2000]
        bodies = {one["name"]: one for one in point["bodies"]}
        assert bodies["기둥"]["volume"] == pytest.approx(100 * height)

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / folder.name.rsplit("-", 1)[0]
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)


#: ⑤-1 **설계 하나** — 「측면 가진」 과 같은 형상 · 조건에서 인자만 비웠다(`factors: []`,
#: 화면의 「해석용으로 내보내기」). 지금 도면 그대로(기둥 높이 100) 설계점 하나 — 폴더 계약은
#: DOE 와 같다. 받는 쪽이 `[]` 를 「인자가 없다는 선언」 으로 읽고 manifest 의 다른 열을 변수로
#: 짐작하지 않는지 보는 자리(SimEngBay 의 부탁, 2026-10-04).
SINGLE: dict[str, Any] = {**LATERAL, "name": "설계하나_측면가진", "factors": []}


def test_설계_하나_픽스처_인자가_없어도_같은_폴더다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    folder = _export(client, member, export_root, SINGLE)
    spec = json.loads((folder / "study.json").read_text(encoding="utf-8"))
    assert spec["factors"] == []
    assert (spec["method"], spec["samples"]) == ("factorial", 1)
    (point,) = _points(folder)
    assert point["point"]["number"] == 1 and point["point"]["params"] == {}
    assert point["point"]["step_file"] == "points/p0001.step"
    assert (folder / "points" / "p0001.step").exists()
    assert point["unresolved"] == []
    # 도면의 값 그대로 — 기둥 높이 100.
    assert point["regions"]["측정점"] == [{"point": [5.0, 5.0, 110.0], "body": "기둥"}]
    bodies = {one["name"]: one for one in point["bodies"]}
    assert bodies["기둥"]["volume"] == pytest.approx(10000)
    assert point["conditions"]["analysis"]["type"] == "harmonic"
    # 표에는 변수 열이 없다 — 되짚는 열쇠 · 파일 · 사유뿐.
    header, row = (folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines()
    assert header.split(",") == [
        "point", "status", "step_file", "point_file",
        "unresolved", "interference", "warnings", "error",
    ]  # fmt: skip
    assert row.startswith("1,ok,points/p0001.step,points/p0001.json")

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / folder.name.rsplit("-", 1)[0]
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)


#: ⑥ **전단을 받는 이음 — 마찰이 할 일이 있는 자리.** 강판(SECC) 위에 알루미늄 판(Al5052)을
#: 40 mm 겹쳐 놓고(겹침 이음), 겹친 자리를 위에서 누른 채(클램프 압력 P, 40 x 20 자리) 위판
#: 끝을 X 로 당긴다(변위 제어 — 미끄러져도 강체 운동이 아니다). 지금까지의 픽스처는 이음이
#: 압축만 받아 마찰이 할 일이 없었고, 두 솔버가 「마찰은 차이 없음」 에 동의할 뿐이었다
#: (SimEngBay, 2026-10-03). 여기서는 전단이 이음을 지나므로 본딩 · 마찰(붙음) · 마찰(미끄러짐)
#: 이 서로 다른 답을 내고, 미끄러지는 한계가 손셈 μ · N(N = P · 800 mm²)이다.
SHEAR_JOINT: dict[str, Any] = {
    "name": "조건_전단이음",
    "method": "table",
    "recipe": {
        "params": {"당김": 0.04, "클램프": 12.5, "마찰계수": 0.15},
        "nodes": [
            {"id": "아래판", "op": "box", "length": 100, "width": 25, "height": 5,
             "align": ["min", "center", "min"]},
            {"id": "위판_원형", "op": "box", "length": 100, "width": 25, "height": 5,
             "at": [60, 0, 5], "align": ["min", "center", "min"]},
            # 클램프가 누르는 자리 — 겹친 자리 위 40 x 20. 판 폭(25)보다 좁게 둬 면의
            # 테두리와 겹치지 않는다.
            {"id": "위판", "op": "divide_face", "target": "위판_원형",
             "on": {"normal": [0, 0, 1]}, "shape": "rect", "size": [40, 20], "at": [80, 0, 10],
             "tag": "클램프"},
            {"id": "조립", "op": "group", "targets": ["아래판", "위판"]},
            # 닿는 자리를 새긴다 — 이음의 두 면이 넓이 · 자리까지 같다.
            {"id": "새김", "op": "imprint", "target": "조립"},
        ],
    },
    "factors": [
        {"name": "접촉 종류", "mode": "choice",
         "target": {"group": "contacts", "item": "이음", "field": "type"},
         "values": ["bonded", "frictional"]},
    ],
    # 표로 준다 — 본딩에는 마찰계수가 뜻이 없어 격자로 짜면 같은 점이 둘 생긴다.
    "table": [
        {"접촉 종류": "bonded", "마찰계수": 0.15, "클램프": 12.5},
        {"접촉 종류": "frictional", "마찰계수": 0.15, "클램프": 12.5},  # μN 1.5 kN — 미끄러짐
        {"접촉 종류": "frictional", "마찰계수": 0.6, "클램프": 12.5},  # μN 6 kN — 붙어 있다
        {"접촉 종류": "frictional", "마찰계수": 0.3, "클램프": 25},  # μN 6 kN — 셋째와 같아야
    ],
    "measures": [
        {"name": "접합_넓이", "kind": "region_area", "region": "접합 위판쪽"},
        {"name": "클램프_넓이", "kind": "region_area", "region": "클램프면"},
    ],
    "conditions": {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("고정단", {"body": "아래판", "normal": [-1, 0, 0]}),
            _face("바닥", {"body": "아래판", "normal": [0, 0, -1]}),
            _face("당기는 끝", {"body": "위판", "normal": [1, 0, 0]}),
            _face("클램프면", {"tag": "클램프"}),
            _face("접합 아래판쪽", {"tag": "아래판/위판"}),
            _face("접합 위판쪽", {"tag": "위판/아래판"}),
            # 미끄럼을 읽는 점 둘 — **같은 자리, 다른 바디**(이음 입구의 모서리). 두 점의 X
            # 변위 차가 곧 이음의 미끄럼이다.
            {"name": "이음 입구 위판", "entity": "vertex",
             "select": {"what": "vertices", "of_face": {"body": "위판", "normal": [0, 0, -1]},
                        "near": [60, 12.5, 5], "limit": 1}},
            {"name": "이음 입구 아래판", "entity": "vertex",
             "select": {"what": "vertices", "of_face": {"body": "아래판", "normal": [0, 0, 1]},
                        "near": [60, 12.5, 5], "limit": 1}},
        ],
        "materials": [
            _material("M-000138", ["아래판"]),
            _material("M-000158", ["위판"]),
        ],
        "constraints": [
            {"name": "고정단 고정", "type": "fixed_support", "on": "고정단"},
            # 아래판은 평평한 바닥에 놓여 있다 — 클램프 압력을 바닥이 받는다(없으면 외팔보).
            {"name": "바닥 받침", "type": "frictionless", "on": "바닥"},
            {"name": "당김", "type": "displacement", "on": "당기는 끝", "cs": "global",
             "x": "=당김", "y": 0, "z": 0},
        ],
        "loads": [
            {"name": "클램프", "type": "pressure", "on": "클램프면", "magnitude": "=클램프",
             "direction": "normal"}
        ],
        "contacts": [
            {"name": "이음", "type": "bonded", "source": "접합 위판쪽",
             "target": "접합 아래판쪽", "friction": "=마찰계수"}
        ],
        "mesh_hints": [
            {"on": "전체", "element_size": 2.5, "order": "quadratic"},
            {"on": "접합 위판쪽", "element_size": 1.25},
        ],
        "analysis": {"type": "static"},
    },
}  # fmt: skip


#: ⑦ **강체 지그 · 쉘 브래킷 · 해석 제외** — 파트별 설정(`body_settings`, 2026-10-04)을 받는
#: 쪽이 읽는지 보는 자리. 강체 지그블록 위에 판금 ㄱ자 브래킷(쉘)을 본딩하고, 브래킷의 세운
#: 다리 바깥면을 누른다. 지그블록 옆의 명판은 형상에만 있고 해석에서 뺀다. 두께를 훑으면 끝
#: 처짐이 1/t³ 로 줄어야 한다(2 → 3 mm 에 3.375 배) — 손셈이 쉬운 외팔 판이다.
RIGID_SHELL: dict[str, Any] = {
    "name": "조건_강체지그_쉘브래킷",
    "recipe": {
        "params": {"두께": 2.0, "압력": 0.05},
        "nodes": [
            {"id": "지그블록", "op": "box", "length": 80, "width": 40, "height": 20,
             "align": ["min", "center", "min"]},
            # 옆에서 본 꺾은선 — 지그블록 윗면(z 20)에 눕힌 다리 x 10 ~ 50, x 50 에서 위로
            # 70 까지. 두께는 꺾은선 안쪽(`right`): 눕힌 다리는 z 20 ~ 20+t, 세운 다리는
            # x 50-t ~ 50.
            {"id": "브래킷", "op": "sheet_metal", "thickness": "=두께", "width": 30,
             "path": [[10, 20], [50, 20], [50, 70]], "bend_radius": 4, "side": "right"},
            {"id": "명판", "op": "box", "length": 30, "width": 1, "height": 10,
             "at": [60, -20, 5], "align": ["min", "max", "min"]},
            {"id": "조립", "op": "group", "targets": ["지그블록", "브래킷", "명판"]},
        ],
    },
    "factors": [{"name": "두께", "mode": "list", "values": [2, 3]}],
    "conditions": {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("블록 바닥", {"body": "지그블록", "normal": [0, 0, -1]}),
            _face("블록 윗면", {"body": "지그블록", "normal": [0, 0, 1]}),
            _face("브래킷 바닥", {"body": "브래킷", "normal": [0, 0, -1]}),
            _face("하중면", {"body": "브래킷", "normal": [1, 0, 0]}),
            # 두께 쪽 면(눕힌 다리 앞끝 x 10) — 중간면에서는 모서리가 된다(`mid` 의 edge).
            _face("브래킷 앞끝",
                  {"body": "브래킷", "normal": [-1, 0, 0], "near": [10, 0, 21]}),
        ],
        "materials": [
            _material("M-000138", ["지그블록", "브래킷"]),
            # 해석에서 뺀 파트에도 물성은 붙어 있을 수 있다 — 받는 쪽은 그냥 버린다.
            _material("M-000158", ["명판"]),
        ],
        "constraints": [
            # 강체 면에는 고정 지지 · 원격 변위만 건다(받는 쪽 규칙) — 원격 변위로 여섯 성분.
            {"name": "블록 고정", "type": "remote_displacement", "on": "블록 바닥",
             "x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0, "behavior": "rigid"},
        ],
        "loads": [
            {"name": "누름", "type": "pressure", "on": "하중면", "magnitude": "=압력",
             "direction": "normal"}
        ],
        "contacts": [
            {"name": "브래킷 접합", "type": "bonded", "source": "브래킷 바닥",
             "target": "블록 윗면"}
        ],
        "body_settings": [
            {"name": "지그블록", "behavior": "rigid", "mesh": {"element_size": 10}},
            {"name": "브래킷", "representation": "shell",
             "mesh": {"element_size": "=두께", "order": "quadratic"}},
            {"name": "명판", "suppressed": True},
        ],
        "mesh_hints": [{"on": "전체", "element_size": 5, "defeature_size": 0.2}],
        "analysis": {"type": "static"},
    },
}  # fmt: skip


def test_강체_지그_쉘_브래킷_픽스처_파트별_설정이_실린다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    folder = _export(client, member, export_root, RIGID_SHELL)
    # 쉘 파트가 있으니 중간면은 고르지 않았어도 나간다 — 표에 `mid_file` 열이 선다.
    header = (folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert "mid_file" in header.split(",")
    points = _points(folder)
    assert [p["point"]["params"]["두께"] for p in points] == [2.0, 3.0]
    for point in points:
        thick = point["point"]["params"]["두께"]
        assert point["unresolved"] == []
        # 명판은 형상(STEP · bodies)에는 있다 — 해석에서만 뺀다.
        assert [one["name"] for one in point["bodies"]] == ["지그블록", "브래킷", "명판"]
        settings = {one["name"]: one for one in point["conditions"]["body_settings"]}
        assert settings["지그블록"]["behavior"] == "rigid"
        assert settings["지그블록"]["mesh"]["element_size"] == 10
        assert settings["브래킷"]["representation"] == "shell"
        assert settings["브래킷"]["mesh"]["element_size"] == pytest.approx(thick)
        assert settings["브래킷"]["mesh"]["order"] == "quadratic"
        assert settings["명판"]["suppressed"] is True
        # 쉘의 재료 — **쉘 파트만**(지그블록 · 명판은 안 만든다), 셸과 짝지을 무게중심 ·
        # 경계상자.
        mid = point["midsurface"]
        assert [one["name"] for one in mid["bodies"]] == ["브래킷"]
        bracket = mid["bodies"][0]
        assert bracket["thickness"] == pytest.approx(thick)
        assert len(bracket["centroid"]) == 3 and len(bracket["bbox"]) == 2
        assert "failed" not in mid
        assert (folder / mid["step_file"]).exists()
        assert point["length_units"]["midsurface"] == "mm"
        # STEP 의 이름 — 한글은 깨지므로 `step_product`(ASCII)를 싣는다. 중간면 셸도 그 이름.
        products = re.findall(
            r"PRODUCT\('([^']*)'",
            (folder / point["point"]["step_file"]).read_text(errors="replace"),
        )
        assert [one["step_product"] for one in point["bodies"]] == [
            "body_1",
            "body_2",
            "body_3",
        ]
        assert set(products) >= {"body_1", "body_2", "body_3"}
        assert bracket["step_product"] == "body_2"
        mid_products = re.findall(
            r"PRODUCT\('([^']*)'", (folder / mid["step_file"]).read_text(errors="replace")
        )
        assert "body_2" in mid_products
        regions = point["regions"]
        load = _only(regions, "하중면")
        assert load["body"] == "브래킷" and load["normal"] == [1.0, 0.0, 0.0]
        # 바깥면의 곧은 자리 — 꺾은선(x 50)이 바깥 면이라 안쪽 R4 + t 로 돌아 z 24+t 부터 70
        # 까지, 폭 30.
        assert load["area"] == pytest.approx(30 * (70 - 24 - thick))
        assert _only(regions, "브래킷 바닥")["body"] == "브래킷"
        assert _only(regions, "블록 바닥")["area"] == pytest.approx(3200)
        # 쉘 파트의 영역은 **중간면 기준으로도** — 겉면은 중간면의 면(원래 겉면의 바깥 법선),
        # 두께 쪽 면은 중간면의 모서리. 쉘이 아닌 파트에는 붙지 않는다.
        (face,) = load["mid"]
        assert face["face"]["area"] == pytest.approx(load["area"])
        assert face["face"]["normal"] == [1.0, 0.0, 0.0]
        assert face["face"]["centroid"][0] == pytest.approx(50 - thick / 2)
        (edge,) = _only(regions, "브래킷 앞끝")["mid"]
        assert edge["edge"]["length"] == pytest.approx(30)
        assert edge["edge"]["midpoint"] == pytest.approx([10.0, 0.0, 20 + thick / 2])
        assert "mid" not in _only(regions, "블록 바닥")

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / folder.name.rsplit("-", 1)[0]
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)


def _only(regions: dict[str, Any], name: str) -> dict[str, Any]:
    """그 그룹에 든 **하나** — 둘이면 짝이 어긋난 것이다."""
    (one,) = regions[name]
    return one  # type: ignore[no-any-return]


def test_전단_이음_픽스처_마찰이_할_일이_있다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    folder = _export(client, member, export_root, SHEAR_JOINT)
    points = _points(folder)
    rows = [
        (p["point"]["params"]["접촉 종류"], p["point"]["params"]["마찰계수"],
         p["point"]["params"]["클램프"])
        for p in points
    ]  # fmt: skip
    assert rows == [
        ("bonded", 0.15, 12.5),
        ("frictional", 0.15, 12.5),
        ("frictional", 0.6, 12.5),
        ("frictional", 0.3, 25),
    ]
    # 형상은 하나 — 네 점이 `shapes/` 의 STEP 한 벌을 나눠 쓴다(조건만 다르다).
    assert len({p["point"]["step_file"] for p in points}) == 1
    assert points[0]["point"]["step_file"].startswith("shapes/")
    for point in points:
        assert point["unresolved"] == []
        regions = point["regions"]
        assert _only(regions, "고정단")["area"] == pytest.approx(125)
        assert _only(regions, "고정단")["centroid"] == [0.0, 0.0, 2.5]
        assert _only(regions, "당기는 끝")["area"] == pytest.approx(125)
        assert _only(regions, "당기는 끝")["centroid"] == [160.0, 0.0, 7.5]
        assert _only(regions, "바닥")["area"] == pytest.approx(2500)
        assert _only(regions, "바닥")["normal"] == [0.0, 0.0, -1.0]
        clamp = _only(regions, "클램프면")
        assert clamp["area"] == pytest.approx(800) and clamp["centroid"] == [80.0, 0.0, 10.0]
        assert clamp["body"] == "위판"
        lower, upper = _only(regions, "접합 아래판쪽"), _only(regions, "접합 위판쪽")
        assert lower["area"] == upper["area"] == pytest.approx(1000)
        assert lower["centroid"] == upper["centroid"] == [80.0, 0.0, 5.0]
        assert (lower["normal"], upper["normal"]) == ([0.0, 0.0, 1.0], [0.0, 0.0, -1.0])
        assert (lower["body"], upper["body"]) == ("아래판", "위판")
        # 미끄럼을 읽는 점 — 같은 자리, 바디로 가른다.
        assert regions["이음 입구 위판"] == [{"point": [60.0, 12.5, 5.0], "body": "위판"}]
        assert regions["이음 입구 아래판"] == [{"point": [60.0, 12.5, 5.0], "body": "아래판"}]
        params = point["point"]["params"]
        conditions = point["conditions"]
        joint = conditions["contacts"][0]
        assert joint["type"] == params["접촉 종류"]
        assert joint["friction"] == pytest.approx(params["마찰계수"])
        assert conditions["loads"][0]["magnitude"] == pytest.approx(params["클램프"])
        pull = next(c for c in conditions["constraints"] if c["type"] == "displacement")
        assert pull["x"] == pytest.approx(0.04) and pull["y"] == 0 and pull["z"] == 0
        assert conditions["analysis"]["type"] == "static"
        assert point["measures"]["접합_넓이"] == pytest.approx(1000)
        assert point["measures"]["클램프_넓이"] == pytest.approx(800)
    # 받는 쪽은 `study.json` 의 factors 를 「바꾼 변수」 의 정본으로 읽는다(SimEngBay v0.2.0).
    spec = json.loads((folder / "study.json").read_text(encoding="utf-8"))
    declared = {one["name"]: one for one in spec["factors"]}
    assert set(declared) == {"접촉 종류", "마찰계수", "클램프"}
    assert declared["마찰계수"]["values"] == [0.15, 0.3, 0.6]
    header = (folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert {"접촉 종류", "마찰계수", "클램프", "접합_넓이"} <= set(header.split(","))

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / folder.name.rsplit("-", 1)[0]
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)


#: ⑧ **볼트 예압** — 알루미늄 판 두 장을 M8 강 볼트 하나로 체결한다(SimEngBay v0.20.0 이
#: CalculiX 로 예압을 걸게 되어 회귀 시험에 둘 폴더를 부탁했다, 2026-10-26). 볼트는 위판의 여유
#: 구멍(9)을 지나 아래판의 구멍(8)에 물린다 — 나사산은 그리지 않고 물린 자리를 본딩으로.
#: 판끼리 · 머리와 위판이 닿는 자리, 물린 자리를 새겨(`imprint`) 몸통이 「자유 몸통」(위판 안,
#: z 10 ~ 18)과 「물린 몸통」(아래판 안)으로 갈린다 — 예압은 자유 몸통의 원통면에 건다.
#:
#: 예압은 두 방식이고 단위(`unit`)가 가른다 — 힘 1000 N, 조임량 0.0025 mm. 그 뒤 위판을 600 N
#: 으로 끌어올린다: 「체결 → 길이 고정 → 다른 하중」 차례면 볼트 힘이 예압보다 조금 는다.
BOLT_PRETENSION: dict[str, Any] = {
    "name": "조건_볼트예압_정적",
    "method": "table",
    "recipe": {
        "params": {"예압": 1000.0},
        "nodes": [
            {"id": "아래판_원형", "op": "box", "length": 60, "width": 40, "height": 10,
             "align": ["center", "center", "min"]},
            {"id": "아래판", "op": "hole", "target": "아래판_원형", "at": [[0, 0]],
             "diameter": 8},
            {"id": "위판_원형", "op": "box", "length": 60, "width": 40, "height": 8,
             "at": [0, 0, 10], "align": ["center", "center", "min"]},
            {"id": "위판", "op": "hole", "target": "위판_원형", "at": [[0, 0]], "diameter": 9},
            # 머리가 위판 윗면(z 18)에 앉고 몸통 18 이 아래판 바닥까지 내려간다.
            {"id": "볼트", "op": "bolt", "at": [0, 0, 18], "nominal": 8, "length": 18,
             "head": "hex"},
            {"id": "조립", "op": "group", "targets": ["아래판", "위판", "볼트"]},
            {"id": "새김", "op": "imprint", "target": "조립"},
        ],
    },
    "factors": [
        {"name": "예압 방식", "mode": "choice",
         "target": {"group": "loads", "item": "볼트 예압", "field": "unit"},
         "values": ["N", "mm"]},
    ],
    # 표로 준다 — 방식마다 값의 뜻(힘 · 길이)이 달라 격자로 짜면 1000 mm 조임 같은 점이 생긴다.
    "table": [
        {"예압 방식": "N", "예압": 1000},
        {"예압 방식": "mm", "예압": 0.0025},
    ],
    "conditions": {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("바닥", {"body": "아래판", "normal": [0, 0, -1]}),
            # 위판 윗면 중 머리가 앉은 자리를 뺀 나머지(새김으로 갈렸다).
            _face("위판 윗면", {"body": "위판", "normal": [0, 0, 1], "near": [25, 0, 18]}),
            _face("자유 몸통", {"body": "볼트", "kind": "cylinder", "near": [4, 0, 14]}),
            _face("머리 밑", {"tag": "볼트/위판"}),
            _face("머리 자리", {"tag": "위판/볼트"}),
            _face("위판 밑", {"tag": "위판/아래판"}),
            _face("아래판 위", {"tag": "아래판/위판"}),
            _face("물린 몸통", {"tag": "볼트/아래판"}),
            _face("물린 구멍", {"tag": "아래판/볼트"}),
        ],
        "materials": [
            _material("M-000138", ["볼트"]),
            _material("M-000158", ["아래판", "위판"]),
        ],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "바닥"}],
        "loads": [
            {"name": "볼트 예압", "type": "bolt_pretension", "on": "자유 몸통",
             "preload": "=예압", "unit": "N"},
            {"name": "끌어올림", "type": "force", "on": "위판 윗면", "magnitude": 600,
             "direction": [0, 0, 1]},
        ],
        "contacts": [
            {"name": "머리-위판", "type": "bonded", "source": "머리 밑",
             "target": "머리 자리"},
            {"name": "판-판", "type": "frictional", "source": "위판 밑", "target": "아래판 위",
             "friction": 0.2},
            {"name": "나사 물림", "type": "bonded", "source": "물린 몸통",
             "target": "물린 구멍"},
        ],
        "mesh_hints": [
            {"on": "전체", "element_size": 2, "order": "quadratic"},
            {"on": "자유 몸통", "element_size": 1},
        ],
        # 1 단계 체결(예압) → 2 단계 길이 고정 + 끌어올림.
        "analysis": {"type": "static", "steps": 2},
    },
}  # fmt: skip

#: ⑧-1 같은 체결의 **선응력 모달** — 정적(예압 → 끌어올림)의 응력을 안고 고유진동을 구한다.
BOLT_PRESTRESSED: dict[str, Any] = {
    **BOLT_PRETENSION,
    "name": "조건_볼트예압_선응력모달",
    "conditions": {
        **BOLT_PRETENSION["conditions"],
        "initial": [{"type": "prestress"}],
        "analysis": {"type": "modal", "modes": 6, "prestressed": True},
    },
}


def test_볼트_예압_픽스처_힘과_조임량_정적과_선응력_모달(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    static = _export(client, member, export_root, BOLT_PRETENSION)
    modal = _export(client, member, export_root, BOLT_PRESTRESSED)
    for folder in (static, modal):
        points = _points(folder)
        assert [one["point"]["params"]["예압 방식"] for one in points] == ["N", "mm"]
        for point in points:
            assert point["unresolved"] == []
            regions = point["regions"]
            # 예압을 거는 자리 — 위판 안의 자유 몸통(2π · 4 · 8). 물린 몸통은 따로
            # (2π · 4 · 10).
            (shank,) = regions["자유 몸통"]
            assert (shank["body"], shank["area"]) == ("볼트", pytest.approx(201.06, abs=0.01))
            assert shank["centroid"] == [0.0, 0.0, 14.0]
            assert regions["물린 몸통"][0]["area"] == pytest.approx(251.33, abs=0.01)
            # 머리가 앉은 자리 — 육각 맞변 13 의 넓이 146.36 - 여유 구멍 63.62.
            assert regions["머리 밑"][0]["area"] == pytest.approx(82.74, abs=0.01)
            assert regions["위판 밑"][0]["area"] == regions["아래판 위"][0]["area"]
            loads = {one["name"]: one for one in point["conditions"]["loads"]}
            bolt = loads["볼트 예압"]
            kind = point["point"]["params"]["예압 방식"]
            assert (bolt["unit"], bolt["preload"]) == (
                (kind, 1000) if kind == "N" else (kind, pytest.approx(0.0025))
            )
        # 형상은 하나 — 두 점이 STEP 하나를 나눠 쓴다.
        assert len({one["point"]["step_file"] for one in points}) == 1
    assert _points(static)[0]["conditions"]["analysis"]["steps"] == 2
    readme = (static / "README.txt").read_text(encoding="utf-8")
    assert "  - 예압 방식: N, mm (조건 loads · 볼트 예압 · unit)" in readme
    analysis = _points(modal)[0]["conditions"]["analysis"]
    assert (analysis["type"], analysis["prestressed"]) == ("modal", True)
    assert _points(modal)[0]["conditions"]["initial"][0]["type"] == "prestress"
    for folder in (static, modal):
        _copy_fixture(folder)


def test_조건_픽스처를_실제_내보내기로_만든다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    two = _export(client, member, export_root, TWO_BODIES)
    hole = _export(client, member, export_root, HOLE_SI)
    sweep = _export(client, member, export_root, MATERIAL_SWEEP)
    combo = _export(client, member, export_root, CONDITION_SWEEP)

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
        # 접촉 · 구속 · 하중의 선택 그룹이 이 점에서 풀렸다 — **그룹마다 그 면 하나만.**
        assert point["unresolved"] == []
        assert point["conditions"]["analysis"]["type"] == "static"
        top = 5.0 if point["point"]["params"]["두께"] == 5 else 8.0
        assert {
            name: [(face["area"], face["centroid"][2]) for face in faces]
            for name, faces in point["regions"].items()
        } == {
            "바닥": [(6000.0, 0.0)],
            "블록 윗면": [(1600.0, top + 20)],
            "판 윗면": [(6000.0, top)],
            "블록 아랫면": [(1600.0, top)],
        }
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

    # ③ 재료만 바뀐다 — 형상 하나를 나눠 쓰고, 블록에 붙은 재료가 점마다 다르다.
    swept = _points(sweep)
    assert [one["point"]["params"]["블록 재료"] for one in swept] == [
        "AL5052H32DEMO_-_-",
        "SECC-EXAD87-DP_선언물성_0.8",
    ]
    assert swept[0]["point"]["step_file"] == swept[1]["point"]["step_file"]
    assert swept[0]["point"]["step_file"].startswith("shapes/")
    on_block = [
        [
            one["ref"]["code"]
            for one in point["conditions"]["materials"]
            if "블록" in one["apply_to"]
        ]
        for point in swept
    ]
    assert on_block == [["M-000158"], ["M-000138"]]
    # 받침판은 그대로 SECC — 한 바디에 재료 하나.
    for point in swept:
        plate = [
            one for one in point["conditions"]["materials"] if "받침판" in one["apply_to"]
        ]
        assert [one["ref"]["code"] for one in plate] == ["M-000138"]
    manifest = (sweep / "manifest.csv").read_text(encoding="utf-8-sig")
    assert "블록 재료" in manifest.splitlines()[0] and "AL5052H32DEMO_-_-" in manifest

    # ④ 조건 훑기 — 네 점이 한 형상을 나눠 쓰고, 접촉 종류 · 블록 탄성계수만 다르다.
    combos = _points(combo)
    assert len(combos) == 4 and len({one["point"]["step_file"] for one in combos}) == 1
    for point in combos:
        params = point["point"]["params"]
        conditions = point["conditions"]
        assert conditions["contacts"][0]["type"] == params["접촉 종류"]
        # 인자가 아닌 도면 변수(압력)와 정수 칸의 식(모드 수)도 풀린다.
        assert conditions["loads"][0]["magnitude"] == pytest.approx(1.5)
        assert conditions["analysis"]["modes"] == 10
        block = next(m for m in conditions["materials"] if "블록" in m["apply_to"])
        support = next(m for m in conditions["materials"] if "받침판" in m["apply_to"])
        youngs = next(
            r
            for r in block["converted"]["properties"]
            if r["key"] == "mechanical.youngs_modulus"
        )
        original = next(
            one for one in block["payload"]["declared_properties"] if one["item"] == "탄성계수"
        )["points"][0]["value_si"]
        # mm · N · t 로 옮긴 값(MPa)에 배율 — 원본(payload, Pa)은 그대로.
        assert youngs["points"][0]["value"] == pytest.approx(
            original / 1e6 * params["블록 탄성계수 배율"]
        )
        assert block["converted"]["scaled"] == {"탄성계수": params["블록 탄성계수 배율"]}
        assert "scaled" not in support["converted"]
        # 물성 사전이 있어 표준 열쇠가 붙고, 탄성계수를 「없다」 고 하지 않는다.
        assert "missing_structural" not in block["converted"]

    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        for folder in (two, hole, sweep, combo):
            # 폴더 이름의 끝(스터디 id 여덟 자리)은 돌릴 때마다 달라진다 — 이름만 남긴다.
            name = folder.name.rsplit("-", 1)[0]
            shutil.rmtree(target / name, ignore_errors=True)
            shutil.copytree(folder, target / name)


#: ⑦ **기준정보가 이어진 DOE** — 「조건_두바디_두재료」 를 작업으로 그려 부품으로 등록하고,
#: 그 부품의 「적용 모델」 에 기본 모델 「P5 플립」 을, 작업에 태그 둘(일반 태그 「본딩」 ·
#: 「시험 목적」 타입의 「강성 검토」)을 이었다. `study.json` 의 `ontology` 가 차는 모양을
#: 받는 쪽이 보게(온톨로지 이식 E 단계, 2026-10-26). 다른 픽스처는 대상 작업이 없어 빈 칸이다.
LINKED: dict[str, Any] = {**TWO_BODIES, "name": "기준정보_태그_적용모델"}


def test_기준정보_픽스처_태그와_적용_모델이_실린다(
    client: TestClient, member: Signed, admin: Signed, export_root: Path
) -> None:
    def ok(response: Any) -> Any:
        assert response.status_code in (200, 201, 202), response.text
        return response.json()

    # 관리자가 정의를 둔다 — 부품 원 표 타입은 태그의 기본 정의가 만든다.
    ok(client.get("/api/tags/types", headers=admin.headers))
    ok(
        client.post(
            "/api/ontology/types",
            json={"slug": "base_model", "label": "기본 모델", "key_policy": "optional"},
            headers=admin.headers,
        )
    )
    ok(
        client.post(
            "/api/ontology/relation-types",
            json={
                "slug": "model_parts",
                "label": "사용 부품",
                "inverse_label": "적용 모델",
                "src_type_slugs": ["base_model"],
                "dst_type_slugs": ["cc_part"],
            },
            headers=admin.headers,
        )
    )
    phone = ok(
        client.post(
            "/api/objects/base_model",
            json={"label": "P5 플립", "key": "SM-P500"},
            headers=admin.headers,
        )
    )
    ok(
        client.post(
            "/api/ontology/types",
            json={"slug": "test_purpose", "label": "시험 목적", "kind_class": "reference"},
            headers=admin.headers,
        )
    )
    grow = {"mode": "grow"}
    ok(client.put("/api/tags/settings/test_purpose", json=grow, headers=admin.headers))

    # 사람이 작업을 그려 부품으로 등록하고, 태그 · 적용 모델을 잇는다.
    work = ok(
        client.post(
            "/api/works",
            json={"name": "두바디 본딩 조립", "kind": "part", "recipe": TWO_BODIES["recipe"]},
            headers=member.headers,
        )
    )
    part = ok(
        client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=member.headers)
    )["part_id"]
    ok(
        client.post(
            f"/api/parts/{part}/ontology/links",
            json={"relation": "model_parts", "object_id": phone["id"]},
            headers=member.headers,
        )
    )
    tagged = f"/api/tags/work/{work['id']}"
    ok(client.post(tagged, json={"label": "본딩"}, headers=member.headers))
    purpose = {"type_slug": "test_purpose", "label": "강성 검토"}
    ok(client.post(tagged, json=purpose, headers=member.headers))

    folder = _export(client, member, export_root, {**LINKED, "work_id": work["id"]})
    written = json.loads((folder / "study.json").read_text(encoding="utf-8"))["ontology"]
    tags = [(one["label"], one["type_slug"], one["type_label"]) for one in written["tags"]]
    assert tags == [
        ("본딩", "cc_tag", "일반 태그"),
        ("강성 검토", "test_purpose", "시험 목적"),
    ]
    [link] = written["links"]
    assert link["on"] == {"kind": "part", "id": part, "name": "두바디 본딩 조립"}
    assert (link["relation"], link["relation_label"]) == ("model_parts", "적용 모델")
    assert (link["label"], link["key"]) == ("P5 플립", "SM-P500")
    assert link["type_slug"] == "base_model"
    readme = (folder / "README.txt").read_text(encoding="utf-8")
    assert "  - 태그: 강성 검토 (시험 목적)" in readme
    assert "  - 두바디 본딩 조립 — 적용 모델: P5 플립 [SM-P500]" in readme
    # 형상 · 조건은 「조건_두바디_두재료」 와 같다 — 기준정보만 더 실렸다.
    assert [len(point["bodies"]) for point in _points(folder)] == [2, 2]
    _copy_fixture(folder)


def test_DOE_는_조건을_안_주면_작업의_현재_조건을_싣는다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """화면 · MCP 가 조건을 따로 실어 보내지 않아 DOE 폴더에 조건이 빠지고 있었다."""
    work = client.post(
        "/api/works",
        json={"name": "조건 따라가기", "recipe": TWO_BODIES["recipe"]},
        headers=member.headers,
    ).json()
    saved = client.put(
        f"/api/works/{work['id']}/versions/1/conditions",
        json={"conditions": TWO_BODIES["conditions"]},
        headers=member.headers,
    )
    assert saved.status_code == 200, saved.text
    study = {
        "name": "조건 따라가기",
        "recipe": TWO_BODIES["recipe"],
        "factors": TWO_BODIES["factors"],
        "work_id": work["id"],
    }
    made = client.post("/api/doe", json=study, headers=member.headers)
    assert made.status_code == 201, made.text
    assert made.json()["conditions"]["contacts"][0]["name"] == "블록-판"
    # 재료 인자도 작업의 조건에서 후보를 찾는다.
    swept = client.post(
        "/api/doe",
        json={**study, "name": "작업 재료 훑기", "factors": MATERIAL_SWEEP["factors"]},
        headers=member.headers,
    )
    assert swept.status_code == 201, swept.text
    # 빈 한 벌을 주면 형상만 훑는다.
    bare = client.post(
        "/api/doe", json={**study, "name": "형상만", "conditions": {}}, headers=member.headers
    )
    assert bare.status_code == 201 and bare.json()["conditions"] == {}


def test_재료_인자는_조건에_담긴_재료와_도면의_바디만_받는다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    def create(factor: dict[str, Any], conditions: dict[str, Any] | None = None) -> Any:
        body = {
            **MATERIAL_SWEEP,
            "factors": [factor],
            "conditions": TWO_BODIES["conditions"] if conditions is None else conditions,
        }
        return client.post("/api/doe", json=body, headers=member.headers)

    base = MATERIAL_SWEEP["factors"][0]
    bad = create({**base, "values": ["없는재료"]})
    assert bad.status_code >= 400 and "조건에 없습니다" in bad.text
    bad = create({**base, "bodies": ["다리"]})
    assert bad.status_code >= 400 and "도면에 없는 바디" in bad.text
    bad = create(base, conditions={})
    assert bad.status_code >= 400 and "조건에 재료가 없습니다" in bad.text


def test_남의_작업의_조건은_DOE_로_가져오지_못한다(
    client: TestClient, member: Signed, db: Session, export_root: Path
) -> None:
    """조건에는 그 사람의 물성 · 하중이 들어 있다 — 작업 id 만 알면 가져가게 두지 않는다."""
    from tests.api.conftest import _login, make_user

    work = client.post(
        "/api/works",
        json={"name": "내 것", "recipe": TWO_BODIES["recipe"]},
        headers=member.headers,
    ).json()
    other = make_user(db, label="other", is_system_admin=False)
    headers = {"Authorization": f"Bearer {_login(client, other.email)}"}
    got = client.post(
        "/api/doe",
        json={
            "name": "남의 조건",
            "recipe": TWO_BODIES["recipe"],
            "factors": TWO_BODIES["factors"],
            "work_id": work["id"],
        },
        headers=headers,
    )
    assert got.status_code == 403, got.text


def test_고르기_배율_인자가_틀리면_만들기_전에_말한다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    def create(factor: dict[str, Any]) -> Any:
        body = {**CONDITION_SWEEP, "name": "틀린 인자", "factors": [factor]}
        return client.post("/api/doe", json=body, headers=member.headers)

    choice = CONDITION_SWEEP["factors"][0]
    bad = create({**choice, "target": {**choice["target"], "item": "없는접촉"}})
    assert bad.status_code >= 400 and "없는접촉" in bad.text
    bad = create({**choice, "values": ["bonded", "sticky"]})
    assert bad.status_code >= 400 and "sticky" in bad.text
    scale = CONDITION_SWEEP["factors"][1]
    bad = create({**scale, "property": "없는물성"})
    assert bad.status_code >= 400 and "없는물성" in bad.text
    # 조건의 식이 도면에 없는 이름을 부르면 설계점을 만들기 전에 말한다.
    broken = {
        **CONDITION_SWEEP,
        "name": "모르는 이름",
        "conditions": {
            **CONDITION_SWEEP["conditions"],
            "loads": [{**CONDITION_SWEEP["conditions"]["loads"][0], "magnitude": "=없는것"}],
        },
    }
    bad = client.post("/api/doe", json=broken, headers=member.headers)
    assert bad.status_code >= 400 and "없는것" in bad.text


def test_재료를_훑는_바디의_배율은_후보마다_그_물성이_있어야_한다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """SECC(선언 물성)에는 항복강도가 없다 — 그 후보에서 배율이 조용히 빠지지 않게 막는다."""
    body = {
        **MATERIAL_SWEEP,
        "name": "항복강도 배율",
        "factors": [
            *MATERIAL_SWEEP["factors"],
            {
                "name": "항복강도 배율",
                "mode": "scale",
                "bodies": ["블록"],
                "property": "항복강도",
                "values": [0.9, 1.1],
            },
        ],
    }
    got = client.post("/api/doe", json=body, headers=member.headers)
    assert got.status_code >= 400, got.text
    assert "SECC" in got.text and "항복강도" in got.text
    # 둘 다 가진 물성(탄성계수)이면 된다.
    body["factors"][1] = {**body["factors"][1], "property": "탄성계수"}
    assert client.post("/api/doe", json=body, headers=member.headers).status_code == 201


# --- 셸 모델(시트 바디) — SimEngBay 의 부탁, 2026-10-15 ---------------------------------
#
# 두께 없는 시트 STEP 을 **올려서**(사람이 하는 그대로) 그 작업을 「설계 하나」 로 내보낸다.
# 받는 쪽은 본 형상(pNNNN.step)의 시트를 넓이 · 무게중심으로 찾아 빼고 중간면(_mid.step)의
# 셸로 짓는다 — gmsh · Mechanical 이 본 형상의 시트를 실제로 어떻게 읽는지 이 셋으로 본다.
# 매처가 아직 면 · 점만 알아(모서리는 모른다) 고정 · 하중은 모두 **면**에 건다.

#: 시트 판 — 폭 20(y 0 ~ 20), 높이 z, 면을 x 에서 나눈다(이음 엣지를 함께 쓰게 꿰맨다).
SHEET_WIDTH = 20.0
SHEET_THICKNESS = 1.2
SHEET_PRESSURE = 0.001  # MPa — 처짐이 L 의 0.3 % 로 선형에 머문다


def _sheet(cuts: list[float], z: float = 0.0) -> Any:
    from itertools import pairwise

    from build123d import Face, Shell, Wire

    faces = [
        Face(
            Wire.make_polygon(
                [(x0, 0, z), (x1, 0, z), (x1, SHEET_WIDTH, z), (x0, SHEET_WIDTH, z)],
                close=True,
            )
        )
        for x0, x1 in pairwise(cuts)
    ]
    return Shell(faces)


def _upload(client: TestClient, member: Signed, tmp_path: Path, shape: Any, name: str) -> Any:
    """STEP 으로 쓰고 「STEP 에서 시작」 으로 올린다 — 그 작업의 레시피(`import_step`)를
    돌려준다. 조립의 구성품 이름은 STEP 의 이름 그대로라 ASCII 로 붙인다(한글은 STEP 에서
    깨진다)."""
    from build123d import export_step

    path = tmp_path / f"{name}.step"
    assert export_step(shape, str(path))
    with path.open("rb") as stream:
        got = client.post(
            "/api/works/from-step",
            files={"file": (path.name, stream, "application/step")},
            headers=member.headers,
        )
    assert got.status_code == 201, got.text
    work = got.json()
    assert work["current"]["job"]["status"] == "done", work["current"]["job"]["error"]
    return work["current"]["recipe"]


def _sheet_conditions(thickness: float | None) -> dict[str, Any]:
    shell: dict[str, Any] = {
        "name": "전체",
        "representation": "shell",
        "mesh": {"element_size": 2},
    }
    if thickness is not None:
        shell["thickness"] = thickness
    return {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("물림 띠", {"near": [5, 10, 0]}),
            _face("하중면", {"near": [55, 10, 0]}),
        ],
        "materials": [_material("M-000138", ["전체"])],
        "constraints": [{"name": "물림", "type": "fixed_support", "on": "물림 띠"}],
        "loads": [{"name": "누름", "type": "pressure", "on": "하중면",
                   "magnitude": SHEET_PRESSURE, "direction": "normal"}],
        "body_settings": [shell],
        "analysis": {"type": "static"},
    }  # fmt: skip


def _copy_fixture(folder: Path) -> None:
    out = os.environ.get("COMPCORE_FIXTURE_OUT")
    if out:
        target = Path(out) / folder.name.rsplit("-", 1)[0]
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)


def test_셸모델_시트_외팔보_픽스처(
    client: TestClient, member: Signed, export_root: Path, tmp_path: Path
) -> None:
    """⑧ 시트 하나(100 x 20)를 물림 띠(x 0 ~ 10)와 나머지(x 10 ~ 100)로. 띠를 고정하고 나머지에
    압력 — 손셈은 README(외팔보 L 90 · qL⁴/8EI)."""
    recipe = _upload(client, member, tmp_path, _sheet([0, 10, 100]), "sheet_cantilever")
    study = {"name": "셸모델_시트외팔보", "recipe": recipe, "factors": [],
             "conditions": _sheet_conditions(SHEET_THICKNESS)}  # fmt: skip
    folder = _export(client, member, export_root, study)
    (point,) = _points(folder)
    assert point["unresolved"] == []
    (body,) = point["bodies"]
    assert body["name"] == "전체" and body["kind"] == "sheet" and body["volume"] == 0
    assert body["area"] == pytest.approx(100 * SHEET_WIDTH)
    mid = point["midsurface"]
    (shell,) = mid["bodies"]
    assert shell["source"] == "sheet" and shell["thickness"] == SHEET_THICKNESS
    assert shell["area"] == pytest.approx(100 * SHEET_WIDTH) and "failed" not in mid
    assert (folder / mid["step_file"]).exists()
    # 영역 — 면 그대로가 중간면의 면이다(겉면 → t/2 안쪽이 아니다).
    strip, load = _only(point["regions"], "물림 띠"), _only(point["regions"], "하중면")
    assert strip["area"] == pytest.approx(10 * SHEET_WIDTH)
    assert load["area"] == pytest.approx(90 * SHEET_WIDTH)
    (mid_load,) = load["mid"]
    assert mid_load["face"]["area"] == pytest.approx(load["area"])
    assert mid_load["face"]["normal"] == [0.0, 0.0, 1.0]
    settings = point["conditions"]["body_settings"][0]
    assert settings["thickness"] == SHEET_THICKNESS
    _copy_fixture(folder)


def test_셸모델_시트_받침_조립_픽스처(
    client: TestClient, member: Signed, export_root: Path, tmp_path: Path
) -> None:
    """⑨ 솔리드 받침(20 x 20 x 10) 윗면에 시트(z 10, 접착 띠 x 0 ~ 20 · 나머지 x 20 ~ 100)를
    본딩. 받침 바닥 고정, 나머지 면에 압력. 솔리드는 부피로, 시트는 넓이로 짝지어지는지
    본다."""
    from build123d import Box, Compound, Pos

    base = Pos(10, 10, 5) * Box(20, 20, 10)
    base.label = "base"
    skin = _sheet([0, 20, 100], z=10)
    skin.label = "skin"
    assembly = Compound(children=[base, skin])
    recipe = _upload(client, member, tmp_path, assembly, "sheet_on_base")
    conditions = {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("받침 바닥", {"body": "base", "normal": [0, 0, -1]}),
            _face("받침 윗면", {"body": "base", "normal": [0, 0, 1]}),
            _face("접착 띠", {"body": "skin", "near": [10, 10, 10]}),
            _face("하중면", {"body": "skin", "near": [60, 10, 10]}),
        ],
        "materials": [_material("M-000138", ["base", "skin"])],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "받침 바닥"}],
        "loads": [{"name": "누름", "type": "pressure", "on": "하중면",
                   "magnitude": SHEET_PRESSURE, "direction": "normal"}],
        "contacts": [{"name": "시트 접착", "type": "bonded", "source": "접착 띠",
                      "target": "받침 윗면"}],
        "body_settings": [
            {"name": "skin", "representation": "shell", "thickness": SHEET_THICKNESS,
             "mesh": {"element_size": 2}},
            {"name": "base", "mesh": {"element_size": 4}},
        ],
        "analysis": {"type": "static"},
    }  # fmt: skip
    study = {"name": "셸모델_시트받침조립", "recipe": recipe, "factors": [],
             "conditions": conditions}  # fmt: skip
    folder = _export(client, member, export_root, study)
    (point,) = _points(folder)
    assert point["unresolved"] == []
    bodies = {one["name"]: one for one in point["bodies"]}
    assert bodies["base"]["kind"] == "solid"
    assert bodies["base"]["volume"] == pytest.approx(4000)
    assert bodies["skin"]["kind"] == "sheet" and bodies["skin"]["volume"] == 0
    assert bodies["skin"]["area"] == pytest.approx(100 * SHEET_WIDTH)
    # 넓이 무게중심 — 중간면 요약과 같은 자리라야 받는 쪽이 짝짓는다(엣지 길이로 재면 45.714).
    assert bodies["skin"]["centroid"] == [50.0, 10.0, 10.0]
    mid = point["midsurface"]
    # 중간면은 시트만 — 받침은 솔리드라 쉘로 고르지 않았다.
    assert [(one["name"], one["source"]) for one in mid["bodies"]] == [("skin", "sheet")]
    assert mid["bodies"][0]["step_product"] == bodies["skin"]["step_product"]
    assert mid["bodies"][0]["centroid"] == bodies["skin"]["centroid"]
    regions = point["regions"]
    assert _only(regions, "접착 띠")["body"] == "skin"
    assert _only(regions, "받침 윗면")["body"] == "base"
    assert _only(regions, "하중면")["area"] == pytest.approx(80 * SHEET_WIDTH)
    assert "mid" not in _only(regions, "받침 바닥")  # 솔리드 파트에는 붙지 않는다
    _copy_fixture(folder)


def test_셸모델_두께_없는_시트_픽스처(
    client: TestClient, member: Signed, export_root: Path, tmp_path: Path
) -> None:
    """⑩ ⑧ 에서 두께만 뺐다 — 중간면을 지을 수 없다는 것이 `midsurface.failed` 로 나간다(받는
    쪽은 그 점을 실패로 보고한다)."""
    recipe = _upload(client, member, tmp_path, _sheet([0, 10, 100]), "sheet_no_thickness")
    study = {"name": "셸모델_두께없음", "recipe": recipe, "factors": [],
             "conditions": _sheet_conditions(None)}  # fmt: skip
    folder = _export(client, member, export_root, study)
    (point,) = _points(folder)
    mid = point["midsurface"]
    assert "step_file" not in mid and "bodies" not in mid
    (failed,) = mid["failed"]
    assert failed["name"] == "전체" and "두께" in failed["error"]
    assert point["conditions"]["body_settings"][0]["thickness"] is None
    _copy_fixture(folder)
