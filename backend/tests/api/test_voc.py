"""VOC 게시판 — 누구나 보고, 한 건은 상태를 거쳐 가며, 누가 언제 무슨 말로 옮겼는지 남는다.

MatNexus 의 VOC 와 같은 절차다: 해결 · 반려는 관리자가 말과 함께, 종료는 작성자가 확인한다.
작성자는 다른 사용자가 말을 남기기 전까지만 고친다. 지우면 `deleted_at` 만 채운다.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.voc import services
from app.modules.voc.models import VocItem
from tests.api.conftest import Signed, _login, make_user


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201), response.text
    return response.json()


def _code(response: Any) -> str:
    return str(response.json()["error"]["code"])


@pytest.fixture
def other(client: TestClient, db: Session) -> Signed:
    """작성자도 관리자도 아닌 사용자."""
    user = make_user(db, label="other", is_system_admin=False)
    return Signed(email=user.email, token=_login(client, user.email))


def _write(client: TestClient, who: Signed, title: str = "STEP 업로드가 안 됩니다") -> Any:
    return _ok(
        client.post(
            "/api/voc",
            json={
                "title": title,
                "body": "200 MB 아래인데도 거절됩니다.",
                "page_path": "/draw",
            },
            headers=who.headers,
        )
    )


def _move(
    client: TestClient, who: Signed, item: str, status: str | None, note: str = ""
) -> Any:
    return client.post(
        f"/api/voc/{item}/events",
        json={"status": status, "note": note or None},
        headers=who.headers,
    )


def test_누구나_보는_게시판이고_번호가_붙는다(
    client: TestClient, member: Signed, other: Signed
) -> None:
    # 시험 DB 는 한 번 도는 동안 공유된다 — 찾기는 이 시험만의 낱말로.
    tag = uuid.uuid4().hex[:8]
    first = _write(client, member)
    second = _write(client, member, f"도면 치수가 겹칩니다 {tag}")
    assert second["seq"] > first["seq"]
    assert first["status"] == "open" and first["status_label"] == "등록"
    assert first["page_path"] == "/draw" and first["created_by"] == "member"
    # 등록도 이력의 첫 줄이다 — 「누가 언제 냈다」.
    assert [(one["from_status"], one["to_status"]) for one in first["events"]] == [
        (None, "open")
    ]
    assert first["is_mine"] and first["can_edit"] and first["event_count"] == 0

    seen = _ok(client.get("/api/voc", headers=other.headers))
    ours = [one for one in seen["items"] if one["id"] in (first["id"], second["id"])]
    assert [one["id"] for one in ours] == [second["id"], first["id"]]  # 최신이 위
    assert all(not one["is_mine"] and not one["can_edit"] for one in ours)
    # 다른 사용자는 상태를 못 옮기고 말만 보탠다.
    detail = _ok(client.get(f"/api/voc/{first['id']}", headers=other.headers))
    assert detail["allowed"] == []

    mine = _ok(client.get("/api/voc?mine=true", headers=other.headers))
    assert all(one["is_mine"] for one in mine["items"])
    found = _ok(client.get(f"/api/voc?q=치수 {tag}", headers=other.headers))
    assert [one["id"] for one in found["items"]] == [second["id"]]
    bad = client.get("/api/voc?status=done", headers=other.headers)
    assert bad.status_code == 422 and _code(bad).endswith("VOC-0002")


def test_해결은_관리자가_말과_함께_종료는_작성자가_확인한다(
    client: TestClient, member: Signed, admin: Signed, other: Signed
) -> None:
    item = _write(client, member)["id"]
    # 작성자는 「등록」 에서 옮길 곳이 없다 — 접수는 관리자의 일이다.
    refused = _move(client, member, item, "accepted")
    assert refused.status_code == 403 and _code(refused).endswith("VOC-0006")
    assert _move(client, other, item, "accepted").status_code == 403

    accepted = _ok(_move(client, admin, item, "accepted"))
    assert accepted["status"] == "accepted" and accepted["status_by"] == "admin"
    assert "resolved" in accepted["allowed"] and "resolved" in accepted["note_required"]
    assert accepted["allowed_labels"]["resolved"] == "해결 처리"
    # 같은 상태로는 못 옮긴다 — 말만 보태려면 상태를 비운다.
    same = _move(client, admin, item, "accepted", "다시")
    assert same.status_code == 422 and _code(same).endswith("VOC-0005")
    # 「해결」 은 무엇을 했는지 없이는 안 된다.
    bare = _move(client, admin, item, "resolved")
    assert bare.status_code == 422 and _code(bare).endswith("VOC-0007")
    resolved = _ok(_move(client, admin, item, "resolved", "업로드 상한을 고쳤습니다."))
    assert resolved["status"] == "resolved"

    # 다른 사용자는 댓글만, 작성자는 확인하고 종료하거나 다시 연다(다시 열 때는 이유).
    comment = _ok(_move(client, other, item, None, "저도 같은 문제를 겪었습니다."))
    assert comment["status"] == "resolved" and comment["events"][-1]["to_status"] == "resolved"
    author = _ok(client.get(f"/api/voc/{item}", headers=member.headers))
    assert set(author["allowed"]) == {"closed", "open"} and author["note_required"] == ["open"]
    assert _move(client, member, item, "open").status_code == 422
    closed = _ok(_move(client, member, item, "closed"))
    assert closed["status"] == "closed" and closed["status_label"] == "종료"
    assert [one["to_status"] for one in closed["events"]] == [
        "open",
        "accepted",
        "resolved",
        "resolved",
        "closed",
    ]
    listed = _ok(client.get("/api/voc?status=closed&limit=200", headers=other.headers))
    row = next(one for one in listed["items"] if one["id"] == item)
    assert row["event_count"] == 4 and row["status_by"] == "member"

    empty = client.post(f"/api/voc/{item}/events", json={}, headers=other.headers)
    assert empty.status_code == 422


def test_작성자는_다른_사용자가_말을_남기기_전까지만_고친다(
    client: TestClient, member: Signed, admin: Signed, other: Signed, db: Session
) -> None:
    item = _write(client, member)["id"]
    edited = _ok(
        client.patch(
            f"/api/voc/{item}", json={"title": "STEP 업로드 실패"}, headers=member.headers
        )
    )
    assert edited["title"] == "STEP 업로드 실패"
    assert edited["body"] == "200 MB 아래인데도 거절됩니다."  # 안 보낸 칸은 그대로
    stranger = client.patch(f"/api/voc/{item}", json={"title": "x"}, headers=other.headers)
    assert stranger.status_code == 403 and _code(stranger).endswith("VOC-0003")
    blank = client.patch(f"/api/voc/{item}", json={"title": "   "}, headers=member.headers)
    assert blank.status_code == 422

    _ok(_move(client, admin, item, None, "어느 파일인지 첨부해 주십시오."))
    late = client.patch(f"/api/voc/{item}", json={"body": "바뀐 본문"}, headers=member.headers)
    assert late.status_code == 403 and _code(late).endswith("VOC-0004")
    assert client.delete(f"/api/voc/{item}", headers=member.headers).status_code == 403
    assert _ok(client.get(f"/api/voc/{item}", headers=member.headers))["can_edit"] is False
    # 관리자는 언제나 — 지우면 목록 · 상세에서 빠지지만 행은 남는다.
    assert client.delete(f"/api/voc/{item}", headers=admin.headers).status_code == 204
    assert client.get(f"/api/voc/{item}", headers=member.headers).status_code == 404
    listed = _ok(client.get("/api/voc?limit=200", headers=member.headers))
    assert item not in {one["id"] for one in listed["items"]}
    row = db.get(VocItem, uuid.UUID(item))
    db.refresh(row)
    assert row is not None and row.deleted_at is not None


def test_관리자는_잘못_옮긴_이력을_지우고_상태가_되돌아간다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    item = _write(client, member)["id"]
    _ok(_move(client, admin, item, "accepted"))
    wrong = _ok(_move(client, admin, item, "resolved", "다른 건에 적을 말"))
    mistake = wrong["events"][-1]
    assert wrong["can_delete_events"] is True
    assert (
        _ok(client.get(f"/api/voc/{item}", headers=member.headers))["can_delete_events"]
        is False
    )

    refused = client.delete(f"/api/voc/{item}/events/{mistake['id']}", headers=member.headers)
    assert refused.status_code == 403 and _code(refused).endswith("VOC-0008")
    back = _ok(client.delete(f"/api/voc/{item}/events/{mistake['id']}", headers=admin.headers))
    assert back["status"] == "accepted" and len(back["events"]) == 2
    first = back["events"][0]["id"]
    kept = client.delete(f"/api/voc/{item}/events/{first}", headers=admin.headers)
    assert kept.status_code == 422 and _code(kept).endswith("VOC-0010")

    # 이력의 말 고치기 — 해결로 옮긴 줄은 비울 수 없고, 댓글을 비우려면 줄을 지운다.
    resolved = _ok(_move(client, admin, item, "resolved", "고쳤습니다."))
    line = resolved["events"][-1]["id"]
    fixed = _ok(
        client.patch(
            f"/api/voc/{item}/events/{line}",
            json={"note": "v0.13.0에서 고쳤습니다."},
            headers=admin.headers,
        )
    )
    assert fixed["events"][-1]["note"] == "v0.13.0에서 고쳤습니다."
    cleared = client.patch(
        f"/api/voc/{item}/events/{line}", json={"note": ""}, headers=admin.headers
    )
    assert cleared.status_code == 422 and _code(cleared).endswith("VOC-0007")
    said = _ok(_move(client, member, item, None, "확인했습니다."))["events"][-1]["id"]
    blank = client.patch(
        f"/api/voc/{item}/events/{said}", json={"note": ""}, headers=admin.headers
    )
    assert blank.status_code == 422 and _code(blank).endswith("VOC-0011")


def test_첨부는_작성자와_관리자가_붙이고_누구나_받는다(
    client: TestClient,
    member: Signed,
    admin: Signed,
    other: Signed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _write(client, member)["id"]
    files = {"file": ("화면 캡처.png", b"\x89PNG fake", "image/png")}
    made = client.post(f"/api/voc/{item}/attachments", files=files, headers=member.headers)
    assert made.status_code == 201, made.text
    attached = made.json()["attachments"]
    assert [one["filename"] for one in attached] == ["화면_캡처.png"]
    assert attached[0]["size"] == len(b"\x89PNG fake") and made.json()["can_attach"] is True

    stranger = client.post(f"/api/voc/{item}/attachments", files=files, headers=other.headers)
    assert stranger.status_code == 403 and _code(stranger).endswith("VOC-0012")
    # 받는 것은 누구나 — 문서로 열리지 않게 늘 내려받기다.
    got = client.get(attached[0]["url"], headers=other.headers)
    assert got.status_code == 200 and got.content == b"\x89PNG fake"
    assert got.headers["content-type"] == "application/octet-stream"
    assert got.headers["x-content-type-options"] == "nosniff"
    listed = _ok(client.get("/api/voc", headers=other.headers))
    assert next(one for one in listed["items"] if one["id"] == item)["attachment_count"] == 1

    monkeypatch.setattr(services, "MAX_ATTACHMENT_BYTES", 4)
    big = client.post(
        f"/api/voc/{item}/attachments",
        files={"file": ("log.txt", b"0123456789", "text/plain")},
        headers=admin.headers,
    )
    assert big.status_code == 413 and _code(big).endswith("VOC-0014")

    gone = _ok(
        client.delete(
            f"/api/voc/{item}/attachments/{attached[0]['id']}", headers=admin.headers
        )
    )
    assert gone["attachments"] == []
    assert client.get(attached[0]["url"], headers=other.headers).status_code == 404


def test_고른_건을_zip_하나로_내려받는다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    first = _write(client, member, "치수/공차 표시")["id"]
    second = _write(client, member)["id"]
    client.post(
        f"/api/voc/{first}/attachments",
        files={"file": ("log.txt", b"trace", "text/plain")},
        headers=member.headers,
    )
    _ok(_move(client, admin, first, "rejected", "중복입니다."))
    response = client.post(
        "/api/voc/export", json={"ids": [second, first]}, headers=member.headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    bundle = zipfile.ZipFile(io.BytesIO(response.content))
    index = json.loads(bundle.read("index.json"))
    assert index["count"] == 2 and index["exported_by"] == "member"
    folders = [one["folder"] for one in index["items"]]
    assert folders[0].endswith("치수-공차-표시")  # 번호 순, 파일 이름에 못 쓰는 글자는 뺀다
    body = json.loads(bundle.read(f"{folders[0]}/item.json"))
    assert body["status"] == "rejected" and body["events"][-1]["note"] == "중복입니다."
    assert body["attachments"][0]["path"] == "attachments/log.txt"
    assert bundle.read(f"{folders[0]}/attachments/log.txt") == b"trace"

    missing = client.post(
        "/api/voc/export", json={"ids": [str(uuid.uuid4())]}, headers=member.headers
    )
    assert missing.status_code == 404 and _code(missing).endswith("VOC-0001")


def test_사이드바의_숫자는_손댈_차례인_건이다(
    client: TestClient, member: Signed, admin: Signed
) -> None:
    def summary(who: Signed) -> Any:
        return _ok(client.get("/api/voc/summary", headers=who.headers))

    # 시험 DB 는 공유된다 — 관리자의 접수 대기는 늘고 준 만큼만 본다.
    before = summary(admin)["waiting"]
    item = _write(client, member)["id"]
    assert summary(admin)["waiting"] == before + 1
    assert summary(member) == {"waiting": 0, "to_confirm": 0}  # 관리자가 아니면 접수 대기는 0
    _ok(_move(client, admin, item, "accepted"))
    assert summary(admin)["waiting"] == before
    _ok(_move(client, admin, item, "resolved", "고쳤습니다."))
    assert summary(member)["to_confirm"] == 1  # 본인 건이 해결되어 확인을 기다린다
    _ok(_move(client, member, item, "closed"))
    assert summary(member)["to_confirm"] == 0
