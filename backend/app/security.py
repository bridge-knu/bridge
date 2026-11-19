"""PIN 해시와 로그인 토큰(JWT)."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 12  # 사지방 하루 사용 기준. 만료되면 다시 로그인한다.
BCRYPT_ROUNDS = 12  # 테스트에서는 속도를 위해 낮춘다 (tests/conftest.py)


def jwt_secret() -> str:
    # 배포 환경에서는 .env의 JWT_SECRET을 반드시 긴 임의 문자열로 바꾼다.
    return os.environ.get("JWT_SECRET", "dev-only-secret-change-me")


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def read_token(token: str) -> int | None:
    """토큰이 올바르면 user_id, 만료·위조·형식 오류면 None."""
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
