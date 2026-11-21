import pytest
from sqlalchemy import select

from app.api import mock_data
from app.clock import today
from app.models import CodeSnapshot, Profile, User


@pytest.fixture
def client(api_client, login):
    mock_data.USERS.clear()
    api_client.headers["Authorization"] = f"Bearer {login('tester')}"
    return api_client


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


def user_id(db, login_id="tester"):
    return db.scalar(select(User.id).where(User.login_id == login_id))


def test_profile_is_saved_in_db(client, db):
    client.put("/profile", json=PROFILE)
    row = db.get(Profile, user_id(db))
    assert row.gap_months == 24
    assert row.completed_courses == [{"course": "C", "grade": "A+"}]
    assert str(row.return_date) == "2027-03-02"


def test_profile_save_overwrites(client, db):
    first = client.put("/profile", json=PROFILE).json()
    second = client.put("/profile", json={**PROFILE, "dailyMinutes": 120}).json()
    assert second["dailyMinutes"] == 120
    assert second["updatedAt"] > first["updatedAt"]
    assert db.get(Profile, user_id(db)).daily_minutes == 120


def test_demo_has_profile(api_client, db):
    row = db.get(Profile, user_id(db, "demo"))
    assert row is not None and row.target_course == "DS"


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
    assert r.json() == {"detail": "지금 풀고 있는 문제가 아니에요", "code": "QUESTION_MISMATCH"}


def finish_diagnosis(client):
    step = client.post("/diagnosis/start").json()
    while not step["done"]:
        step = client.post("/diagnosis/answer", json={"questionId": step["question"]["id"], "choice": 0}).json()
    return step


def test_answer_after_finished(client):
    finish_diagnosis(client)
    r = client.post("/diagnosis/answer", json={"questionId": "q-array-1", "choice": 0})
    assert r.status_code == 400
    assert r.json()["code"] == "DIAGNOSIS_FINISHED"


def test_result_before_diagnosis(client):
    r = client.get("/diagnosis/result")
    assert r.status_code == 400
    assert r.json() == {"detail": "진단을 먼저 끝내 주세요", "code": "DIAGNOSIS_NOT_FINISHED"}


def test_result_during_diagnosis(client):
    finish_diagnosis(client)
    client.post("/diagnosis/start")  # 다시 시작하면 끝날 때까지 결과를 주지 않는다
    assert client.get("/diagnosis/result").json()["code"] == "DIAGNOSIS_NOT_FINISHED"


def test_diagnosis_result(client):
    finish_diagnosis(client)
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


def test_plan_has_no_deferred_when_time_is_enough(client):
    client.put("/profile", json=PROFILE)
    plan = client.post("/plan/generate").json()
    assert plan["deferredConcepts"] == []
    assert plan["message"] is None


def test_plan_defers_concepts_when_time_is_short(client):
    from datetime import timedelta

    tomorrow = (today() + timedelta(days=1)).isoformat()
    client.put("/profile", json={**PROFILE, "returnDate": tomorrow, "dailyMinutes": 30})  # 블록 1개만 가능
    plan = client.post("/plan/generate").json()
    assert [b["blockId"] for d in plan["days"] for b in d["blocks"]] == ["b-array-1"]
    assert plan["deferredConcepts"] == [
        {"conceptId": "pointer", "conceptName": "포인터", "blocks": 1},
        {"conceptId": "linked_list", "conceptName": "연결 리스트", "blocks": 1},
    ]
    assert plan["message"] == "시간이 부족해 포인터, 연결 리스트은(는) 복학 후로 미뤘어요"


def test_plan_today_is_korean_date(client):
    from datetime import datetime, timedelta, timezone

    plan = client.get("/plan").json()
    assert plan["today"] == today().isoformat()
    assert today() == (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    assert plan["days"][0]["date"] == plan["today"]


def test_today_remaining_is_daily_minus_done_today(client):
    client.put("/profile", json={**PROFILE, "dailyMinutes": 90})
    assert client.post("/plan/generate").json()["todayRemainingMinutes"] == 90
    client.post("/blocks/b-array-1/complete")
    assert client.get("/plan").json()["todayRemainingMinutes"] == 60
    client.post("/blocks/b-array-1/complete")  # 같은 블록을 다시 완료해도 두 번 빼지 않는다
    assert client.get("/plan").json()["todayRemainingMinutes"] == 60


def test_today_remaining_never_negative(client):
    client.put("/profile", json={**PROFILE, "dailyMinutes": 30})
    client.post("/blocks/b-array-1/complete")
    client.post("/blocks/b-pointer-1/complete")
    assert client.get("/plan").json()["todayRemainingMinutes"] == 0


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
    assert r.json() == {"detail": "블록을 찾을 수 없어요", "code": "BLOCK_NOT_FOUND"}


def test_save_code_then_load(client):
    r = client.put("/code/b-array-1", json={"code": "int main(){}"})
    assert r.status_code == 200
    assert r.json()["blockId"] == "b-array-1"

    client.put("/code/b-array-1", json={"code": "int main(){return 0;}"})
    b = client.get("/blocks/b-array-1").json()
    assert b["savedCode"] == "int main(){return 0;}"
    assert b["savedAt"] is not None


def test_saved_code_is_per_user(client, login):
    client.put("/code/b-array-1", json={"code": "mine"})
    other_token = login("other")
    other = client.get("/blocks/b-array-1", headers={"Authorization": f"Bearer {other_token}"}).json()
    assert other["savedCode"] is None


def test_save_code_rejects_nul_character(client, db):
    # PostgreSQL은 NUL 문자를 저장할 수 없다. 500 대신 422 JSON으로 거부해야 화면이 재시도하지 않는다
    r = client.put("/code/b-array-1", json={"code": "int main(){}\u0000"})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/json")
    assert db.get(CodeSnapshot, (user_id(db), "b-array-1")) is None


def test_save_code_keeps_other_special_characters(client):
    code = 'printf("탭\t줄바꿈\n이모지 😀 백슬래시 \\\\");'
    client.put("/code/b-array-1", json={"code": code})
    assert client.get("/blocks/b-array-1").json()["savedCode"] == code


def test_save_code_needs_login(api_client):
    r = api_client.put("/code/b-array-1", json={"code": "x"})
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_save_code_too_long_is_422(client):
    assert client.put("/code/b-array-1", json={"code": "a" * 65537}).status_code == 422
    assert client.put("/code/b-array-1", json={"code": "a" * 65536}).status_code == 200


def test_save_code_unknown_block_has_code(client):
    r = client.put("/code/nope", json={"code": "x"})
    assert r.json() == {"detail": "블록을 찾을 수 없어요", "code": "BLOCK_NOT_FOUND"}


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
