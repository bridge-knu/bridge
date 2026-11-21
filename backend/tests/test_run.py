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


def test_stale_job_is_reported_as_failed(client, fake_redis):
    job_id = submit(client)
    job = run_queue.load(fake_redis, job_id)
    job["createdAt"] -= run.STALE_SECONDS + 1  # 워커가 죽어서 오래 대기 중인 상황
    run_queue.save(fake_redis, job)
    res = client.get(f"/run/{job_id}").json()
    assert res["status"] == "done"
    assert res["exitCode"] == 1
