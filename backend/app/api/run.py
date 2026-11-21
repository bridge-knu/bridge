import time
import uuid

from fastapi import APIRouter, Depends
from redis import Redis

from app import rate_limit, run_queue
from app.api.blocks import get_block_or_404
from app.api.deps import get_current_user
from app.api.errors import ApiError, responses
from app.api.schemas import RunAccepted, RunRequest, RunResult
from app.login_lock import get_redis
from app.content import get_graph
from app.models import User

router = APIRouter(prefix="/run", tags=["run"])

# 큐에 이만큼 쌓여 있으면 새 요청을 받지 않는다 (워커 4개 기준 수십 초 분량)
MAX_QUEUE = 100
# 한 사람이 실행 대기열을 독차지하지 못하게 한다 (1분에 20번)
RUNS_PER_USER = (20, 60)


def is_stale(job: dict, now: float) -> bool:
    """워커가 죽는 등으로 끝나지 않을 작업인지. 맞으면 화면이 계속 기다리지 않게 실패로 돌려준다.

    - 대기 중: 워커는 QUEUE_TIMEOUT보다 오래 기다린 작업을 실행하지 않으므로 그 뒤로는 실패
    - 실행 중: 실행을 시작하고 RUN_TIMEOUT이 지나도 결과가 없으면 실패
    """
    if job["status"] == "queued":
        return now - job["createdAt"] > run_queue.QUEUE_TIMEOUT_SECONDS
    return now - job.get("startedAt", job["createdAt"]) > run_queue.RUN_TIMEOUT_SECONDS


def normalize_output(text: str) -> str:
    """정답 비교용. 줄 끝 공백·윈도우 줄바꿈·마지막 빈 줄 차이는 무시한다."""
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")


@router.post(
    "",
    response_model=RunAccepted,
    status_code=202,
    responses=responses("BLOCK_NOT_FOUND", "TOO_MANY_REQUESTS", "SERVICE_UNAVAILABLE"),
    summary="코드 실행 요청 → jobId",
    description=(
        "작업을 큐에 넣고 바로 jobId를 돌려준다. 워커가 샌드박스 컨테이너에서 실행한다. "
        "제한: 실행 5초, 메모리 128MB, 출력 64KB, 네트워크 차단."
    ),
)
def run(body: RunRequest, user: User = Depends(get_current_user), r: Redis = Depends(get_redis)):
    if body.block_id is not None:
        get_block_or_404(body.block_id)
    if not rate_limit.hit(r, f"run:{user.id}", *RUNS_PER_USER):
        raise ApiError("TOO_MANY_REQUESTS")
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
        if is_stale(job, time.time()):
            return RunResult(
                job_id=job_id,
                status="done",
                stderr=run_queue.EXPIRED_MESSAGE,
                exit_code=1,
                matches_expected=False if job["blockId"] else None,
            )
        return RunResult(job_id=job_id, status=job["status"])

    out = job["result"]
    matches = None
    block = get_graph().blocks.get(job["blockId"]) if job["blockId"] else None
    if block is not None:
        expected = block.practice.expected
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
