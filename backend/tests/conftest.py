"""공통 테스트 준비.

- DB: docker compose의 postgres를 쓴다. 연결할 수 없으면 DB가 필요한 테스트는 건너뛴다.
  REQUIRE_DB=1이면 건너뛰지 않고 실패한다 (PR 전 확인용).
  각 테스트는 트랜잭션 안에서 실행하고 끝나면 되돌리므로 DB에 데이터가 남지 않는다.
- Redis: 실제 Redis 대신 메모리용 가짜(fakeredis)를 쓴다.
"""

import os
import secrets

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import login_lock, security
from app.db import database_url, get_db
from app.main import app
from app.seed import ensure_demo_user

# 테스트를 실행할 때마다 새로 만드는 서명 키. 서명·검증할 때 읽으므로 앱을 불러온 뒤에 넣어도 된다.
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(security, "BCRYPT_ROUNDS", 4)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(database_url())
    try:
        with eng.connect():
            pass
    except OperationalError:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail("postgres에 연결할 수 없음 (REQUIRE_DB=1이라 건너뛰지 않음)")
        pytest.skip("postgres에 연결할 수 없음 (docker compose up -d 필요)")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    conn = engine.connect()
    tx = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    tx.rollback()
    conn.close()


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def api_client(db, fake_redis):
    """테스트용 DB 세션과 가짜 Redis를 쓰는 클라이언트. 서버 시작 시드는 돌리지 않고 여기서 넣는다."""
    ensure_demo_user(db)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[login_lock.get_redis] = lambda: fake_redis
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def login(api_client):
    """아이디로 로그인(없으면 가입)하고 토큰을 돌려준다."""

    def _login(login_id: str, pin: str = "1234") -> str:
        r = api_client.post("/auth/login", json={"loginId": login_id, "pin": pin})
        assert r.status_code == 200, r.text
        return r.json()["token"]

    return _login
