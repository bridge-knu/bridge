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


# 컨테이너에서 받는 출력의 최대 크기. runner.py 결과 JSON은 출력 64KB × 2를 이스케이프해도 1MB 안에 든다.
# 학생 코드가 제한을 우회해 대량으로 쓰더라도 워커 메모리를 채우지 못하게 이만큼만 읽고 컨테이너를 지운다.
MAX_STDOUT_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024


def _drain(stream, limit: int, chunks: list[bytes], on_overflow: Callable[[], None]) -> None:
    """stream을 끝까지 읽되 limit까지만 모은다. 넘으면 on_overflow를 부른다."""
    total = 0
    while chunk := stream.read(65536):
        if total < limit:
            chunks.append(chunk[: limit - total])
        total += len(chunk)
        if total > limit:
            on_overflow()


def parse_result(raw: bytes) -> dict | None:
    """runner.py가 마지막에 쓴 결과 JSON을 꺼낸다. 앞에 다른 글자가 섞여 있어도 마지막 결과만 본다."""
    text = raw.decode("utf-8", errors="replace")
    start = text.rfind('{"stdout"')
    if start == -1:
        return None
    try:
        result = json.loads(text[start:])
    except ValueError:
        return None
    return result if isinstance(result, dict) else None


def run_in_container(job: dict) -> dict:
    """샌드박스 컨테이너 하나로 작업을 실행하고 runner.py의 결과를 돌려준다."""
    name = f"bridge-run-{job['jobId']}"
    payload = json.dumps({"lang": job["lang"], "code": job["code"], "stdin": job.get("stdin", "")})

    overflow = threading.Event()
    removed = threading.Lock()

    def remove_container() -> None:
        if removed.acquire(blocking=False):  # 한 번만
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    def on_overflow() -> None:
        if not overflow.is_set():
            overflow.set()
            remove_container()

    proc = subprocess.Popen(
        docker_command(name), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out: list[bytes] = []
    err: list[bytes] = []
    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, MAX_STDOUT_BYTES, out, on_overflow), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, MAX_STDERR_BYTES, err, on_overflow), daemon=True),
    ]
    for t in readers:
        t.start()
    try:
        proc.stdin.write(payload.encode())
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    try:
        proc.wait(timeout=CONTAINER_TIMEOUT)
        timed_out = False
    except subprocess.TimeoutExpired:
        remove_container()
        proc.wait()
        timed_out = True
    for t in readers:
        t.join(timeout=5)

    if overflow.is_set():
        return failure("출력이 너무 많아 실행을 중단했어요 (최대 64KB)")
    if timed_out:
        return {**failure("시간 초과"), "exitCode": 124, "timedOut": True}

    result = parse_result(b"".join(out))
    if result is not None:
        return result
    # runner.py가 결과를 못 내고 죽은 경우. 137은 메모리 초과로 컨테이너가 종료된 것
    if proc.returncode == 137:
        return {**failure("메모리 제한(128MB)을 넘어 강제 종료됐어요"), "exitCode": 137}
    log.error("sandbox failed (%s): %s", proc.returncode, b"".join(err).decode(errors="replace")[-500:])
    return failure("실행 환경 오류: 잠시 후 다시 시도해 주세요")


def process(r: Redis, job_id: str, execute: Callable[[dict], dict] = run_in_container) -> None:
    job = run_queue.load(r, job_id)
    if job is None:  # 1시간이 지나 지워진 작업
        return
    if time.time() - job["createdAt"] > run_queue.QUEUE_TIMEOUT_SECONDS:
        # 너무 오래 기다린 작업은 화면이 이미 실패로 보여 줬으므로 실행하지 않는다
        job.update(status="done", result=failure(run_queue.EXPIRED_MESSAGE), code="")
        run_queue.save(r, job)
        return
    job.update(status="running", startedAt=time.time())
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
