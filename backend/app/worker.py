"""코드 실행 워커. `python -m app.worker`로 띄운다.

Redis 큐에서 작업을 꺼내 작업마다 새 샌드박스 컨테이너(sandbox/)에서 실행하고
결과를 Redis에 적는다. 동시에 최대 4개를 실행하고 나머지는 큐에서 기다린다.

컨테이너 제한 (개발 가이드 7장)
- 네트워크 차단, 메모리 128MB, CPU 0.5개, 프로세스 64개
- 루트 파일 시스템 읽기 전용, 쓰기는 /tmp(16MB)만
- 일반 사용자(1000)로 실행, 권한 상승 금지
- 실행 5초·출력 64KB 제한은 컨테이너 안의 runner.py가 건다
"""

import json
import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable

from redis import Redis
from redis.exceptions import RedisError

from app import run_queue
from app.login_lock import get_redis

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "bridge-sandbox")
CONCURRENCY = 4
# 컴파일 10초 + 실행 5초 + 컨테이너 시작 시간. 이 안에 끝나지 않으면 컨테이너를 강제로 지운다.
CONTAINER_TIMEOUT = 30

log = logging.getLogger("worker")


def docker_command(name: str) -> list[str]:
    return [
        "docker", "run", "-i", "--rm", "--name", name,
        "--network", "none",
        "--memory", "128m", "--memory-swap", "128m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--read-only",
        "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=16m",
        "--user", "1000:1000",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        SANDBOX_IMAGE,
    ]


def failure(message: str) -> dict:
    return {"stdout": "", "stderr": message, "exitCode": 1, "timedOut": False, "durationMs": 0}


def run_in_container(job: dict) -> dict:
    """샌드박스 컨테이너 하나로 작업을 실행하고 runner.py의 결과를 돌려준다."""
    name = f"bridge-run-{job['jobId']}"
    payload = json.dumps({"lang": job["lang"], "code": job["code"], "stdin": job.get("stdin", "")})
    try:
        proc = subprocess.run(
            docker_command(name), input=payload.encode(), capture_output=True, timeout=CONTAINER_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        return {**failure("시간 초과"), "exitCode": 124, "timedOut": True}

    try:
        return json.loads(proc.stdout)
    except ValueError:
        # runner.py가 결과를 못 내고 죽은 경우. 137은 메모리 초과로 컨테이너가 종료된 것
        if proc.returncode == 137:
            return {**failure("메모리 제한(128MB)을 넘어 강제 종료됐어요"), "exitCode": 137}
        log.error("sandbox failed (%s): %s", proc.returncode, proc.stderr.decode(errors="replace")[-500:])
        return failure("실행 환경 오류: 잠시 후 다시 시도해 주세요")


def process(r: Redis, job_id: str, execute: Callable[[dict], dict] = run_in_container) -> None:
    job = run_queue.load(r, job_id)
    if job is None:  # 1시간이 지나 지워진 작업
        return
    job["status"] = "running"
    run_queue.save(r, job)
    try:
        outcome = execute(job)
    except Exception:
        log.exception("job %s failed", job_id)
        outcome = failure("실행 환경 오류: 잠시 후 다시 시도해 주세요")
    job.update(status="done", result=outcome, code="")  # 결과가 나오면 코드는 지운다
    run_queue.save(r, job)


def loop(r: Redis, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            item = r.blpop([run_queue.QUEUE_KEY], timeout=5)
            if item:
                process(r, item[1])
        except RedisError:
            log.warning("redis 연결 실패, 2초 후 다시 시도")
            time.sleep(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    r = get_redis()
    stop = threading.Event()
    threads = [threading.Thread(target=loop, args=(r, stop), daemon=True) for _ in range(CONCURRENCY)]
    for t in threads:
        t.start()
    log.info("worker started: image=%s concurrency=%d", SANDBOX_IMAGE, CONCURRENCY)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
