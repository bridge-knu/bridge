from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import login_lock
from app.models import User
from app.main import app
from app.security import JWT_ALGORITHM, JwtSecretError, jwt_secret, verify_pin

WRONG_PIN = {"detail": "아이디 또는 PIN이 틀렸어요", "code": "WRONG_PIN"}
LOCKED = {"detail": "1분 후 다시 시도해 주세요", "code": "LOGIN_LOCKED"}
UNAUTHORIZED = {"detail": "다시 로그인해 주세요", "code": "UNAUTHORIZED"}


def post_login(client, login_id, pin):
    return client.post("/auth/login", json={"loginId": login_id, "pin": pin})


# ---- 가입·로그인 ----


def test_new_id_signs_up(api_client, db):
    r = post_login(api_client, "kim", "1234")
    assert r.status_code == 200
    assert r.json()["isNewUser"] is True
    user = db.scalar(select(User).where(User.login_id == "kim"))
    assert user.pin_hash != "1234"
    assert verify_pin("1234", user.pin_hash)


def test_is_new_user_until_profile_saved(api_client):
    token = post_login(api_client, "kim", "1234").json()["token"]
    # 가입만 하고 프로필 입력 전에 나갔다면 다시 프로필 화면으로
    assert post_login(api_client, "kim", "1234").json()["isNewUser"] is True

    profile = {"completedCourses": [], "gapMonths": 12, "targetCourse": "DS",
               "returnDate": "2027-03-02", "dailyMinutes": 60}
    api_client.put("/profile", json=profile, headers={"Authorization": f"Bearer {token}"})
    r = post_login(api_client, "kim", "1234")
    assert r.status_code == 200
    assert r.json()["isNewUser"] is False


def test_demo_account_is_seeded(api_client):
    r = post_login(api_client, "demo", "0000")
    assert r.status_code == 200
    assert r.json()["isNewUser"] is False


def test_wrong_pin(api_client):
    post_login(api_client, "kim", "1234")
    r = post_login(api_client, "kim", "9999")
    assert r.status_code == 401
    assert r.json() == WRONG_PIN


@pytest.mark.parametrize("login_id", ["kim\u0000", "kim\nlee", "\ttab", "del\u007f"])
def test_login_id_rejects_control_characters(api_client, login_id):
    assert post_login(api_client, login_id, "1234").status_code == 422


def test_login_id_allows_korean_and_symbols(api_client):
    assert post_login(api_client, "상민_kim-01", "1234").status_code == 200


@pytest.mark.parametrize("pin", ["123", "12345", "abcd"])
def test_pin_must_be_4_digits(api_client, pin):
    assert post_login(api_client, "kim", pin).status_code == 422


# ---- 5번 틀리면 1분 잠금 ----


def test_locked_after_5_failures(api_client):
    post_login(api_client, "kim", "1234")
    codes = [post_login(api_client, "kim", "0000").status_code for _ in range(5)]
    assert codes == [401, 401, 401, 401, 429]

    r = post_login(api_client, "kim", "1234")  # 맞는 PIN도 잠금 중에는 거부
    assert r.status_code == 429
    assert r.json() == LOCKED


def test_lock_lasts_1_minute(api_client, fake_redis):
    post_login(api_client, "kim", "1234")
    for _ in range(5):
        post_login(api_client, "kim", "0000")
    assert 0 < fake_redis.ttl("login:lock:kim") <= login_lock.LOCK_SECONDS

    fake_redis.delete("login:lock:kim")  # 1분이 지난 상황
    assert post_login(api_client, "kim", "1234").status_code == 200


def test_success_resets_failure_count(api_client):
    post_login(api_client, "kim", "1234")
    for _ in range(4):
        post_login(api_client, "kim", "0000")
    assert post_login(api_client, "kim", "1234").status_code == 200
    codes = [post_login(api_client, "kim", "0000").status_code for _ in range(4)]
    assert codes == [401, 401, 401, 401]


def test_lock_is_per_login_id(api_client):
    post_login(api_client, "kim", "1234")
    for _ in range(5):
        post_login(api_client, "kim", "0000")
    assert post_login(api_client, "demo", "0000").status_code == 200


# ---- 토큰 ----


