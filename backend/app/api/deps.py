"""여러 라우터가 같이 쓰는 의존성."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db import get_db
from app.models import User
from app.security import read_token

# 공용 데모 계정 아이디 (app.seed가 이 값으로 만든다).
# 여러 명이 같이 쓰므로 프로필 저장·진단 다시 시작을 막는다. 체험 계정(demo-xxxxxx)은 막지 않는다.
DEMO_LOGIN_ID = "demo"

# /docs 오른쪽 위 Authorize 버튼에 토큰을 넣으면 모든 요청에 붙는다.
bearer = HTTPBearer(auto_error=False, description="/auth/login 으로 받은 token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Authorization: Bearer <token> 을 확인한다. 없거나 만료·위조면 401."""
    user_id = read_token(credentials.credentials) if credentials else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise ApiError("UNAUTHORIZED", headers={"WWW-Authenticate": "Bearer"})
    return user
