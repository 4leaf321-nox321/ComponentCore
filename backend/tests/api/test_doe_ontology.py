"""기준정보를 CompCore 기능이 쓴다(온톨로지 이식 E 단계, 2026-10-26) — 부품 · 지그 목록을
기준정보로 거르고, DOE 폴더가 이은 객체(태그 · 적용 모델 …)의 키와 이름을 싣는다.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.conftest import Signed

BOX = {
    "params": {"두께": 10.0},
    "nodes": [{"id": "b", "op": "box", "length": 40, "width": 30, "height": "=두께"}],
}


@pytest.fixture
def export_root(tmp_path: Path) -> Iterator[Path]:
    settings = get_settings()
    before = settings.doe_export_root
    settings.doe_export_root = tmp_path / "공유"
    yield settings.doe_export_root
    settings.doe_export_root = before


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201, 202), response.text
    return response.json()


def _uniq(base: str) -> str:
    return f"{base}_{uuid.uuid4().hex[:6]}"


def _model_and_relation(client: TestClient, admin: Signed) -> tuple[str, str, str]:
    """기본 모델 타입 · 「기본 모델 → 부품」 관계 · 모델 객체 하나. 부품 원 표 타입은 태그의
    기본 정의가 만든다(`/api/tags/types`)."""
    _ok(client.get("/api/tags/types", headers=admin.headers))
    model = _uniq("model")
    _ok(
        client.post(
            "/api/ontology/types",
            json={"slug": model, "label": "기본 모델", "key_policy": "optional"},
            headers=admin.headers,
        )
    )
    relation = _uniq("uses")[:32]
    _ok(
        client.post(
            "/api/ontology/relation-types",
            json={
                "slug": relation,
                "label": "사용 부품",
                "inverse_label": "적용 모델",
                "src_type_slugs": [model],
                "dst_type_slugs": ["cc_part"],
            },
            headers=admin.headers,
        )
    )
    phone = _ok(
        client.post(
            f"/api/objects/{model}",
            json={"label": "P5 플립", "key": _uniq("SM-P500")},
            headers=admin.headers,
        )
    )
    return model, relation, phone["id"]


def _folder(root: Path, study_id: str) -> Path:
    """내보낸 폴더 — 이름이 아니라 `study.json` 의 id 로 찾는다."""
    for one in root.iterdir():
        found = one / "study.json"
        if found.exists() and json.loads(found.read_text(encoding="utf-8"))["id"] == study_id:
            return one
    raise AssertionError(f"{study_id} 의 폴더가 없다")


def _part(client: TestClient, who: Signed, name: str) -> tuple[str, str]:
    work = _ok(
        client.post(
            "/api/works",
            json={"name": name, "kind": "part", "recipe": BOX},
            headers=who.headers,
        )
    )
    promoted = _ok(
        client.post(f"/api/works/{work['id']}/promote/part", json={}, headers=who.headers)
    )
    return work["id"], promoted["part_id"]


def test_부품_목록을_기준정보로_거른다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    _model, relation, phone = _model_and_relation(client, admin)
    _work, linked = _part(client, member, "적용된 판")
    _other_work, other = _part(client, member, "안 이은 판")
    _ok(
        client.post(
            f"/api/parts/{linked}/ontology/links",
            json={"relation": relation, "object_id": phone},
            headers=member.headers,
        )
    )
    kinds = _ok(client.get("/api/parts/ontology/kinds", headers=member.headers))
    row = next(one for one in kinds if one["relation"] == relation)
    assert row["label"] == "적용 모델" and row["incoming"] is True

    by_object = _ok(
        client.get("/api/parts", params={"link_object": phone}, headers=member.headers)
    )
    assert [one["id"] for one in by_object["items"]] == [linked]
    exact = _ok(
        client.get(
            "/api/parts",
            params={"link_object": phone, "link_relation": relation},
            headers=member.headers,
        )
    )
    assert [one["id"] for one in exact["items"]] == [linked]
    wrong = _ok(
        client.get(
            "/api/parts",
            params={"link_object": phone, "link_relation": "cc_tagged"},
            headers=member.headers,
        )
    )
    assert wrong["total"] == 0 and other not in {one["id"] for one in wrong["items"]}


def test_DOE_폴더가_태그와_기준정보를_싣는다(
    client: TestClient, member: Signed, admin: Signed, export_root: Path
) -> None:
    _model, relation, phone = _model_and_relation(client, admin)
    work, part = _part(client, member, "해석할 판")
    _ok(
        client.post(
            f"/api/parts/{part}/ontology/links",
            json={"relation": relation, "object_id": phone},
            headers=member.headers,
        )
    )
    _ok(client.post(f"/api/tags/work/{work}", json={"label": "EMC"}, headers=member.headers))
    study = _ok(
        client.post(
            "/api/doe",
            json={"name": "기준정보 실린 DOE", "recipe": BOX, "work_id": work},
            headers=member.headers,
        )
    )
    _ok(client.post(f"/api/doe/{study['id']}/export", headers=member.headers))
    folder = _folder(export_root, study["id"])

    written = json.loads((folder / "study.json").read_text(encoding="utf-8"))["ontology"]
    assert [(one["label"], one["type_slug"]) for one in written["tags"]] == [("EMC", "cc_tag")]
    [link] = written["links"]
    assert link["on"] == {"kind": "part", "id": part, "name": "해석할 판"}
    assert (link["relation"], link["relation_label"]) == (relation, "적용 모델")
    assert link["label"] == "P5 플립" and link["key"].startswith("SM-P500")
    readme = (folder / "README.txt").read_text(encoding="utf-8")
    assert "기준정보" in readme and "적용 모델: P5 플립" in readme and "태그: EMC" in readme

    # 대상 작업이 없는 DOE 는 빈 칸으로.
    bare = _ok(
        client.post(
            "/api/doe", json={"name": "작업 없는 DOE", "recipe": BOX}, headers=member.headers
        )
    )
    _ok(client.post(f"/api/doe/{bare['id']}/export", headers=member.headers))
    empty = _folder(export_root, bare["id"])
    assert json.loads((empty / "study.json").read_text(encoding="utf-8"))["ontology"] == {
        "tags": [],
        "links": [],
    }