def test_token_opens_protected_api(api_client, login):
    token = login("kim")
    r = api_client.post("/diagnosis/start", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


@pytest.mark.parametrize(
    "header",
    [None, "Bearer", "Bearer not-a-token", "Basic abc", "mock-token-kim"],
)
def test_missing_or_bad_token_is_401(api_client, header):
    headers = {"Authorization": header} if header else {}
    r = api_client.post("/diagnosis/start", headers=headers)
    assert r.status_code == 401
    assert r.json() == UNAUTHORIZED


def test_expired_token_is_401(api_client, login, db):
    login("kim")
    user = db.scalar(select(User).where(User.login_id == "kim"))
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = jwt.encode({"sub": str(user.id), "exp": past}, jwt_secret(), algorithm=JWT_ALGORITHM)
    r = api_client.get("/plan", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_token_signed_with_other_secret_is_401(api_client, login, db):
    login("kim")
    user = db.scalar(select(User).where(User.login_id == "kim"))
    forged = jwt.encode({"sub": str(user.id)}, "other-secret", algorithm=JWT_ALGORITHM)
    assert api_client.get("/plan", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("put", "/profile"),
        ("post", "/diagnosis/start"),
        ("post", "/diagnosis/answer"),
        ("get", "/diagnosis/result"),
        ("post", "/plan/generate"),
        ("get", "/plan"),
        ("get", "/blocks/b-array-1"),
        ("put", "/code/b-array-1"),
        ("post", "/run"),
        ("get", "/run/x"),
        ("post", "/blocks/b-array-1/complete"),
    ],
)
def test_all_apis_except_login_need_token(api_client, method, path):
    assert api_client.request(method, path, json={}).status_code == 401


# ---- 서명 키·필수 클레임 (토큰 위조 방지) ----


def demo_user_id(db) -> int:
    return db.scalar(select(User.id).where(User.login_id == "demo"))


@pytest.mark.parametrize("secret", ["dev-only-secret-change-me", "change-me"])
def test_token_signed_with_public_secret_is_401(api_client, db, secret):
    now = datetime.now(timezone.utc)
    claims = {"sub": str(demo_user_id(db)), "iat": now, "exp": now + timedelta(hours=1)}
    forged = jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)
    assert api_client.get("/plan", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


@pytest.mark.parametrize("missing", ["exp", "iat", "sub"])
def test_token_without_required_claim_is_401(api_client, db, missing):
    now = datetime.now(timezone.utc)
    claims = {"sub": str(demo_user_id(db)), "iat": now, "exp": now + timedelta(hours=1)}
    del claims[missing]
    token = jwt.encode(claims, jwt_secret(), algorithm=JWT_ALGORITHM)
    assert api_client.get("/plan", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("value", [None, "", "change-me", "dev-only-secret-change-me", "short-secret"])
def test_unsafe_jwt_secret_is_rejected(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("JWT_SECRET", raising=False)
    else:
        monkeypatch.setenv("JWT_SECRET", value)
    with pytest.raises(JwtSecretError):
        jwt_secret()


def test_server_does_not_start_with_unsafe_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "change-me")
    with pytest.raises(JwtSecretError):
        with TestClient(app):
            pass


# ---- DB·Redis 장애 ----


def test_redis_down_is_503(api_client):
    from redis import Redis

    down = Redis.from_url("redis://localhost:1/0", socket_connect_timeout=0.2)
    app.dependency_overrides[login_lock.get_redis] = lambda: down
    r = post_login(api_client, "kim", "1234")
    assert r.status_code == 503
    assert r.json() == {"detail": "잠시 후 다시 시도해 주세요", "code": "SERVICE_UNAVAILABLE"}


def test_db_down_is_503(api_client):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db import get_db

    down = create_engine("postgresql+psycopg://x:x@localhost:1/x", connect_args={"connect_timeout": 1})

    def broken_db():
        with Session(down) as s:
            yield s

    app.dependency_overrides[get_db] = broken_db
    r = post_login(api_client, "kim", "1234")
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"


# ---- IP별 횟수 제한 ----


def test_login_rate_limit_per_ip(api_client, monkeypatch):
    from app.api import auth

    monkeypatch.setattr(auth, "LOGIN_PER_IP", (3, 60))
    codes = [post_login(api_client, f"user{i}", "1234").status_code for i in range(4)]
    assert codes == [200, 200, 200, 429]
    assert post_login(api_client, "demo", "0000").json()["code"] == "TOO_MANY_REQUESTS"


def test_signup_rate_limit_per_ip(api_client, monkeypatch):
    from app.api import auth

    monkeypatch.setattr(auth, "SIGNUP_PER_IP", (2, 3600))
    assert post_login(api_client, "a1", "1234").status_code == 200
    assert post_login(api_client, "a2", "1234").status_code == 200
    r = post_login(api_client, "a3", "1234")
    assert r.status_code == 429
    assert r.json()["code"] == "TOO_MANY_REQUESTS"
    # 이미 있는 계정 로그인은 계속 된다
    assert post_login(api_client, "a1", "1234").status_code == 200


def test_rate_limit_window_expires(fake_redis):
    from app import rate_limit

    assert rate_limit.hit(fake_redis, "x", 1, 60)
    assert not rate_limit.hit(fake_redis, "x", 1, 60)
    assert 0 < fake_redis.ttl("rate:x") <= 60
    fake_redis.delete("rate:x")  # 1분이 지난 상황
    assert rate_limit.hit(fake_redis, "x", 1, 60)


def test_docs_can_be_disabled(monkeypatch):
    import importlib

    import app.main as main

    monkeypatch.setenv("DISABLE_DOCS", "1")
    off = importlib.reload(main).app
    paths = {r.path for r in off.routes}
    assert "/docs" not in paths and "/openapi.json" not in paths
    monkeypatch.delenv("DISABLE_DOCS")
    importlib.reload(main)
