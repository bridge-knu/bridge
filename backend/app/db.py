"""DB 연결.

DATABASE_URL은 .env의 postgresql://... 형태를 그대로 쓰고,
SQLAlchemy가 psycopg(3) 드라이버를 쓰도록 여기서 접두어만 바꾼다.
"""

import os
from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://bridge:change-me@localhost:5432/bridge")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class Base(DeclarativeBase):
    # 제약 조건 이름을 고정해 두어야 마이그레이션에서 이름으로 찾을 수 있다.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 의존성: 요청마다 세션을 열고 끝나면 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
