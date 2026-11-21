"""로그인 실패 잠금. 같은 아이디로 PIN을 5번 틀리면 1분 동안 로그인을 막는다.

실패 횟수와 잠금은 Redis에 두고, 시간이 지나면 키가 저절로 사라진다.
"""

import os

from redis import Redis

MAX_FAILURES = 5
LOCK_SECONDS = 60
FAILURE_WINDOW_SECONDS = 600  # 실패 횟수는 마지막 실패 후 10분 동안만 센다

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    return _redis


def _fail_key(login_id: str) -> str:
    return f"login:fail:{login_id}"


def _lock_key(login_id: str) -> str:
    return f"login:lock:{login_id}"


def is_locked(r: Redis, login_id: str) -> bool:
    return bool(r.exists(_lock_key(login_id)))


def record_failure(r: Redis, login_id: str) -> bool:
    """실패를 기록한다. 이번 실패로 잠기면 True."""
    key = _fail_key(login_id)
    count = r.incr(key)
    r.expire(key, FAILURE_WINDOW_SECONDS)
    if count >= MAX_FAILURES:
        r.set(_lock_key(login_id), 1, ex=LOCK_SECONDS)
        r.delete(key)
        return True
    return False


def clear_failures(r: Redis, login_id: str) -> None:
    r.delete(_fail_key(login_id))
