import time
import uuid

from fastapi import APIRouter, Depends
from redis import Redis

from app import run_queue
from app.api.blocks import get_block_or_404
from app.api.deps import get_current_user
from app.api.mock_data import BLOCK_BY_ID
from app.api.errors import ApiError, responses
from app.api.schemas import RunAccepted, RunRequest, RunResult
from app.login_lock import get_redis
from app.models import User

router = APIRouter(prefix="/run", tags=["run"])

# 큐에 이만큼 쌓여 있으면 새 요청을 받지 않는다 (워커 4개 기준 수십 초 분량)
MAX_QUEUE = 100
# 워커가 죽는 등으로 이 시간 안에 끝나지 않은 작업은 실패로 돌려줘서 화면이 계속 기다리지 않게 한다
STALE_SECONDS = 90


def normalize_output(text: str) -> str:
    """정답 비교용. 줄 끝 공백·윈도우 줄바꿈·마지막 빈 줄 차이는 무시한다."""
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")


@router.post(
    "",
    response_model=RunAccepted,
    status_code=202,
    responses=responses("BLOCK_NOT_FOUND", "SERVICE_UNAVAILABLE"),
    summary="코드 실행 요청 → jobId",
    description=(
        "작업을 큐에 넣고 바로 jobId를 돌려준다. 워커가 샌드박스 컨테이너에서 실행한다. "
        "제한: 실행 5초, 메모리 128MB, 출력 64KB, 네트워크 차단."
    ),
)
def run(body: RunRequest, user: User = Depends(get_current_user), r: Redis = Depends(get_redis)):
    if body.block_id is not None:
        get_block_or_404(body.block_id)
    if run_queue.queue_length(r) >= MAX_QUEUE:
        raise ApiError("SERVICE_UNAVAILABLE")
    job_id = uuid.uuid4().hex
    run_queue.enqueue(
        r,
        {
            "jobId": job_id,
            "userId": user.id,
            "status": "queued",
            "lang": body.lang,
            "code": body.code,
            "stdin": body.stdin,
            "blockId": body.block_id,
            "createdAt": time.time(),
        },
    )
    return RunAccepted(job_id=job_id)


@router.get(
    "/{job_id}",
    response_model=RunResult,
    responses=responses("JOB_NOT_FOUND"),
    summary="실행 결과 (출력, 에러, 시간 초과)",
    description="프론트는 status가 done이 될 때까지 0.5초마다 호출한다. 결과는 1시간 동안 보관한다.",
)
def result(job_id: str, user: User = Depends(get_current_user), r: Redis = Depends(get_redis)):
    job = run_queue.load(r, job_id)
    if job is None or job["userId"] != user.id:
        raise ApiError("JOB_NOT_FOUND")
    if job["status"] != "done":
        if time.time() - job["createdAt"] > STALE_SECONDS:
            return RunResult(
                job_id=job_id,
                status="done",
                stderr="실행이 너무 오래 걸려 중단됐어요. 다시 실행해 주세요",
                exit_code=1,
                matches_expected=False if job["blockId"] else None,
            )
        return RunResult(job_id=job_id, status=job["status"])

    out = job["result"]
    matches = None
    block = BLOCK_BY_ID.get(job["blockId"]) if job["blockId"] else None
    if block is not None:
        expected = block["practice"]["expected"]
        matches = (
            out["exitCode"] == 0
            and not out["timedOut"]
            and normalize_output(out["stdout"]) == normalize_output(expected)
        )
    return RunResult(
        job_id=job_id,
        status="done",
        stdout=out["stdout"],
        stderr=out["stderr"],
        exit_code=out["exitCode"],
        timed_out=out["timedOut"],
        duration_ms=out["durationMs"],
        matches_expected=matches,
    )
