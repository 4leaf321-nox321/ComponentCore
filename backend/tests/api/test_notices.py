"""공지 — 폐쇄망의 소통 창구 하나(다른 하나 VOC 는 `test_voc.py`). MatNexus 의 시험을 옮겼다.

지키려는 것:
  - 초안은 발행 전까지 남에게 보이지 않는다 — 목록에도, 한 건 주소로도
  - 팝업은 읽으면 다시 뜨지 않는다
  - 게시판이다 — 쪽으로 나가고, 제목·내용으로 찾고, 안 읽은 것만 고른다
  - 안 읽은 수는 발행된 것만 세고, 「모두 읽음」 이 그 수를 0 으로 만든다
  - (CompCore) 「초안 모두 발행」 은 관리자만, 배포 안내의 발행 시각은 그 판의 날짜다
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from tests.api.conftest import Signed


@pytest.fixture(autouse=True)
def _empty_board(db: Session) -> None:
    """**시험마다 빈 게시판** — 표는 파일마다만 비워진다(`fresh_tables`). 이 파일의
    시험은 「목록이 정확히 이것」 을 보므로 앞 시험의 공지가 남으면 안 된다. 읽음은 FK 가
    함께 지운다."""
    from app.modules.notices.models import Notice, NoticeSeedKey

    db.execute(delete(Notice))
    db.execute(delete(NoticeSeedKey))
    db.commit()


def test_draft_notice_is_hidden_until_published(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    created = client.post(
        "/api/notices",
        json={"title": "점검 안내", "body": "토요일 점검", "is_published": False},
        headers=admin.headers,
    )
    assert created.status_code == 201
    notice_id = created.json()["id"]

    headers = member.headers
    assert client.get("/api/notices", headers=headers).json()["items"] == []
    # 주소를 알아도 못 연다 — 남에게는 없는 것과 같다.
    assert client.get(f"/api/notices/{notice_id}", headers=headers).status_code == 404
    assert client.get(f"/api/notices/{notice_id}", headers=admin.headers).status_code == 200

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin.headers
    )
    listed = client.get("/api/notices", headers=headers).json()["items"]
    assert [n["title"] for n in listed] == ["점검 안내"]


def test_popup_disappears_after_reading(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    notice_id = client.post(
        "/api/notices",
        json={"title": "필독", "body": "중요 변경", "is_popup": True},
        headers=admin.headers,
    ).json()["id"]

    headers = member.headers
    assert len(client.get("/api/notices/popup", headers=headers).json()) == 1

    assert client.post(f"/api/notices/{notice_id}/read", headers=headers).status_code == 204
    assert client.get("/api/notices/popup", headers=headers).json() == []


def test_publish_time_is_stamped_once(client: TestClient, admin: Signed) -> None:
    """수정할 때마다 발행 시각을 갱신하면 "언제 알려졌는가"를 잃는다."""
    notice_id = client.post(
        "/api/notices", json={"title": "안내", "body": "내용"}, headers=admin.headers
    ).json()["id"]
    first = client.get(f"/api/notices/{notice_id}", headers=admin.headers).json()[
        "published_at"
    ]

    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": False}, headers=admin.headers
    )
    client.patch(
        f"/api/notices/{notice_id}", json={"is_published": True}, headers=admin.headers
    )

    again = client.get(f"/api/notices/{notice_id}", headers=admin.headers).json()[
        "published_at"
    ]
    assert again == first


def test_공지를_지우면_읽음_기록도_함께_간다(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    """`notice_reads` 가 CASCADE 다. 안 지워지면 지운 공지를 가리키는 행이 남는다."""
    from app.modules.notices.models import NoticeRead

    notice_id = client.post(
        "/api/notices",
        json={"title": "점검", "body": "토요일", "is_published": True, "is_popup": True},
        headers=admin.headers,
    ).json()["id"]
    headers = member.headers
    client.post(f"/api/notices/{notice_id}/read", headers=headers)
    assert db.query(NoticeRead).count() == 1

    assert client.delete(f"/api/notices/{notice_id}", headers=admin.headers).status_code == 204
    assert client.get("/api/notices", headers=headers).json()["items"] == []
    db.expire_all()
    assert db.query(NoticeRead).count() == 0


def test_공지는_시스템_관리자만_지운다(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    notice_id = client.post(
        "/api/notices",
        json={"title": "점검", "body": "토요일", "is_published": True},
        headers=admin.headers,
    ).json()["id"]
    headers = member.headers

    assert client.delete(f"/api/notices/{notice_id}", headers=headers).status_code == 403
    assert client.delete(f"/api/notices/{notice_id}", headers=admin.headers).status_code == 204


def test_게시판은_쪽으로_나가고_제목_내용으로_찾는다(
    client: TestClient, admin: Signed
) -> None:
    """공지가 늘면 카드 더미에서는 찾을 길이 없었다. **최근에 알린 것이 위다.**"""
    for title, body in (
        ("1월 점검", "토요일 점검"),
        ("새 기능", "내보내기"),
        ("2월 점검", "일요일"),
    ):
        made = client.post(
            "/api/notices", json={"title": title, "body": body}, headers=admin.headers
        )
        assert made.status_code == 201, made.text

    page = client.get("/api/notices", params={"limit": 2}, headers=admin.headers).json()
    assert page["total"] == 3 and page["limit"] == 2 and len(page["items"]) == 2
    assert page["items"][0]["title"] == "2월 점검"  # 마지막에 알린 것이 위다
    rest = client.get(
        "/api/notices", params={"limit": 2, "offset": 2}, headers=admin.headers
    ).json()
    assert [one["title"] for one in rest["items"]] == ["1월 점검"]

    # 제목으로도, 내용으로도 찾는다.
    found = client.get("/api/notices", params={"q": "점검"}, headers=admin.headers).json()
    assert {one["title"] for one in found["items"]} == {"1월 점검", "2월 점검"}
    found = client.get("/api/notices", params={"q": "내보내기"}, headers=admin.headers).json()
    assert [one["title"] for one in found["items"]] == ["새 기능"]


def test_안_읽은_것만_고른다(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    ids = [
        client.post(
            "/api/notices", json={"title": title, "body": "본문"}, headers=admin.headers
        ).json()["id"]
        for title in ("가", "나")
    ]
    headers = member.headers
    client.post(f"/api/notices/{ids[0]}/read", headers=headers)

    unread = client.get("/api/notices", params={"unread": True}, headers=headers).json()
    assert [one["title"] for one in unread["items"]] == ["나"]
    listed = {
        one["title"]: one["is_read"]
        for one in client.get("/api/notices", headers=headers).json()["items"]
    }
    assert listed == {"가": True, "나": False}


def test_쓴_사람과_배포에_실려_온_안내를_가른다(
    client: TestClient, db: Session, admin: Signed
) -> None:
    """배포가 넣은 글(`seeds/notices`)은 쓴 사람이 없다 — 「알 수 없음」 이 아니라
    배포 안내다."""
    from app.modules.notices.models import Notice

    written = client.post(
        "/api/notices", json={"title": "직접 쓴 공지", "body": "본문"}, headers=admin.headers
    ).json()
    assert written["created_by"] == "admin"
    assert written["from_release"] is False

    seeded = Notice(
        title="새로 생긴 것", body="- 물성", is_published=True, seed_key="2026-09-24-시험"
    )
    db.add(seeded)
    db.commit()
    one = client.get(f"/api/notices/{seeded.id}", headers=admin.headers).json()
    assert one["created_by"] is None and one["from_release"] is True


def test_안_읽은_수는_발행된_것만_센다(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    """사이드바의 수. **초안은 안 센다** — 관리자에게도 초안은 아직 아무에게도 안 알린 글이라
    「새 글」 이 아니다(목록의 「새 글」 표와 같다)."""
    ids = [
        client.post(
            "/api/notices", json={"title": title, "body": "본문"}, headers=admin.headers
        ).json()["id"]
        for title in ("가", "나", "다")
    ]
    client.post(
        "/api/notices",
        json={"title": "초안", "body": "본문", "is_published": False},
        headers=admin.headers,
    )
    headers = member.headers
    count = client.get("/api/notices/unread-count", headers=headers)
    assert count.status_code == 200, count.text
    assert count.json() == {"unread": 3}

    client.post(f"/api/notices/{ids[0]}/read", headers=headers)
    assert client.get("/api/notices/unread-count", headers=headers).json() == {"unread": 2}
    # 관리자도 초안은 안 센다.
    assert client.get("/api/notices/unread-count", headers=admin.headers).json() == {
        "unread": 3
    }


def test_모두_읽음은_수를_0_으로_만들고_이미_읽은_것은_건너뛴다(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    """처음 들어온 사람에게는 쌓인 공지가 전부 새 글이다. 하나를 이미 읽었어도(다른 탭에서)
    겹친 짝 때문에 전부가 되돌려지면 안 된다."""
    from sqlalchemy import func, select

    from app.modules.notices.models import NoticeRead

    ids = [
        client.post(
            "/api/notices", json={"title": title, "body": "본문"}, headers=admin.headers
        ).json()["id"]
        for title in ("가", "나")
    ]
    headers = member.headers
    client.post(f"/api/notices/{ids[0]}/read", headers=headers)

    done = client.post("/api/notices/read-all", headers=headers)
    assert done.status_code == 200, done.text
    assert done.json() == {"unread": 0}
    assert client.get("/api/notices/unread-count", headers=headers).json() == {"unread": 0}
    listed = client.get("/api/notices", headers=headers).json()["items"]
    assert all(one["is_read"] for one in listed)
    # 짝마다 한 줄 — 이미 읽은 것을 두 번 적지 않았다.
    rows = db.scalar(select(func.count()).select_from(NoticeRead))
    assert rows == 2

    # 남의 읽음은 건드리지 않는다.
    assert client.get("/api/notices/unread-count", headers=admin.headers).json() == {
        "unread": 2
    }


def test_초안_모두_발행은_관리자만_하고_배포_안내는_판의_날짜로_선다(
    client: TestClient, db: Session, admin: Signed, member: Signed
) -> None:
    """첫 배포에 지난 판의 안내가 수십 건 초안으로 들어온다 — 하나씩 켜라고 하면 아무도 안
    한다. 배포 안내는 발행해도 **그 판의 날짜**에 선다 — 오늘 발행했다고 v0.3.0 이 맨 위로
    오지 않는다."""
    from app.modules.notices.models import Notice

    old = Notice(
        title="v0.3.0 업데이트",
        body="- 옛 기능",
        is_published=False,
        seed_key="2026-09-01-v0.3.0",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    new = Notice(
        title="v0.4.0 업데이트",
        body="- 새 기능",
        is_published=False,
        seed_key="2026-09-05-v0.4.0",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )
    db.add_all([old, new])
    db.commit()
    hand = client.post(
        "/api/notices",
        json={"title": "손으로 쓴 초안", "body": "본문", "is_published": False},
        headers=admin.headers,
    ).json()

    drafts = client.get(
        "/api/notices", params={"draft": True, "limit": 1}, headers=admin.headers
    )
    assert drafts.json()["total"] == 3
    # 남에게 초안은 없는 것과 같다.
    assert (
        client.get("/api/notices", params={"draft": True}, headers=member.headers).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.post("/api/notices/publish-drafts", headers=member.headers).status_code == 403
    )
    assert client.get("/api/notices", headers=member.headers).json()["items"] == []

    done = client.post("/api/notices/publish-drafts", headers=admin.headers)
    assert done.status_code == 200, done.text
    assert done.json() == {"published": 3}
    assert client.post("/api/notices/publish-drafts", headers=admin.headers).json() == {
        "published": 0
    }

    listed = client.get("/api/notices", headers=member.headers).json()["items"]
    # 손으로 쓴 것은 지금 발행 — 맨 위. 배포 안내는 판 순.
    assert [one["title"] for one in listed] == [
        "손으로 쓴 초안",
        "v0.4.0 업데이트",
        "v0.3.0 업데이트",
    ]
    by_title = {one["title"]: one for one in listed}
    assert by_title["v0.3.0 업데이트"]["published_at"].startswith("2026-09-01")
    assert by_title["손으로 쓴 초안"]["id"] == hand["id"]
    assert by_title["손으로 쓴 초안"]["published_at"] is not None
    # 팝업은 켜지 않는다 — 수십 건이 로그인마다 뜨면 아무도 안 읽는다.
    assert client.get("/api/notices/popup", headers=member.headers).json() == []


def test_배포_안내를_하나씩_발행해도_판의_날짜다(
    client: TestClient, db: Session, admin: Signed
) -> None:
    from app.modules.notices.models import Notice

    seeded = Notice(
        title="v0.5.0 업데이트",
        body="- 본문",
        is_published=False,
        seed_key="2026-09-10-v0.5.0",
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
    )
    db.add(seeded)
    db.commit()
    patched = client.patch(
        f"/api/notices/{seeded.id}", json={"is_published": True}, headers=admin.headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["published_at"].startswith("2026-09-10")
