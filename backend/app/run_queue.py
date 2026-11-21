"""코드 실행 작업 큐. API가 작업을 넣고 워커(app.worker)가 꺼내서 실행한다.

- 작업 목록: Redis 리스트 run:queue (작업 id)
- 작업 내용·결과: run:job:{id} (JSON, 1시간 뒤 자동 삭제)

상태는 queued → running → done 순서로 바뀐다.
"""

import json

from redis import Redis

QUEUE_KEY = "run:queue"
JOB_TTL_SECONDS = 3600

# 대기열에서 이보다 오래 기다린 작업은 워커가 실행하지 않고 실패로 끝낸다
QUEUE_TIMEOUT_SECONDS = 60
# 실행을 시작하고 이 시간 안에 결과가 없으면(워커가 죽은 경우 등) API가 실패로 돌려준다.
# 워커의 컨테이너 제한 시간(30초)보다 길게 잡는다
RUN_TIMEOUT_SECONDS = 45
EXPIRED_MESSAGE = "실행이 너무 오래 걸려 중단됐어요. 다시 실행해 주세요"


def job_key(job_id: str) -> str:
    return f"run:job:{job_id}"


def enqueue(r: Redis, job: dict) -> None:
    r.set(job_key(job["jobId"]), json.dumps(job), ex=JOB_TTL_SECONDS)
    r.rpush(QUEUE_KEY, job["jobId"])


def load(r: Redis, job_id: str) -> dict | None:
    raw = r.get(job_key(job_id))
    return json.loads(raw) if raw else None


def save(r: Redis, job: dict) -> None:
    r.set(job_key(job["jobId"]), json.dumps(job), ex=JOB_TTL_SECONDS)


def queue_length(r: Redis) -> int:
    return r.llen(QUEUE_KEY)
