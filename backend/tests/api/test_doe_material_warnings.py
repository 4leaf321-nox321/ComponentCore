"""탄성계수가 빠진 재료는 **내보낸 표에도** 경고가 남는다(2026-11-17).

고를 때 한 번 말하고 그 뒤에는 조용했다 — 받는 쪽은 재료를 거절하거나 기본값(구조용 강)으로
풀고, 그것은 고유진동수가 틀린 뒤에야 드러난다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.recipe.templates import TEMPLATES
from tests.api.conftest import Signed
from tests.api.test_fixture_export import export_root, property_keys  # noqa: F401


def _conditions(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "materials": [
            {
                "apply_to": ["전체"],
                "ref": {"source": "matnexus", "name": "맨재료"},
                "payload": payload,
            }
        ],
        "named_selections": [
            {"name": "바닥", "entity": "face", "select": {"what": "faces", "role": "bottom"}}
        ],
        "constraints": [{"name": "고정", "type": "fixed_support", "on": "바닥"}],
        "analysis": {"type": "modal", "modes": 6},
    }


def test_탄성계수가_빠진_재료는_manifest_경고에_적힌다(
    client: TestClient,
    member: Signed,
    export_root: Path,  # noqa: F811
) -> None:
    bare = {
        "density": 2700.0,
        "density_unit": "kg/m3",
        "poisson_ratio": 0.33,
        "declared_properties": [],
    }
    study = client.post(
        "/api/doe",
        json={
            "name": "맨재료_모달",
            "recipe": TEMPLATES["plate_with_holes"](),
            "conditions": _conditions(bare),
            "factors": [],
        },
        headers=member.headers,
    )
    assert study.status_code == 201, study.text
    done = client.post(f"/api/doe/{study.json()['id']}/export", headers=member.headers)
    assert done.status_code in (200, 201, 202), done.text
    folder = next(one for one in export_root.iterdir() if one.name.startswith("맨재료_모달"))
    manifest = (folder / "manifest.csv").read_text(encoding="utf-8-sig").splitlines()
    header = manifest[0].split(",")
    row = dict(zip(header, manifest[1].split(","), strict=False))
    assert "재료 ‘맨재료’: 탄성계수 없음 — 구조 해석에 필요합니다" in row["warnings"]
    point = json.loads((folder / "points" / "p0001.json").read_text(encoding="utf-8"))
    (material,) = point["conditions"]["materials"]
    assert material["converted"]["missing_structural"] == ["탄성계수"]
