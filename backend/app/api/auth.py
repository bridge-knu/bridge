from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import login_lock
from app.api.schemas import ErrorResponse, LoginRequest, LoginResponse
from app.db import get_db
from app.models import User
from app.security import create_token, hash_pin, verify_pin

router = APIRouter(prefix="/auth", tags=["auth"])

WRONG_PIN = "아이디 또는 PIN이 틀렸어요"
LOCKED = "1분 후 다시 시도해 주세요"


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="아이디 + PIN 로그인 (없는 아이디면 가입)",
    description=(
        "없는 아이디면 그 PIN으로 가입하고 isNewUser=true. "
        "같은 아이디로 PIN을 5번 틀리면 1분 동안 429. 데모 계정은 demo / 0000."
    ),
)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    r: Redis = Depends(login_lock.get_redis),
):
    if login_lock.is_locked(r, body.login_id):
        raise HTTPException(429, LOCKED)

    user = db.scalar(select(User).where(User.login_id == body.login_id))
    is_new = user is None

    if is_new:
        user = User(login_id=body.login_id, pin_hash=hash_pin(body.pin))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # 같은 아이디로 동시에 가입한 경우: 먼저 만든 계정으로 로그인을 다시 시도하게 한다.
            db.rollback()
            raise HTTPException(401, WRONG_PIN) from None
    elif not verify_pin(body.pin, user.pin_hash):
        if login_lock.record_failure(r, body.login_id):
            raise HTTPException(429, LOCKED)
        raise HTTPException(401, WRONG_PIN)

    login_lock.clear_failures(r, body.login_id)
    return LoginResponse(token=create_token(user.id), is_new_user=is_new)
