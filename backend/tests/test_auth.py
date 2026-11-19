from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app import login_lock
from app.models import User
from app.security import JWT_ALGORITHM, jwt_secret, verify_pin

WRONG_PIN = {"detail": "아이디 또는 PIN이 틀렸어요"}
LOCKED = {"detail": "1분 후 다시 시도해 주세요"}
UNAUTHORIZED = {"detail": "다시 로그인해 주세요"}


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


def test_second_login_is_existing_user(api_client):
    post_login(api_client, "kim", "1234")
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
