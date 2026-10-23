"""설계점 파일에 **전역 요소 크기 제안**이 실리나 — 사람이 메시를 안 정했어도 받는 쪽이 같은
규칙의 값을 쓰게(2026-10-23, 규칙은 `core/mesh_suggestion.py`)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

PLATE = {"nodes": [{"id": "판", "op": "box", "length": 40, "width": 30, "height": 2}]}


@pytest.fixture
def export_root(tmp_path: Path) -> Iterator[Path]:
    """공유 폴더는 시험에서 임시 폴더로(`test_doe.py` 와 같다)."""
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _point(client: TestClient, who: Signed, root: Path, conditions: dict[str, Any]) -> Any:
    made = client.post(
        "/api/doe",
        json={"name": "판 메시", "recipe": PLATE, "conditions": conditions},
        headers=who.headers,
    )
    assert made.status_code == 201, made.text
    sent = client.post(f"/api/doe/{made.json()['id']}/export", headers=who.headers)
    assert sent.status_code == 200, sent.text
    folder = next(one for one in root.iterdir() if one.name.startswith("판"))
    return json.loads((folder / "points" / "p0001.json").read_text("utf-8"))


def test_메시를_안_정해도_전역_크기_제안이_실린다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    point = _point(client, member, export_root, {"units": {"system": "si"}})
    suggestion = point["mesh_suggestion"]
    # 판 40 x 30 x 2 — 최소 벽 2 의 절반이 1(가장 긴 변 40 의 1/20 = 2 보다 작다).
    assert suggestion["element_size"] == 1.0
    assert suggestion["in_conditions"] is False
    assert "최소 벽 두께" in suggestion["basis"]
    # SI 로 내보내도 제안은 도면의 mm 다 — 단위를 함께 말한다.
    assert point["length_units"]["mesh_suggestion"] == "mm"
    assert point["conditions"]["units"]["system"] == "si"


def test_사람이_전체_크기를_정했으면_그렇다고_적는다(
    client: TestClient, member: Signed, export_root: Path
) -> None:
    """받는 쪽은 사람이 정한 값을 쓴다 — 제안값은 참고로 남는다."""
    point = _point(
        client, member, export_root, {"mesh_hints": [{"on": "전체", "element_size": 3}]}
    )
    assert point["mesh_suggestion"]["in_conditions"] is True
    assert point["mesh_suggestion"]["element_size"] == 1.0
    hints = point["conditions"]["mesh_hints"]
    assert any(one["on"] == "전체" and one["element_size"] == 3 for one in hints)
