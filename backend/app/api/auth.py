from fastapi import APIRouter, Depends, Request
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import login_lock, rate_limit
from app.api.errors import ApiError, responses
from app.api.schemas import LoginRequest, LoginResponse
from app.db import get_db
from app.models import User
from app.security import create_token, hash_pin, verify_pin

router = APIRouter(prefix="/auth", tags=["auth"])

# 같은 IP에서 여러 아이디를 돌아가며 시도하거나 계정을 대량으로 만드는 것을 막는다.
# 사지방처럼 여러 명이 IP 하나를 같이 쓰는 경우를 생각해서 넉넉하게 잡는다.
LOGIN_PER_IP = (60, 60)  # 1분에 60번
SIGNUP_PER_IP = (30, 3600)  # 1시간에 새 계정 30개


def client_ip(request: Request) -> str:
    # 배포에서는 Caddy가 넘겨준 실제 접속 IP (uvicorn --proxy-headers)
    return request.client.host if request.client else "unknown"

@router.post(
    "/login",
    response_model=LoginResponse,
    responses=responses("WRONG_PIN", "LOGIN_LOCKED", "TOO_MANY_REQUESTS", "SERVICE_UNAVAILABLE"),
    summary="아이디 + PIN 로그인 (없는 아이디면 가입)",
    description=(
        "없는 아이디면 그 PIN으로 가입하고 isNewUser=true. "
        "같은 아이디로 PIN을 5번 틀리면 1분 동안 429. 데모 계정은 demo / 0000."
    ),
)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    r: Redis = Depends(login_lock.get_redis),
):
    ip = client_ip(request)
    if not rate_limit.hit(r, f"login:{ip}", *LOGIN_PER_IP):
        raise ApiError("TOO_MANY_REQUESTS")
    if login_lock.is_locked(r, body.login_id):
        raise ApiError("LOGIN_LOCKED")

    user = db.scalar(select(User).where(User.login_id == body.login_id))
    is_new = user is None

    if is_new:
        if not rate_limit.hit(r, f"signup:{ip}", *SIGNUP_PER_IP):
            raise ApiError("TOO_MANY_REQUESTS")
        user = User(login_id=body.login_id, pin_hash=hash_pin(body.pin))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # 같은 아이디로 동시에 가입한 경우: 먼저 만든 계정으로 로그인을 다시 시도하게 한다.
            db.rollback()
            raise ApiError("WRONG_PIN") from None
    elif not verify_pin(body.pin, user.pin_hash):
        if login_lock.record_failure(r, body.login_id):
            raise ApiError("LOGIN_LOCKED")
        raise ApiError("WRONG_PIN")

    login_lock.clear_failures(r, body.login_id)
    return LoginResponse(token=create_token(user.id), is_new_user=is_new)
