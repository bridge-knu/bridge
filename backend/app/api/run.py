import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.blocks import get_block_or_404
from app.api.deps import get_current_user
from app.api.mock_data import BLOCK_BY_ID, JOBS, Job
from app.api.schemas import ErrorResponse, RunAccepted, RunRequest, RunResult
from app.models import User

router = APIRouter(prefix="/run", tags=["run"])

MOCK_RUN_SECONDS = 1.0
INFINITE_LOOP = re.compile(r"while\s*\(\s*1\s*\)|for\s*\(\s*;\s*;\s*\)|while\s+True")


@router.post(
    "",
    response_model=RunAccepted,
    status_code=202,
    responses={404: {"model": ErrorResponse}},
    summary="코드 실행 요청 → jobId",
    description=(
        "mock은 실제로 실행하지 않는다. 1초 동안 running 상태였다가 결과가 나온다. "
        "코드에 while(1)/for(;;)/while True → 시간 초과, COMPILE_ERROR → 컴파일 에러, "
        "그 외에는 blockId가 있으면 정답 출력, 없으면 hello."
    ),
)
def run(body: RunRequest, user: User = Depends(get_current_user)):
    if body.block_id is not None:
        get_block_or_404(body.block_id)
    job_id = uuid.uuid4().hex
    JOBS[job_id] = Job(job_id, user.id, time.monotonic(), body.lang, body.code, body.block_id)
    return RunAccepted(job_id=job_id)


@router.get(
    "/{job_id}",
    response_model=RunResult,
    responses={404: {"model": ErrorResponse}},
    summary="실행 결과 (출력, 에러, 시간 초과)",
    description="프론트는 status가 done이 될 때까지 0.5초마다 호출한다.",
)
def result(job_id: str, user: User = Depends(get_current_user)):
    job = JOBS.get(job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "실행 작업을 찾을 수 없어요")
    if time.monotonic() - job.created < MOCK_RUN_SECONDS:
        return RunResult(job_id=job_id, status="running")

    expected = BLOCK_BY_ID[job.block_id]["practice"]["expected"] if job.block_id else None
    failed = False if expected is not None else None

    if INFINITE_LOOP.search(job.code):
        return RunResult(
            job_id=job_id,
            status="done",
            stderr="시간 초과 (5초)",
            exit_code=124,
            timed_out=True,
            duration_ms=5000,
            matches_expected=failed,
        )
    if "COMPILE_ERROR" in job.code:
        return RunResult(
            job_id=job_id,
            status="done",
            stderr="main.c:3:5: error: expected ';' before 'return'",
            exit_code=1,
            duration_ms=120,
            matches_expected=failed,
        )
    return RunResult(
        job_id=job_id,
        status="done",
        stdout=expected if expected is not None else "hello\n",
        exit_code=0,
        duration_ms=35,
        matches_expected=True if expected is not None else None,
    )
