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
# 설계점은 한 프로세스로 — 시험마다 일꾼을 띄우면 느리다. 나눠 만드는 길은 그 시험이 켠다.
os.environ.setdefault("DOE_WORKERS", "1")
# **시험은 살아 있는 MatNexus 에 닿지 않는다.** `.env` 의 주소를 그대로 쓰면 그쪽이 꺼져 있는
# 날 연결을 기다리느라 스위트가 25초에서 7분이 됐다(실측 2026-09-25 — 호출마다 15초 제한).
# MatNexus 를 쓰는 시험은 클라이언트 함수를 바꿔 끼운다.
os.environ["MATNEXUS_BASE_URL"] = ""

import contextlib  # noqa: E402
import time  # noqa: E402
from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Connection, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.all_models  # noqa: F401,E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

#: 시험 DB 하나를 **한 pytest 만** 쓴다 — 그 잠금(advisory lock)의 열쇠("CCST").
SUITE_LOCK = 0x43435354
#: 잠금 연결의 이름 — 기다리는 쪽이 누가 쥐고 있는지 말한다(`pg_stat_activity`).
SUITE_NAME = f"compcore pytest {os.getpid()}"

_WHO = """
SELECT a.application_name, a.backend_start
  FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
 WHERE l.locktype = 'advisory' AND l.granted AND l.classid = 0 AND l.objid = :key
   AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
 LIMIT 1
"""


def _say(config: pytest.Config, line: str) -> None:
    """캡처를 비켜 바로 보인다 — 기다리는 동안 말이 없으면 멈춘 줄 안다."""
    capture = config.pluginmanager.getplugin("capturemanager")
    off = capture.global_and_fixture_disabled() if capture else contextlib.nullcontext()
    with off:
        print(line, flush=True)


def _holder(connection: Connection) -> str:
    row = connection.execute(text(_WHO), {"key": SUITE_LOCK}).first()
    if row is None:
        return "누구인지 모름"
    return f"{row.application_name or '이름 없음'}, {row.backend_start:%H:%M:%S} 시작"


def _hold_suite(config: pytest.Config) -> Connection:
    """시험 DB 의 잠금을 쥔다 — 다른 pytest 가 쥐고 있으면 놓을 때까지 기다린다.

    시험은 시작하며 스키마를 지운다. 긴 실행 중에 둘째 pytest 가 뜨면 앞 실행의 표가 사라지고,
    둘이 같은 DB 에 열어 둔 트랜잭션은 지표 워터마크까지 붙잡는다(2026-10-16 — 같은 작업 트리의
    두 세션이 겹쳐 돌려 `test_metric_rules` · `test_mcp_organize` 가 번갈아 깨졌다). 규칙
    (AGENTS.md)만으로는 안 지켜져 잠금으로 막는다. 잠금은 연결에 붙어 있어 프로세스가 죽으면
    저절로 풀린다 — 파일 잠금처럼 찌꺼기가 남지 않는다.

    **트랜잭션을 열지 않는다(AUTOCOMMIT).** 열어 두면 이 연결이 스위트 내내 「도는 트랜잭션」
    이 되어 워터마크를 붙잡는다 — 막으려던 바로 그 일이다. 기다리는 시간은
    `COMPCORE_TEST_LOCK_WAIT`(초, 기본 1800 · 0 이면 기다리지 않고 멈춘다)."""
    wait = float(os.environ.get("COMPCORE_TEST_LOCK_WAIT", "1800"))
    lock = create_engine(
        engine.url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
        connect_args={"application_name": SUITE_NAME},
    )
    connection = lock.connect()
    take = text("SELECT pg_try_advisory_lock(:key)")
    if connection.execute(take, {"key": SUITE_LOCK}).scalar():
        return connection
    holder = _holder(connection)
    _say(
        config,
        f"\n다른 pytest 가 시험 DB({engine.url.database})를 쓰고 있습니다({holder}). "
        f"끝날 때까지 기다립니다(최대 {wait:.0f}초).",
    )
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(2)
        if connection.execute(take, {"key": SUITE_LOCK}).scalar():
            _say(config, "시험 DB 가 비었습니다 — 이어서 시작합니다.")
            return connection
    holder = _holder(connection)
    connection.close()
    pytest.exit(
        f"시험 DB({engine.url.database})를 {wait:.0f}초 기다렸지만 다른 pytest({holder})가 "
        "아직 쓰고 있습니다. 그 실행이 끝난 뒤 다시 돌리십시오.",
        returncode=3,
    )


@pytest.fixture(scope="session", autouse=True)
def schema(request: pytest.FixtureRequest) -> Iterator[None]:
    """표를 만들고 시작한다. 시험이 보려는 것은 **지금 코드의 모델**이다 — 마이그레이션이
    모델과 어긋났는지는 `alembic check` 가 본다. 지우기 **전에** 시험 DB 의 잠금을 쥔다
    (`_hold_suite`)."""
    name = engine.url.database or ""
    if not name.endswith("_test"):
        raise RuntimeError(f"시험 DB 가 아닙니다: {name}. 이름이 _test 로 끝나야 합니다.")
    held = _hold_suite(request.config)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        Base.metadata.create_all(bind=engine)
        yield
    finally:
        held.close()


@pytest.fixture(scope="module", autouse=True)
def fresh_tables(schema: None) -> None:
    """**시험 파일마다 빈 표로 시작한다.**

    예전에는 스위트 전체가 한 DB 에 쌓였다 — 앞 파일이 남긴 타입 · 지표 · 객체가 수백 개가
    되어, 정의 전체를 훑는 동작(속성 삭제 점검 · 지표 재계산 · 통째 내보내기)이 혼자 돌면
    0.5초인 시험을 3분으로 늘렸다(2026-10-21 — 스위트 35분 중 95%가 그것). 남이 남긴 줄을
    「차이로 보는」 시험은 그대로 통하고, 한 파일 안의 시험끼리는 지금처럼 이어진다.

    다른 연결이 표를 쥐고 있으면 TRUNCATE 가 끝없이 기다린다 — 10초 넘게 못 잡으면 오류로
    말한다(시험이 연결을 안 닫은 것이다).

    **줄이 있는 표만** 비운다 — 표 150여 개를 늘 통째로 비우면 파일마다 0.5초(스위트에서
    1분 반)였고, 한 파일이 쓰는 표는 수십 개다. DB 를 안 쓰는 파일 뒤에는 아무것도 안 한다."""
    probe = " UNION ALL ".join(
        f"SELECT '{table.name}' WHERE EXISTS (SELECT 1 FROM \"{table.name}\")"
        for table in Base.metadata.tables.values()
    )
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        filled = [str(row[0]) for row in connection.execute(text(probe))]
        if filled:
            names = ", ".join(f'"{name}"' for name in filled)
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


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
