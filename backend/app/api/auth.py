from fastapi import APIRouter, HTTPException

from app.api.schemas import ErrorResponse, LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])

EXISTING_USERS = {"demo"}


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    summary="아이디 + PIN 로그인 (없는 아이디면 가입)",
    description=(
        "mock 동작: PIN 9999 → 401, 아이디 locked → 429, 아이디 demo → 기존 사용자, "
        "그 외 아이디 → 새 사용자."
    ),
)
def login(body: LoginRequest):
    if body.login_id == "locked":
        raise HTTPException(429, "1분 후 다시 시도해 주세요")
    if body.pin == "9999":
        raise HTTPException(401, "아이디 또는 PIN이 틀렸어요")
    return LoginResponse(
        token=f"mock-token-{body.login_id}",
        is_new_user=body.login_id not in EXISTING_USERS,
    )
