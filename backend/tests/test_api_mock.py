import time

import pytest
from fastapi.testclient import TestClient

from app.api import mock_data, run
from app.main import app


@pytest.fixture
def client():
    mock_data.USERS.clear()
    mock_data.JOBS.clear()
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer mock-token-test"
    return c


@pytest.fixture
def instant_run(monkeypatch):
    monkeypatch.setattr(run, "MOCK_RUN_SECONDS", 0)


# ---- 인증 ----


def test_login_new_user(client):
    r = client.post("/auth/login", json={"loginId": "kim", "pin": "1234"})
    assert r.status_code == 200
    assert r.json() == {"token": "mock-token-kim", "isNewUser": True}


def test_login_demo_is_existing_user(client):
    r = client.post("/auth/login", json={"loginId": "demo", "pin": "0000"})
    assert r.json()["isNewUser"] is False


def test_login_wrong_pin(client):
    r = client.post("/auth/login", json={"loginId": "kim", "pin": "9999"})
    assert r.status_code == 401
    assert r.json() == {"detail": "아이디 또는 PIN이 틀렸어요"}


def test_login_locked(client):
    r = client.post("/auth/login", json={"loginId": "locked", "pin": "1234"})
    assert r.status_code == 429
    assert r.json() == {"detail": "1분 후 다시 시도해 주세요"}


@pytest.mark.parametrize("pin", ["123", "12345", "abcd"])
def test_login_pin_must_be_4_digits(client, pin):
    r = client.post("/auth/login", json={"loginId": "kim", "pin": pin})
    assert r.status_code == 422


# ---- 프로필 ----

PROFILE = {
    "completedCourses": [{"course": "C", "grade": "A+"}],
    "gapMonths": 24,
    "targetCourse": "DS",
    "returnDate": "2027-03-02",
    "dailyMinutes": 60,
}


def test_save_profile(client):
    r = client.put("/profile", json=PROFILE)
    assert r.status_code == 200
    body = r.json()
    assert body["gapMonths"] == 24
    assert body["completedCourses"] == [{"course": "C", "grade": "A+"}]
    assert "updatedAt" in body


@pytest.mark.parametrize(
    "change",
    [
        {"dailyMinutes": 10},
        {"dailyMinutes": 601},
        {"gapMonths": -1},
        {"gapMonths": 121},
        {"targetCourse": "자료구조"},
        {"completedCourses": [{"course": "C프로그래밍", "grade": "B+"}]},
        {"completedCourses": [{"course": "C"}]},
        {"completedCourses": [{"course": "C", "grade": None}]},
        {"completedCourses": [{"course": "C", "grade": "A"}]},
        {"completedCourses": [{"course": "C", "grade": "a+"}]},
        {"completedCourses": [{"course": "C", "grade": "E"}]},
    ],
)
def test_profile_rejects_invalid_values(client, change):
    r = client.put("/profile", json={**PROFILE, **change})
    assert r.status_code == 422


ALL_GRADES = ["A+", "A0", "A-", "B+", "B0", "B-", "C+", "C0", "C-", "D+", "D0", "D-", "F", "P"]


@pytest.mark.parametrize("grade", ALL_GRADES)
def test_profile_accepts_all_14_grades(client, grade):
    r = client.put("/profile", json={**PROFILE, "completedCourses": [{"course": "C", "grade": grade}]})
    assert r.status_code == 200
    assert r.json()["completedCourses"][0]["grade"] == grade


def test_profile_keeps_raw_grade(client):
    courses = [{"course": "C", "grade": "A+"}, {"course": "DS", "grade": "P"}]
    r = client.put("/profile", json={**PROFILE, "completedCourses": courses})
    assert r.json()["completedCourses"] == courses


# ---- 진단 ----


def test_diagnosis_flow(client):
    r = client.post("/diagnosis/start")
    step = r.json()
    assert step["done"] is False
    assert step["correct"] is None
    assert step["answeredCount"] == 0
    assert step["maxQuestions"] == 3
    assert "answer" not in step["question"]

    q = step["question"]
    step = client.post("/diagnosis/answer", json={"questionId": q["id"], "choice": 0}).json()
    assert step["correct"] is True
    assert step["answeredCount"] == 1

    while not step["done"]:
        q = step["question"]
        step = client.post("/diagnosis/answer", json={"questionId": q["id"], "choice": 3}).json()
    assert step["question"] is None
    assert step["correct"] is False
    assert step["answeredCount"] == 3


def test_diagnosis_wrong_question_id(client):
    client.post("/diagnosis/start")
    r = client.post("/diagnosis/answer", json={"questionId": "q-xxx", "choice": 0})
    assert r.status_code == 400


def test_diagnosis_result(client):
    concepts = client.get("/diagnosis/result").json()["concepts"]
    assert [c["id"] for c in concepts] == ["array", "pointer", "linked_list"]
    for c in concepts:
        assert 0 <= c["mastery"] <= 1
        assert c["source"] in ("prior", "diagnosed")
    assert concepts[1]["prereqs"] == ["array"]


