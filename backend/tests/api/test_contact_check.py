"""부품 셋 → 조립 → 접촉 점검 → 내보내기 — 화면이 밟는 길 그대로(2026-11-16).

CalculiX 로 끝까지 풀어 보니(SimEngBay v0.26.1) 받침-덮개 접촉을 빠뜨린 조립에서 덮개가 떠 모드
여섯이 모두 0 Hz 였고, 어느 쪽도 말하지 않았다. 조건 화면은 그것을 미리 말하고 본딩으로 채울
것을 주며, 내보내기는 점 파일 · 표에 적는다.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import Signed
from tests.api.test_fixture_export import (  # noqa: F401
    _export,
    _material,
    export_root,
    property_keys,
)


def _box(length: float, width: float, height: float) -> dict[str, Any]:
    node = {"id": "몸", "op": "box", "length": length, "width": width, "height": height}
    return {"nodes": [{**node, "align": ["center", "center", "min"]}]}


def _work(
    client: TestClient, member: Signed, name: str, recipe: dict[str, Any], kind: str
) -> str:
    made = client.post(
        "/api/works",
        json={"name": name, "recipe": recipe, "kind": kind},
        headers=member.headers,
    )
    assert made.status_code in (200, 201), made.text
    return str(made.json()["id"])


def _face(name: str, body: str, z: int) -> dict[str, Any]:
    select = {"what": "faces", "body": body, "kind": "plane", "normal": [0, 0, z]}
    return {"name": name, "entity": "face", "select": select}


def test_조립에서_빠뜨린_접촉을_말하고_채우면_내보내기에서도_사라진다(
    client: TestClient,
    member: Signed,
    export_root: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = _work(client, member, "판", _box(60, 40, 3), "part")
    bracket = _work(client, member, "받침", _box(20, 20, 10), "part")
    cover = _work(client, member, "덮개", _box(30, 20, 2), "part")
    recipe = {
        "nodes": [
            {"id": "판", "op": "component", "source": f"work:{base}"},
            {
                "id": "받침",
                "op": "component",
                "source": f"work:{bracket}",
                "translate": [0, 0, 3],
            },
            {
                "id": "덮개",
                "op": "component",
                "source": f"work:{cover}",
                "translate": [0, 0, 13],
            },
            {"id": "조립", "op": "group", "targets": ["판", "받침", "덮개"]},
        ]
    }
    assembly = _work(client, member, "ASSY", recipe, "assembly")
    conditions: dict[str, Any] = {
        "units": {"system": "mm_n_tonne"},
        "named_selections": [
            _face("판 바닥", "판", -1),
            _face("판 윗면", "판", 1),
            _face("받침 아랫면", "받침", -1),
        ],
        "materials": [_material("M-000138", ["판", "받침", "덮개"])],
        "constraints": [{"name": "바닥 고정", "type": "fixed_support", "on": "판 바닥"}],
        "contacts": [
            {"name": "판-받침", "type": "bonded", "source": "받침 아랫면", "target": "판 윗면"}
        ],
        "mesh_hints": [{"on": "전체", "element_size": 2, "order": "quadratic"}],
        "analysis": {"type": "modal", "modes": 6},
    }

    # 조건 화면 — 받침-덮개가 맞닿았는데 접촉이 없다고, 자리와 함께.
    got = client.post(
        "/api/cad/conditions/contacts",
        json={"recipe": recipe, "conditions": conditions},
        headers=member.headers,
    )
    assert got.status_code == 200, got.text
    report = got.json()
    assert [(one["a"], one["b"]) for one in report["missing"]] == [("받침", "덮개")]
    assert any(one["level"] == "warn" for one in report["notes"])

    # 그대로 내보내면 점 파일 · 표가 같은 것을 적는다.
    folder = _export(
        client,
        member,
        export_root,
        {
            "name": "조립_접촉빠짐",
            "recipe": recipe,
            "factors": [],
            "work_id": assembly,
            "conditions": conditions,
        },
    )
    point = json.loads(next((folder / "points").glob("p*.json")).read_text(encoding="utf-8"))
    assert [(one["a"], one["b"]) for one in point["quality"]["touching"]] == [
        ("판", "받침"),
        ("받침", "덮개"),
    ]
    assert any(
        "접촉 미정의: 인접 바디 ‘받침’ · ‘덮개’" in one for one in point["quality"]["warnings"]
    )
    with (folder / "manifest.csv").open(encoding="utf-8-sig") as handle:
        (row,) = list(csv.DictReader(handle))
    assert "접촉 미정의" in row["warnings"]

    # 「맞닿은 면으로 본딩 채우기」 — 제안을 그대로 담으면 빠진 쌍도 경고도 없다.
    filled = {
        **conditions,
        "named_selections": conditions["named_selections"]
        + report["proposal"]["named_selections"],
        "contacts": conditions["contacts"] + report["proposal"]["contacts"],
    }
    saved = client.put(
        f"/api/works/{assembly}/versions/1/conditions",
        json={"conditions": filled},
        headers=member.headers,
    )
    assert saved.status_code == 200, saved.text
    again = client.post(
        "/api/cad/conditions/contacts",
        json={"recipe": recipe, "conditions": filled},
        headers=member.headers,
    ).json()
    assert again["missing"] == []
    folder = _export(
        client,
        member,
        export_root,
        {"name": "조립_접촉채움", "recipe": recipe, "factors": [], "work_id": assembly},
    )
    point = json.loads(next((folder / "points").glob("p*.json")).read_text(encoding="utf-8"))
    assert not any("접촉 미정의" in one for one in point["quality"]["warnings"])
    assert {one["name"] for one in point["conditions"]["contacts"]} == {
        "판-받침",
        "본딩 받침-덮개",
    }

    # 걸었는데 두 면이 안 맞닿은 본딩 — 그룹이 딴 면을 가리킨다(접촉 자동 찾기가 중심으로 지은
    # 규칙이 그랬다, 2026-11-26). 화면도 내보내기도 말한다.
    wrong = {
        **filled,
        "contacts": [
            *filled["contacts"],
            {
                "name": "판바닥-받침",
                "type": "bonded",
                "source": "받침 아랫면",
                "target": "판 바닥",
            },
        ],
    }
    notes = client.post(
        "/api/cad/conditions/contacts",
        json={"recipe": recipe, "conditions": wrong},
        headers=member.headers,
    ).json()["notes"]
    assert [(one["where"], one["level"]) for one in notes if "맞닿아" in one["text"]] == [
        ("접촉 ‘판바닥-받침’", "warn")
    ]
    folder = _export(
        client,
        member,
        export_root,
        {
            "name": "조립_접촉어긋남",
            "recipe": recipe,
            "factors": [],
            "work_id": assembly,
            "conditions": wrong,
        },
    )
    point = json.loads(next((folder / "points").glob("p*.json")).read_text(encoding="utf-8"))
    assert point["quality"]["misplaced_contacts"] == [
        {
            "name": "판바닥-받침",
            "type": "bonded",
            "source": "받침 아랫면",
            "target": "판 바닥",
            "problem": "apart",
        }
    ]
    assert [one for one in point["quality"]["warnings"] if "맞닿아" in one] == [
        "접촉 ‘판바닥-받침’: 접촉면 ‘받침 아랫면’ 과 대상면 ‘판 바닥’ 이 "
        "맞닿아 있지 않습니다. 선택 그룹이 다른 면을 가리키는지 확인하십시오."
    ]

    # 만들기 전의 「끝 점 미리 만들어 보기」 도 같은 판정을 점마다 말한다 — 만든 뒤에야 점의
    # 경고로 보이던 것(2026-11-26).
    probed = client.post(
        "/api/doe/probe",
        json={"recipe": recipe, "factors": [], "conditions": wrong},
        headers=member.headers,
    )
    assert probed.status_code == 200, probed.text
    (centre,) = [one for one in probed.json()["points"] if one["status"] == "ok"]
    assert [one for one in centre["warnings"] if "맞닿아" in one] == [
        "접촉 ‘판바닥-받침’: 접촉면 ‘받침 아랫면’ 과 대상면 ‘판 바닥’ 이 "
        "맞닿아 있지 않습니다. 선택 그룹이 다른 면을 가리키는지 확인하십시오."
    ]

    # 운영에서 한 번 훑는 점검(`scripts/check_contacts.py`)도 **저장된** 조건에서 같은 것을
    # 찾는다.
    saved = client.put(
        f"/api/works/{assembly}/versions/1/conditions",
        json={"conditions": wrong},
        headers=member.headers,
    )
    assert saved.status_code == 200, saved.text
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_contacts.py"
    spec = importlib.util.spec_from_file_location("check_contacts_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["check_contacts.py"])
    capsys.readouterr()
    assert module.main() == 1
    out = capsys.readouterr().out
    assert f"작업 ‘ASSY’ v1 ({assembly}) · 접촉 ‘판바닥-받침’(bonded) 맞닿지 않음" in out
    assert "접촉 ‘판-받침’" not in out
    # DOE 는 스냅샷이다 — 틀린 조건으로 만든 스터디가 만든 날과 함께 나온다. `--doe` 는 그것만.
    assert "DOE ‘조립_접촉어긋남’ (" in out and ", 만듦 20" in out
    monkeypatch.setattr(sys, "argv", ["check_contacts.py", "--doe"])
    assert module.main() == 1
    only = capsys.readouterr().out
    assert "DOE ‘조립_접촉어긋남’ (" in only
    assert "작업 ‘ASSY’" not in only and "DOE ‘조립_접촉채움’" not in only
