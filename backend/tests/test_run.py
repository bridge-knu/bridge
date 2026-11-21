"""POST /run, GET /run/{jobId}와 워커의 큐 처리.

실제 컨테이너 실행 대신 가짜 실행 함수를 쓴다. 실제 샌드박스 테스트는 test_sandbox.py.
"""

import pytest

from app import run_queue, worker
from app.api import run


@pytest.fixture
def client(api_client, login):
    api_client.headers["Authorization"] = f"Bearer {login('tester')}"
    return api_client


def ok(stdout):
    return {"stdout": stdout, "stderr": "", "exitCode": 0, "timedOut": False, "durationMs": 12}


def submit(client, **payload):
    r = client.post("/run", json={"lang": "c", "code": "int main(){}", **payload})
    assert r.status_code == 202, r.text
    return r.json()["jobId"]


def work(fake_redis, execute):
    """워커가 큐에서 작업 하나를 꺼내 처리한 상황."""
    _, job_id = fake_redis.blpop([run_queue.QUEUE_KEY], timeout=1)
    worker.process(fake_redis, job_id, execute)
    return job_id


def test_run_is_queued_until_worker_picks_it(client, fake_redis):
    job_id = submit(client)
    assert client.get(f"/run/{job_id}").json() == {
        "jobId": job_id, "status": "queued", "stdout": "", "stderr": "", "exitCode": None,
        "timedOut": False, "durationMs": None, "matchesExpected": None,
    }
    assert run_queue.queue_length(fake_redis) == 1


def test_running_status_while_executing(client, fake_redis):
    seen = {}

    def execute(job):
        seen["status"] = client.get(f"/run/{job['jobId']}").json()["status"]
        return ok("")

    submit(client)
    work(fake_redis, execute)
    assert seen["status"] == "running"


def test_worker_receives_code_and_stdin(client, fake_redis):
    received = {}
    submit(client, lang="python", code="print(input())", stdin="hi\n")
    work(fake_redis, lambda job: received.update(job) or ok("hi\n"))
    assert (received["lang"], received["code"], received["stdin"]) == ("python", "print(input())", "hi\n")


def test_result_after_done(client, fake_redis):
    job_id = submit(client)
    work(fake_redis, lambda job: ok("hello\n"))
    res = client.get(f"/run/{job_id}").json()
    assert res["status"] == "done"
    assert res["stdout"] == "hello\n"
    assert res["exitCode"] == 0
    assert res["matchesExpected"] is None
    # 실행이 끝나면 Redis에 남은 코드는 지운다
    assert run_queue.load(fake_redis, job_id)["code"] == ""


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [("15\n", True), ("15", True), ("15  \r\n", True), ("16\n", False), ("", False)],
)
def test_matches_expected(client, fake_redis, stdout, expected):
    job_id = submit(client, blockId="b-array-1")  # 정답 출력 "15\n"
    work(fake_redis, lambda job: ok(stdout))
    assert client.get(f"/run/{job_id}").json()["matchesExpected"] is expected


def test_timeout_never_matches(client, fake_redis):
    job_id = submit(client, blockId="b-array-1")
    work(fake_redis, lambda job: {**ok("15\n"), "timedOut": True, "exitCode": 124})
    res = client.get(f"/run/{job_id}").json()
    assert res["timedOut"] is True
    assert res["matchesExpected"] is False


def test_worker_error_becomes_result(client, fake_redis):
    def boom(job):
        raise RuntimeError("docker not found")

    job_id = submit(client)
    work(fake_redis, boom)
    res = client.get(f"/run/{job_id}").json()
    assert res["status"] == "done"
    assert res["exitCode"] == 1
    assert "잠시 후" in res["stderr"]


def test_unknown_block_404(client):
    r = client.post("/run", json={"lang": "c", "code": "x", "blockId": "nope"})
    assert r.status_code == 404


