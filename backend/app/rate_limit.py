"""요청 횟수 제한. 정해진 시간(window) 안에 같은 키로 limit번을 넘으면 막는다.

키는 Redis에 두고 window가 지나면 저절로 사라진다 (고정 창 방식).
"""

from redis import Redis


def hit(r: Redis, key: str, limit: int, window_seconds: int) -> bool:
    """요청을 1번 센다. 허용이면 True, 한도를 넘었으면 False."""
    full_key = f"rate:{key}"
    count = r.incr(full_key)
    if count == 1:
        r.expire(full_key, window_seconds)
    return count <= limit
