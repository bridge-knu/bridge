from fastapi import APIRouter, Depends, Request
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import login_lock, rate_limit
from app.api.errors import ApiError, responses
from app.api.schemas import LoginRequest, LoginResponse
from app.db import get_db
from app.models import Profile, User
from app.seed import create_trial_user
from app.security import create_token, hash_pin, verify_pin

router = APIRouter(prefix="/auth", tags=["auth"])

# 같은 IP에서 여러 아이디를 돌아가며 시도하거나 계정을 대량으로 만드는 것을 막는다.
# 사지방처럼 여러 명이 IP 하나를 같이 쓰는 경우를 생각해서 넉넉하게 잡는다.
LOGIN_PER_IP = (60, 60)  # 1분에 60번
SIGNUP_PER_IP = (30, 3600)  # 1시간에 새 계정 30개
# 체험 계정은 심사장처럼 여러 명이 같은 와이파이(IP 하나)에서 누를 수 있어서 따로, 더 넉넉하게 센다.
TRIAL_PER_IP = (300, 3600)  # 1시간에 체험 계정 300개


def client_ip(request: Request) -> str:
    # 배포에서는 Caddy가 넘겨준 실제 접속 IP (uvicorn --proxy-headers)
    return request.client.host if request.client else "unknown"

@router.post(
    "/login",
    response_model=LoginResponse,
    responses=responses("WRONG_PIN", "LOGIN_LOCKED", "TOO_MANY_REQUESTS", "SERVICE_UNAVAILABLE"),
    summary="아이디 + PIN 로그인 (없는 아이디면 가입)",
    description=(
        "없는 아이디면 그 PIN으로 가입한다. isNewUser는 프로필을 아직 입력하지 않았으면 true. "
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
    # 가입만 하고 프로필 입력 전에 나간 사용자도 다시 프로필 화면으로 보낸다.
    needs_profile = is_new or db.get(Profile, user.id) is None
    return LoginResponse(token=create_token(user.id), is_new_user=needs_profile)


@router.post(
    "/demo",
    response_model=LoginResponse,
    responses=responses("TOO_MANY_REQUESTS", "SERVICE_UNAVAILABLE"),
    summary="체험 계정 만들기",
    description=(
        "데모 데이터(프로필 + 진단 결과)를 채운 체험 계정(demo-xxxxxx)을 새로 만들고 토큰을 준다. "
        "누를 때마다 다른 계정이라 여러 명이 동시에 써도 서로 결과가 바뀌지 않는다. "
        "isNewUser는 항상 false (프로필이 이미 있음). 같은 IP에서 1시간에 300개까지."
    ),
)
def demo(
    request: Request,
    db: Session = Depends(get_db),
    r: Redis = Depends(login_lock.get_redis),
):
    if not rate_limit.hit(r, f"trial:{client_ip(request)}", *TRIAL_PER_IP):
        raise ApiError("TOO_MANY_REQUESTS")
    user = create_trial_user(db)
    return LoginResponse(token=create_token(user.id), is_new_user=False)