def test_unknown_job_404(client):
    r = client.get("/run/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "실행 작업을 찾을 수 없어요", "code": "JOB_NOT_FOUND"}


def test_job_of_other_user_is_hidden(client, login):
    job_id = submit(client)
    other = {"Authorization": f"Bearer {login('other')}"}
    assert client.get(f"/run/{job_id}", headers=other).status_code == 404


def test_full_queue_is_503(client, fake_redis, monkeypatch):
    monkeypatch.setattr(run, "MAX_QUEUE", 2)
    submit(client)
    submit(client)
    r = client.post("/run", json={"lang": "c", "code": "x"})
    assert r.status_code == 503
    assert r.json()["code"] == "SERVICE_UNAVAILABLE"


def test_expired_job_is_skipped(fake_redis):
    worker.process(fake_redis, "gone", lambda job: pytest.fail("실행하면 안 됨"))


def test_container_limits():
    cmd = " ".join(worker.docker_command("x"))
    for flag in ["--network none", "--memory 128m", "--memory-swap 128m", "--cpus 0.5",
                 "--pids-limit 64", "--read-only", "--user 1000:1000", "--cap-drop ALL", "--rm"]:
        assert flag in cmd


def age_job(fake_redis, job_id, **seconds_ago):
    job = run_queue.load(fake_redis, job_id)
    for key, ago in seconds_ago.items():
        job[key] = job.get(key, job["createdAt"]) - ago
    run_queue.save(fake_redis, job)


def test_stale_queued_job_is_reported_as_failed(client, fake_redis):
    job_id = submit(client)
    age_job(fake_redis, job_id, createdAt=run_queue.QUEUE_TIMEOUT_SECONDS + 1)  # 워커가 죽어서 오래 대기
    res = client.get(f"/run/{job_id}").json()
    assert res["status"] == "done"
    assert res["exitCode"] == 1


def test_worker_skips_job_that_waited_too_long(client, fake_redis):
    # 리뷰 M2: API가 실패로 알려 준 작업을 워커가 뒤늦게 실행하면 안 된다
    job_id = submit(client)
    age_job(fake_redis, job_id, createdAt=run_queue.QUEUE_TIMEOUT_SECONDS + 1)
    work(fake_redis, lambda job: pytest.fail("실행하면 안 됨"))
    res = client.get(f"/run/{job_id}").json()
    assert res["status"] == "done"
    assert res["stderr"] == run_queue.EXPIRED_MESSAGE
    assert run_queue.load(fake_redis, job_id)["code"] == ""


def test_running_job_judged_by_start_time(client, fake_redis):
    # 오래 기다렸다가 방금 실행을 시작한 작업은 아직 실패가 아니다
    job_id = submit(client)
    job = run_queue.load(fake_redis, job_id)
    job.update(status="running", createdAt=job["createdAt"] - 59, startedAt=job["createdAt"])
    run_queue.save(fake_redis, job)
    assert client.get(f"/run/{job_id}").json()["status"] == "running"
    # 실행 시작 후 RUN_TIMEOUT이 지나면 실패
    age_job(fake_redis, job_id, startedAt=run_queue.RUN_TIMEOUT_SECONDS + 1)
    assert client.get(f"/run/{job_id}").json()["status"] == "done"


def test_parse_result_ignores_injected_prefix():
    # 리뷰 C1: 결과 앞에 다른 글자가 섞여도 runner.py의 마지막 결과만 본다
    real = b'{"stdout": "15\\n", "stderr": "", "exitCode": 0, "timedOut": false, "durationMs": 3}'
    assert worker.parse_result(b"garbage" + real)["stdout"] == "15\n"
    assert worker.parse_result(b"no json here") is None
    assert worker.parse_result(b'{"stdout": broken') is None


def test_drain_stops_collecting_at_limit():
    import io

    called = []
    chunks: list[bytes] = []
    worker._drain(io.BytesIO(b"x" * 200_000), 100_000, chunks, lambda: called.append(1))
    assert sum(len(c) for c in chunks) == 100_000
    assert called  # 넘쳤으니 컨테이너를 지우도록 알림


def test_runs_per_user_are_limited(client, login, monkeypatch):
    monkeypatch.setattr(run, "RUNS_PER_USER", (2, 60))
    submit(client)
    submit(client)
    r = client.post("/run", json={"lang": "c", "code": "x"})
    assert r.status_code == 429
    assert r.json()["code"] == "TOO_MANY_REQUESTS"
    # 다른 사람은 영향 없음
    other = {"Authorization": f"Bearer {login('other')}"}
    assert client.post("/run", json={"lang": "c", "code": "x"}, headers=other).status_code == 202
