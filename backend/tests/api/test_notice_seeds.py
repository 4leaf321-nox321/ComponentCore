"""배포에 실려 온 버전 안내 — **초안으로 들어오고, 같은 키는 두 번 안 들어온다.**

새 기능은 코드와 함께 도착하는데 알리는 글은 사람이 따로 써야 했다. 씨앗이 초안으로 들어오면
관리자가 읽고 발행한다 — 자동 발행하지 않는다(배포한 사람이 첫 독자다). MatNexus 의 시험을
옮기고, CompCore 의 「만든 시각은 그 판의 날짜」 를 더했다.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.notices.models import Notice, NoticeSeedKey
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


BACKEND = Path(__file__).resolve().parents[2]


def _script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "import_notices", BACKEND / "scripts" / "import_notices.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_notices"] = module
    spec.loader.exec_module(module)
    return module


def test_씨앗이_초안으로_한_번만_들어오고_관리자만_본다(
    client: TestClient, db: Session, admin: Signed, member: Signed, tmp_path: Path
) -> None:
    script = _script()
    (tmp_path / "2026-09-12-v0.3.0.md").write_text(
        "# v0.3.0 업데이트 — 새로 생긴 것\n\n■ 새 기능\n- 접촉 검사\n- 단면\n",
        encoding="utf-8",
    )
    (tmp_path / "빈-것.md").write_text("# 제목만\n", encoding="utf-8")  # 본문 없음 — 건너뛴다

    assert script.run(db, tmp_path) == ["2026-09-12-v0.3.0"]
    assert script.run(db, tmp_path) == []  # 두 번째는 아무것도 안 넣는다
    assert script.plan(db, tmp_path) == []

    rows = db.scalars(select(Notice).where(Notice.seed_key.is_not(None))).all()
    assert len(rows) == 1
    assert rows[0].title == "v0.3.0 업데이트 — 새로 생긴 것"
    assert rows[0].body == "■ 새 기능\n- 접촉 검사\n- 단면"
    assert rows[0].is_published is False and rows[0].is_popup is False

    # 관리자는 초안을 보고, 일반 사용자는 못 본다.
    titles = [
        one["title"]
        for one in client.get("/api/notices", headers=admin.headers).json()["items"]
    ]
    assert "v0.3.0 업데이트 — 새로 생긴 것" in titles
    assert client.get("/api/notices", headers=member.headers).json()["items"] == []

    # 운영에서 고친 글은 안 덮인다 — 같은 키의 파일 내용이 바뀌어도.
    (tmp_path / "2026-09-12-v0.3.0.md").write_text(
        "# 바뀐 제목\n\n다른 본문\n", encoding="utf-8"
    )
    assert script.run(db, tmp_path) == []
    db.expire_all()
    kept = db.scalar(select(Notice).where(Notice.seed_key == "2026-09-12-v0.3.0"))
    assert kept is not None and kept.title == "v0.3.0 업데이트 — 새로 생긴 것"


def test_지운_초안은_다음_배포에_되살아나지_않는다(
    client: TestClient, db: Session, admin: Signed, tmp_path: Path
) -> None:
    script = _script()
    (tmp_path / "2026-11-15-v0.9.0.md").write_text("# 지울 것\n\n- 본문\n", encoding="utf-8")
    assert script.run(db, tmp_path) == ["2026-11-15-v0.9.0"]
    assert db.get(NoticeSeedKey, "2026-11-15-v0.9.0") is not None

    notice = db.scalar(select(Notice).where(Notice.seed_key == "2026-11-15-v0.9.0"))
    assert notice is not None
    gone = client.delete(f"/api/notices/{notice.id}", headers=admin.headers)
    assert gone.status_code == 204, gone.text
    db.expire_all()

    assert script.plan(db, tmp_path) == []
    assert script.run(db, tmp_path) == []
    assert db.scalar(select(Notice).where(Notice.seed_key == "2026-11-15-v0.9.0")) is None

    # 기억 밖에서 들어온 줄(공지 행만 있다)도 두 번 넣지 않는다.
    db.add(Notice(title="옛 것", body="본문", seed_key="2026-11-15-옛-것"))
    db.commit()
    (tmp_path / "2026-11-15-옛-것.md").write_text("# 옛 것\n\n본문\n", encoding="utf-8")
    assert script.plan(db, tmp_path) == []


def test_만든_시각은_판의_날짜이고_같은_날은_판_번호_순이다(
    db: Session, tmp_path: Path
) -> None:
    """첫 배포에 수십 판이 한꺼번에 들어와도 게시판이 버전 순으로 선다 — 넣은 순간으로 두면
    전부 같은 시각이라 차례가 없다. v0.10.0 은 v0.9.0 뒤다(문자 순이 아니다)."""
    script = _script()
    for key in (
        "2026-11-14-v0.10.0",
        "2026-11-14-v0.9.0",
        "2026-11-14-v0.9.1",
        "2026-11-13-v0.8.0",
    ):
        (tmp_path / f"{key}.md").write_text(f"# {key}\n\n- 본문\n", encoding="utf-8")
    script.run(db, tmp_path)
    rows = {
        one.seed_key: one.created_at
        for one in db.scalars(select(Notice).where(Notice.seed_key.is_not(None)))
    }
    order = sorted(rows, key=lambda key: rows[key])
    assert order == [
        "2026-11-13-v0.8.0",
        "2026-11-14-v0.9.0",
        "2026-11-14-v0.9.1",
        "2026-11-14-v0.10.0",
    ]
    # 한국 시각으로 그 날짜다(자정 UTC 면 화면에서 날짜가 어긋난다).
    first = rows["2026-11-14-v0.9.0"].astimezone(script.KST)
    assert (first.year, first.month, first.day, first.hour) == (2026, 11, 14, 9)
    assert rows["2026-11-14-v0.9.1"] - rows["2026-11-14-v0.9.0"] == timedelta(minutes=1)


def test_실린_씨앗은_전부_읽히고_판마다_하나다() -> None:
    """저장소의 씨앗 파일이 제목·본문을 갖는다 — 배포에서 처음 터지면 늦다. 이름은
    `<날짜>-v<판>` 이고, 같은 판이 두 번 실리지 않는다."""
    script = _script()
    files = sorted((BACKEND / "seeds" / "notices").glob("*.md"))
    assert files, "안내 씨앗이 하나도 없다"
    seen: set[str] = set()
    for path in files:
        title, body = script.read_seed(path)
        assert title and body, path.name
        found = re.fullmatch(r"\d{4}-\d{2}-\d{2}-(v\d+\.\d+\.\d+)", path.stem)
        assert found, path.name
        assert found.group(1) not in seen, path.name
        seen.add(found.group(1))
        assert found.group(1) in title, f"{path.name}: 제목에 판 번호가 없다"
