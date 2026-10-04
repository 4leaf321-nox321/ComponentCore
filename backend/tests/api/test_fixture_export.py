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
        ],
        "materials": [
            _material("M-000138", ["지그블록", "브래킷"]),
            # 해석에서 뺀 파트에도 물성은 붙어 있을 수 있다 — 받는 쪽은 그냥 버린다.
            _material("M-000158", ["명판"]),
        ],
        "constraints": [
            # 강체는 면에 고정 지지를 못 건다(Mechanical) — 원격 변위로 여섯 성분을 묶는다.
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
        # 쉘의 재료 — 브래킷의 중간면과 두께.
        mid = point["midsurface"]
        bracket = next(one for one in mid["bodies"] if one["name"] == "브래킷")
        assert bracket["thickness"] == pytest.approx(thick)
        assert (folder / mid["step_file"]).exists()
        regions = point["regions"]
        load = _only(regions, "하중면")
        assert load["body"] == "브래킷" and load["normal"] == [1.0, 0.0, 0.0]
        # 바깥면의 곧은 자리 — 꺾은선(x 50)이 R4 로 돌아 z 24 부터 70 까지, 폭 30.
        assert load["area"] == pytest.approx(30 * (70 - 24))
        assert _only(regions, "브래킷 바닥")["body"] == "브래킷"
        assert _only(regions, "블록 바닥")["area"] == pytest.approx(3200)

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
