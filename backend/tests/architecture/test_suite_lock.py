"""시험 DB 는 **한 pytest 만** 쓴다 — 둘째 실행은 스키마를 지우기 전에 멈추거나 기다린다.

시험은 시작하며 `<db>_test` 의 스키마를 지운다. 같은 작업 트리의 두 세션이 pytest 를 겹쳐
돌리자 앞 실행의 표가 사라지고, 열어 둔 트랜잭션이 지표 워터마크를 붙잡아 엉뚱한 시험이
번갈아 깨졌다(2026-10-16). 규칙(AGENTS.md)만으로는 안 지켜져 `tests/conftest.py` 가 잠금을
쥔다 — 여기서 그 잠금이 정말 둘째 실행을 막는지 본다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import SUITE_LOCK, SUITE_NAME

BACKEND = Path(__file__).resolve().parents[2]


def _held_by_me(db: Session) -> bool:
    return bool(
        db.scalar(
            text(
                """SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
                    WHERE l.locktype = 'advisory' AND l.granted AND l.objid = :key
                      AND a.application_name = :name"""
            ),
            {"key": SUITE_LOCK, "name": SUITE_NAME},
        )
    )


def test_둘째_pytest_는_스키마를_지우기_전에_누가_쓰는지_말하고_멈춘다(db: Session) -> None:
    if not _held_by_me(db):
        # 이 프로세스가 잠금을 안 쥐었으면(`--noconftest` 등) 둘째 실행이 진짜로 스키마를
        # 지운다 — 띄우지 않는다.
        pytest.skip("이 실행이 시험 DB 잠금을 쥐고 있지 않습니다")
    db.commit()  # 위의 조회가 연 트랜잭션을 닫는다 — 둘째 실행 동안 워터마크를 붙잡지 않게
    env = {
        **os.environ,
        # 이 실행이 쓰는 시험 DB 그대로 — 안 주면 둘째의 conftest 가 `_test` 를 한 번 더
        # 붙인다.
        "APP_TEST_DATABASE_URL": os.environ["DATABASE_URL"],
        "COMPCORE_TEST_LOCK_WAIT": "0",
    }
    env.pop("PYTEST_ADDOPTS", None)
    second = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/unit/test_core_units.py"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )  # fmt: skip
    said = second.stdout + second.stderr
    assert second.returncode == 3, said
    assert "다른 pytest" in said and SUITE_NAME in said, said
    # 지우지 않았다 — 이 실행의 표가 그대로 있다.
    assert db.scalar(text("SELECT to_regclass('public.users') IS NOT NULL"))
