"""DB 세션과 선언적 기반.

제약 이름 규약을 여기서 고정한다. 이름이 자동으로 정해지면 Alembic 이 autogenerate 에서
제약을 지웠다 만드는 diff 를 내고, 마이그레이션이 매번 흔들린다.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import DDL, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,  # 유휴 커넥션이 끊겨도 조용히 재연결
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 찾기의 트라이그램 색인(`gin_trgm_ops`, 마이그레이션 0028)은 `pg_trgm` 확장이 먼저 있어야
# 만들어진다. 마이그레이션은 스스로 만들지만, 시험처럼 `create_all` 로 표를 세우는 자리도 같은
# 확장이 먼저 있어야 한다 — 없으면 색인 DDL 이 「gin_trgm_ops 가 없다」 로 죽는다.
event.listen(
    Base.metadata,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS pg_trgm").execute_if(  # type: ignore[no-untyped-call]
        dialect="postgresql"
    ),
)
