"""테스트 공통 준비.

**개발 DB 를 건드리지 않는다.** 접속 정보는 개발 .env 에서 읽되 데이터베이스 이름만
`<이름>_test` 로 바꿔 쓴다. bcrypt 라운드를 낮춘다 — 시험이 보려는 것은 인증 로직이지
bcrypt 의 느림이 아니다.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_BCRYPT_ROUNDS", "4")


def _test_database_url() -> str:
    explicit = os.environ.get("APP_TEST_DATABASE_URL")
    if explicit:
        return explicit
    from app.config import Settings

    url = Settings().database_url
    base, _, name = url.rpartition("/")
    return f"{base}/{name}_test" if base else url


os.environ["DATABASE_URL"] = _test_database_url()

import tempfile  # noqa: E402

# 시험은 저장소 밖(임시 폴더)에 파일을 쓴다 — 개발 filestore 를 시험 산출물로 채우지 않는다.
_TEMP_STORE = tempfile.mkdtemp(prefix="compcore-test-")
os.environ["FILESTORE_DIR"] = _TEMP_STORE
os.environ["LOG_DIR"] = os.path.join(_TEMP_STORE, "logs")
# API 시험은 워커 없이 돈다 — 작업이 요청 안에서 끝난다. 워커 자체는 tests/api/test_jobs.py 가
# 직접 부른다(claim → execute).
os.environ.setdefault("JOBS_INLINE", "1")
# **시험은 살아 있는 MatNexus 에 닿지 않는다.** `.env` 의 주소를 그대로 쓰면 그쪽이 꺼져 있는
# 날 연결을 기다리느라 스위트가 25초에서 7분이 됐다(실측 2026-09-25 — 호출마다 15초 제한).
# MatNexus 를 쓰는 시험은 클라이언트 함수를 바꿔 끼운다.
os.environ["MATNEXUS_BASE_URL"] = ""

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.all_models  # noqa: F401,E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema() -> None:
    """표를 만들고 시작한다. 시험이 보려는 것은 **지금 코드의 모델**이다 — 마이그레이션이
    모델과 어긋났는지는 `alembic check` 가 본다."""
    name = engine.url.database or ""
    if not name.endswith("_test"):
        raise RuntimeError(f"시험 DB 가 아닙니다: {name}. 이름이 _test 로 끝나야 합니다.")
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    fastapi_app.state.session_factory = SessionLocal
    with TestClient(fastapi_app) as test_client:
        yield test_client
