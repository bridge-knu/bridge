"""API 오류 응답. 모든 오류는 {"detail": "안내 문구", "code": "오류 코드"} 형태다.

화면은 code로 분기하고, detail은 그대로 사용자에게 보여 준다.
입력값 검증 실패(422)는 FastAPI 기본 형태를 그대로 쓴다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

from app.api.schemas import ErrorResponse

# 코드: (상태, 안내 문구)
ERRORS: dict[str, tuple[int, str]] = {
    "UNAUTHORIZED": (401, "다시 로그인해 주세요"),
    "WRONG_PIN": (401, "아이디 또는 PIN이 틀렸어요"),
    "LOGIN_LOCKED": (429, "1분 후 다시 시도해 주세요"),
    "DIAGNOSIS_FINISHED": (400, "진단이 이미 끝났어요"),
    "QUESTION_MISMATCH": (400, "지금 풀고 있는 문제가 아니에요"),
    "DIAGNOSIS_NOT_FINISHED": (400, "진단을 먼저 끝내 주세요"),
    "BLOCK_NOT_FOUND": (404, "블록을 찾을 수 없어요"),
    "JOB_NOT_FOUND": (404, "실행 작업을 찾을 수 없어요"),
    "SERVICE_UNAVAILABLE": (503, "잠시 후 다시 시도해 주세요"),
    "TOO_MANY_REQUESTS": (429, "요청이 너무 많아요. 잠시 후 다시 시도해 주세요"),
    "DEMO_READ_ONLY": (403, "공용 데모 계정은 프로필을 바꿀 수 없어요. 체험하기로 나만의 계정을 만들어 보세요"),
}


class ApiError(Exception):
    def __init__(self, code: str, headers: dict[str, str] | None = None):
        self.code = code
        self.status_code, self.detail = ERRORS[code]
        self.headers = headers


def error_response(code: str, headers: dict[str, str] | None = None) -> JSONResponse:
    status, detail = ERRORS[code]
    return JSONResponse({"detail": detail, "code": code}, status_code=status, headers=headers)


def responses(*codes: str) -> dict:
    """라우터 responses= 에 넣을 /docs 설명. 같은 상태 코드의 오류는 한 줄로 묶는다."""
    by_status: dict[int, list[str]] = {}
    for code in codes:
        by_status.setdefault(ERRORS[code][0], []).append(code)
    return {
        status: {"model": ErrorResponse, "description": ", ".join(cs)}
        for status, cs in by_status.items()
    }


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.code, exc.headers)

    # DB나 Redis에 연결할 수 없을 때 500 대신 503으로 알린다.
    @app.exception_handler(RedisError)
    @app.exception_handler(OperationalError)
    async def _unavailable(_: Request, __: Exception):
        return error_response("SERVICE_UNAVAILABLE")
