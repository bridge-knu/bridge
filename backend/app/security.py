"""PIN 해시와 로그인 토큰(JWT)."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 12  # 사지방 하루 사용 기준. 만료되면 다시 로그인한다.
BCRYPT_ROUNDS = 12  # 테스트에서는 속도를 위해 낮춘다 (tests/conftest.py)


MIN_SECRET_LENGTH = 32
# 저장소에 공개된 적 있는 값. 이 값으로 서명하면 누구나 토큰을 위조할 수 있다.
PUBLIC_SECRETS = {"change-me", "dev-only-secret-change-me"}


class JwtSecretError(RuntimeError):
    pass


def jwt_secret() -> str:
    """.env의 JWT_SECRET. 없거나, 짧거나, 공개된 값이면 서명·검증을 거부한다."""
    secret = os.environ.get("JWT_SECRET", "")
    if secret in PUBLIC_SECRETS or len(secret) < MIN_SECRET_LENGTH:
        raise JwtSecretError(
            f"JWT_SECRET이 없거나 안전하지 않습니다 ({MIN_SECRET_LENGTH}자 이상 임의 문자열 필요). "
            'python -c "import secrets; print(secrets.token_urlsafe(48))" 결과를 .env에 넣으세요.'
        )
    return secret


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
        payload = jwt.decode(
            token,
            jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
