"""DB 스키마가 코드보다 뒤처져 있는가 — 기동할 때 한 번 본다.

기동을 막지는 않는다 — DB 에 못 붙는 상황에서 서버까지 안 뜨면 원인을 볼 화면조차 없다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def code_head() -> str | None:
    try:
        config = Config(str(_ALEMBIC_INI))
        script_location = config.get_main_option("script_location") or "migrations"
        config.set_main_option("script_location", str(_ALEMBIC_INI.parent / script_location))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # pragma: no cover
        logger.debug("마이그레이션 head 를 읽지 못했습니다.", exc_info=True)
        return None


def db_revision(engine: Engine) -> str | None:
    try:
        with engine.connect() as connection:
            found = connection.scalar(text("SELECT version_num FROM alembic_version"))
        return str(found) if found is not None else None
    except Exception:
        logger.debug("alembic_version 을 읽지 못했습니다.", exc_info=True)
        return None


def warn_if_behind(engine: Engine) -> str | None:
    head = code_head()
    current = db_revision(engine)
    if head is None or current is None or current == head:
        return None
    logger.warning(
        "데이터베이스가 코드보다 뒤처져 있습니다: %s -> %s. "
        "`alembic upgrade head` 를 돌리세요.",
        current,
        head,
    )
    return head
