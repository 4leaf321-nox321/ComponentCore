"""참조 색인 트리거의 **두 벌이 같은 글인가** — 모델 쪽 DDL(시험이 스키마를 세울 때)과 운영이
마이그레이션으로 거는 사본(CompCore 는 `0036_sp_platform` 하나 — SP 의 `0049` · `0075` 를 한
판으로 들였다, ADR 0008).

시험은 모델로 스키마를 세우므로 사본이 어긋나도 시험은 다 통과하고, 그 어긋남은 운영에서만
드러난다 — 그것도 오류가 아니라 「관련 객체」 에서 조용히 빠지는 줄로(SP ADR 0010). 그래서 글을
그대로 견준다. 함수를 고치면 새 마이그레이션에 같은 글을 싣고 여기서 그 판을 본다.

SP 의 「0075 를 되돌리면 0049 의 트리거」 시험은 안 들였다 — 이 저장소에는 그 두 판이 없다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from app.modules.objects import refindex

VERSIONS = Path(__file__).resolve().parents[3] / "migrations" / "versions"


def _migration(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_색인_함수_셋은_0036_과_같은_글이다() -> None:
    first = _migration("0036_sp_platform")
    assert refindex.UPDATED_FUNCTION.strip() in first.REFS_FUNCTIONS
    assert refindex.INSERTED_FUNCTION.strip() in first.REFS_FUNCTIONS
    assert refindex.REDEFINED_FUNCTION.strip() in first.REFS_FUNCTIONS


def test_트리거_정의는_0036_과_같은_글이다() -> None:
    assert refindex.TRIGGERS.strip() == _migration("0036_sp_platform").REFS_TRIGGERS.strip()


def test_큰_문장은_그때_계획하고_작은_문장은_정적_SQL_이다() -> None:
    """두 갈래가 **같은 SQL** 을 돈다 — 한쪽만 고치면 크기에 따라 결과가 갈린다."""
    body = refindex.UPDATED_FUNCTION
    # plpgsql 의 갈래(줄 하나짜리 `ELSE`) — SQL 안의 `CASE … ELSE` 와 섞이지 않게 줄로 찾는다.
    dynamic = body[body.index("EXECUTE $sql$") : body.index("\n    ELSE\n")]
    static = body[body.index("\n    ELSE\n") : body.index("\n    END IF;")]
    for part in (dynamic, static):
        assert refindex._UPDATE_DELETE in part
        assert refindex._UPDATE_INSERT in part
    assert f"> {refindex.PLAN_EACH_ABOVE} THEN" in body