# ---- 플랜 ----


def test_plan_uses_daily_minutes(client):
    client.put("/profile", json=PROFILE)  # 하루 60분 → 블록 2개
    plan = client.post("/plan/generate").json()
    assert plan["dailyMinutes"] == 60
    assert plan["returnDate"] == "2027-03-02"
    assert [len(d["blocks"]) for d in plan["days"]] == [2, 1]
    assert plan["todayRemainingMinutes"] == 60
    assert client.get("/plan").json() == plan


def test_plan_without_profile(client):
    plan = client.get("/plan").json()
    assert len(plan["days"]) >= 1
    assert plan["days"][0]["blocks"][0]["blockId"] == "b-array-1"


# ---- 블록·자동 저장 ----


def test_get_block(client):
    b = client.get("/blocks/b-array-1").json()
    assert b["conceptName"] == "배열"
    assert b["video"]["end"] > b["video"]["start"]
    assert b["practice"]["lang"] == "c"
    assert b["checkQuestions"][0]["id"] == "q-array-2"
    assert "answer" not in b["checkQuestions"][0]
    assert b["savedCode"] is None
    assert b["done"] is False


def test_unknown_block_404(client):
    r = client.get("/blocks/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "블록을 찾을 수 없어요"}


def test_save_code_then_load(client):
    r = client.put("/code/b-array-1", json={"code": "int main(){}"})
    assert r.status_code == 200
    assert r.json()["blockId"] == "b-array-1"

    client.put("/code/b-array-1", json={"code": "int main(){return 0;}"})
    b = client.get("/blocks/b-array-1").json()
    assert b["savedCode"] == "int main(){return 0;}"
    assert b["savedAt"] is not None


def test_saved_code_is_per_user(client):
    client.put("/code/b-array-1", json={"code": "mine"})
    other = client.get("/blocks/b-array-1", headers={"Authorization": "Bearer other"}).json()
    assert other["savedCode"] is None


def test_complete_block(client):
    r = client.post("/blocks/b-array-1/complete", json={"checkAnswers": [{"questionId": "q-array-2", "choice": 1}]})
    body = r.json()
    assert body == {
        "blockId": "b-array-1",
        "done": True,
        "correctCount": 1,
        "totalCount": 1,
        "nextBlockId": "b-pointer-1",
    }
    assert client.get("/blocks/b-array-1").json()["done"] is True
    assert client.get("/plan").json()["days"][0]["blocks"][0]["done"] is True


def test_complete_without_body(client):
    r = client.post("/blocks/b-linked_list-1/complete")
    assert r.status_code == 200
    assert r.json()["correctCount"] == 0
    assert r.json()["nextBlockId"] is None


# ---- 코드 실행 ----


def run_and_wait(client, payload):
    r = client.post("/run", json=payload)
    assert r.status_code == 202
    return client.get(f"/run/{r.json()['jobId']}").json()


def test_run_is_running_first(client):
    job_id = client.post("/run", json={"lang": "c", "code": "x"}).json()["jobId"]
    assert client.get(f"/run/{job_id}").json()["status"] == "running"


def test_run_becomes_done(client):
    job_id = client.post("/run", json={"lang": "c", "code": "x"}).json()["jobId"]
    time.sleep(run.MOCK_RUN_SECONDS + 0.1)
    assert client.get(f"/run/{job_id}").json()["status"] == "done"


def test_run_block_matches_expected(client, instant_run):
    res = run_and_wait(client, {"lang": "c", "code": "...", "blockId": "b-array-1"})
    assert res["status"] == "done"
    assert res["stdout"] == "15\n"
    assert res["matchesExpected"] is True


def test_run_without_block(client, instant_run):
    res = run_and_wait(client, {"lang": "python", "code": "print('hello')"})
    assert res["stdout"] == "hello\n"
    assert res["matchesExpected"] is None


def test_run_infinite_loop_times_out(client, instant_run):
    res = run_and_wait(client, {"lang": "c", "code": "while (1) {}", "blockId": "b-array-1"})
    assert res["timedOut"] is True
    assert res["matchesExpected"] is False


def test_run_compile_error(client, instant_run):
    res = run_and_wait(client, {"lang": "c", "code": "COMPILE_ERROR"})
    assert res["exitCode"] == 1
    assert "error" in res["stderr"]


def test_run_unknown_job(client):
    assert client.get("/run/nope").status_code == 404


def test_all_12_endpoints_in_docs(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        ("post", "/auth/login"),
        ("put", "/profile"),
        ("post", "/diagnosis/start"),
        ("post", "/diagnosis/answer"),
        ("get", "/diagnosis/result"),
        ("post", "/plan/generate"),
        ("get", "/plan"),
        ("get", "/blocks/{block_id}"),
        ("put", "/code/{block_id}"),
        ("post", "/run"),
        ("get", "/run/{job_id}"),
        ("post", "/blocks/{block_id}/complete"),
    }
    actual = {(m, p) for p, ops in paths.items() for m in ops}
    assert expected <= actual
