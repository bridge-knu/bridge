from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.clock import today
from app.content import get_graph
from app.models import CodeSnapshot, ConceptState, DiagnosisAnswer, Profile, User
from app.models import PlanBlock as PlanBlockRow

GRAPH = get_graph()


@pytest.fixture
def client(api_client, login):
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


# ---- 진단 (실제 엔진) ----


def answer(client, step, right: bool):
    q = step["question"]
    correct = GRAPH.questions[q["id"]].answer
    wrong = (correct + 1) % len(q["choices"])
    r = client.post("/diagnosis/answer", json={"questionId": q["id"], "choice": correct if right else wrong})
    assert r.status_code == 200, r.text
    return r.json()


def finish_diagnosis(client, right: bool = True, step=None):
    step = step or client.post("/diagnosis/start").json()
    while not step["done"]:
        step = answer(client, step, right)
    return step


def test_diagnosis_flow(client):
    step = client.post("/diagnosis/start").json()
    assert step["done"] is False
    assert step["correct"] is None
    assert step["answeredCount"] == 0
    assert step["maxQuestions"] == 10
    assert "answer" not in step["question"]
    assert step["question"]["conceptName"] == GRAPH.concepts[step["question"]["conceptId"]].name

    step = answer(client, step, right=True)
    assert step["correct"] is True
    assert step["answeredCount"] == 1

    step = answer(client, step, right=False)
    assert step["correct"] is False
    step = finish_diagnosis(client, right=False, step=step)
    assert step["question"] is None
    assert step["answeredCount"] <= 10


def test_all_wrong_goes_down_to_basics_within_10(client):
    asked = []
    step = client.post("/diagnosis/start").json()
    while not step["done"]:
        asked.append(step["question"]["conceptId"])
        step = answer(client, step, right=False)
    assert len(asked) <= 10
    assert GRAPH.depth(asked[-1]) < GRAPH.depth(asked[0])  # 틀리면 더 기초로 내려간다


def test_fresh_a_grade_has_no_questions(client):
    # 공백 0개월 + A학점 → 문제가 거의 안 나옴 (C 개념은 모두 안다고 봄)
    client.put("/profile", json={**PROFILE, "gapMonths": 0})
    step = client.post("/diagnosis/start").json()
    assert step["done"] is True
    assert step["question"] is None
    assert client.get("/diagnosis/result").status_code == 200


def test_diagnosis_wrong_question_id(client):
    client.post("/diagnosis/start")
    r = client.post("/diagnosis/answer", json={"questionId": "q-xxx", "choice": 0})
    assert r.status_code == 400
    assert r.json() == {"detail": "지금 풀고 있는 문제가 아니에요", "code": "QUESTION_MISMATCH"}


def test_answer_without_start(client):
    r = client.post("/diagnosis/answer", json={"questionId": "q-array-1", "choice": 0})
    assert r.json()["code"] == "QUESTION_MISMATCH"


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
    step = client.post("/diagnosis/start").json()
    first = step["question"]["conceptId"]
    finish_diagnosis(client, right=False, step=step)
    concepts = client.get("/diagnosis/result").json()["concepts"]

    ids = [c["id"] for c in concepts]
    assert set(ids) == GRAPH.required_for_course("DS")
    for c in concepts:
        assert 0 <= c["mastery"] <= 1
        assert c["source"] in ("prior", "diagnosed")
        assert c["prereqs"] == GRAPH.prereqs(c["id"])
        for p in c["prereqs"]:
            assert ids.index(p) < ids.index(c["id"])  # 선수 개념이 먼저
    by_id = {c["id"]: c for c in concepts}
    assert by_id[first]["mastery"] == 0.2
    assert by_id[first]["source"] == "diagnosed"


def test_diagnosis_is_saved_in_db(client, db):
    step = finish_diagnosis(client, right=False)
    uid = user_id(db)
    answers = db.scalars(select(DiagnosisAnswer).where(DiagnosisAnswer.user_id == uid)).all()
    assert len(answers) == step["answeredCount"]
    assert all(a.correct is False for a in answers)
    states = db.scalars(select(ConceptState).where(ConceptState.user_id == uid)).all()
    assert {s.concept_id for s in states} == GRAPH.required_for_course("DS")


def test_demo_has_finished_diagnosis(api_client, login):
    headers = {"Authorization": f"Bearer {login('demo', '0000')}"}
    concepts = api_client.get("/diagnosis/result", headers=headers).json()["concepts"]
    assert {c["source"] for c in concepts} == {"prior", "diagnosed"}
    assert api_client.get("/plan", headers=headers).json()["days"]


# ---- 플랜 (실제 엔진) ----


def planned(plan):
    return [b for d in plan["days"] for b in d["blocks"]]


def test_plan_uses_daily_minutes(client):
    client.put("/profile", json=PROFILE)  # 하루 60분 → 블록 2개
    plan = client.post("/plan/generate").json()
    assert plan["dailyMinutes"] == 60
    assert plan["returnDate"] == "2027-03-02"
    assert all(len(d["blocks"]) <= 2 for d in plan["days"])
    assert [d["date"] for d in plan["days"]] == [
        (today() + timedelta(days=i)).isoformat() for i in range(len(plan["days"]))
    ]
    assert plan["todayRemainingMinutes"] == 60
    assert client.get("/plan").json() == plan


def test_plan_puts_prereqs_first(client):
    client.put("/profile", json=PROFILE)
    order = [b["conceptId"] for b in planned(client.get("/plan").json())]
    for i, cid in enumerate(order):
        for p in GRAPH.ancestors(cid):
            if p in order:
                assert order.index(p) < i


def test_plan_only_has_concepts_not_known(client):
    finish_diagnosis(client, right=False)
    mastery = {c["id"]: c["mastery"] for c in client.get("/diagnosis/result").json()["concepts"]}
    blocks = planned(client.get("/plan").json())
    assert blocks
    assert {b["conceptId"] for b in blocks} == {c for c, m in mastery.items() if m < 0.6}


def test_plan_has_no_deferred_when_time_is_enough(client):
    client.put("/profile", json=PROFILE)
    plan = client.post("/plan/generate").json()
    assert plan["deferredConcepts"] == []
    assert plan["message"] is None


def test_plan_defers_concepts_when_time_is_short(client):
    tomorrow = (today() + timedelta(days=1)).isoformat()
    client.put("/profile", json={**PROFILE, "returnDate": tomorrow, "dailyMinutes": 30})  # 블록 1개만 가능
    plan = client.post("/plan/generate").json()
    assert len(planned(plan)) <= 1
    assert plan["deferredConcepts"]
    names = ", ".join(d["conceptName"] for d in plan["deferredConcepts"])
    assert plan["message"] == f"시간이 부족해 {names}은(는) 복학 후로 미뤘어요"
    assert client.get("/plan").json()["deferredConcepts"] == plan["deferredConcepts"]


def test_plan_is_saved_in_db(client, db):
    plan = client.get("/plan").json()
    rows = db.scalars(select(PlanBlockRow).where(PlanBlockRow.user_id == user_id(db))).all()
    assert sorted(r.block_id for r in rows) == sorted(b["blockId"] for b in planned(plan))


def test_profile_change_rebuilds_plan(client):
    client.put("/profile", json=PROFILE)
    assert client.get("/plan").json()["dailyMinutes"] == 60
    client.put("/profile", json={**PROFILE, "dailyMinutes": 90})
    plan = client.get("/plan").json()
    assert plan["dailyMinutes"] == 90
    assert len(plan["days"][0]["blocks"]) == 3


def test_finishing_diagnosis_rebuilds_plan(client):
    before = planned(client.get("/plan").json())
    finish_diagnosis(client, right=True)  # 다 맞히면 배울 개념이 줄어든다
    after = planned(client.get("/plan").json())
    assert len(after) < len(before)


def test_regenerate_keeps_done_blocks(client):
    client.put("/profile", json=PROFILE)
    client.get("/plan")
    client.post("/blocks/b-array-1/complete")
    plan = client.post("/plan/generate").json()
    assert {b["blockId"]: b["done"] for b in planned(plan)}["b-array-1"] is True


def pass_days(db, n=1):
    """저장된 플랜을 n일 전에 만든 것처럼 날짜를 당긴다 (하루가 지난 상황)."""
    db.expire_all()
    rows = db.scalars(select(PlanBlockRow).where(PlanBlockRow.user_id == user_id(db))).all()
    for r in rows:  # (user, date, order) 유일 제약에 걸리지 않게 멀리 옮겼다가 다시 옮긴다
        r.date -= timedelta(days=1000)
    db.flush()
    for r in rows:
        r.date += timedelta(days=1000 - n)
        if r.done_at:
            r.done_at -= timedelta(days=n)
    db.flush()


def test_plan_moves_to_today_when_day_passes(client, db):
    client.put("/profile", json=PROFILE)
    before = planned(client.get("/plan").json())
    first = next(b["blockId"] for b in before if b["blockId"] in GRAPH.blocks)
    client.post(f"/blocks/{first}/complete")
    pass_days(db, 30)  # 플랜 전체가 지난 날짜가 되게

    plan = client.get("/plan").json()
    now = today().isoformat()
    past = [b for d in plan["days"] if d["date"] < now for b in d["blocks"]]
    assert [(b["blockId"], b["done"]) for b in past] == [(first, True)]  # 끝낸 블록은 그 날짜에 기록으로
    upcoming = [d for d in plan["days"] if d["date"] >= now]
    assert upcoming[0]["date"] == now  # 안 끝낸 블록은 오늘부터 다시
    assert len(upcoming[0]["blocks"]) == 2
    assert not any(b["done"] for d in upcoming for b in d["blocks"])
    assert sorted(b["blockId"] for b in planned(plan)) == sorted(b["blockId"] for b in before)
    assert plan["todayRemainingMinutes"] == 60
    assert client.get("/plan").json() == plan  # 한 번 옮기면 그대로


def test_plan_moves_even_if_nothing_done(client, db):
    client.put("/profile", json=PROFILE)
    before = planned(client.get("/plan").json())
    pass_days(db, 3)
    plan = client.get("/plan").json()
    assert plan["days"][0]["date"] == today().isoformat()
    assert [b["blockId"] for b in planned(plan)] == [b["blockId"] for b in before]


def test_finished_concept_is_not_planned_again(client, db):
    client.put("/profile", json=PROFILE)
    blocks = planned(client.get("/plan").json())
    by_concept: dict[str, list[str]] = {}
    for b in blocks:
        by_concept.setdefault(b["conceptId"], []).append(b["blockId"])
    concept, ids = next(
        ((c, ids) for c, ids in by_concept.items() if all(i in GRAPH.blocks for i in ids)), (None, [])
    )
    if concept is None:
        pytest.skip("블록 내용이 다 있는 개념이 없음 (content/blocks.json)")
    for bid in ids:
        client.post(f"/blocks/{bid}/complete")
    pass_days(db, 30)
    plan = client.post("/plan/generate").json()
    now = today().isoformat()
    past = [b for d in plan["days"] if d["date"] < now for b in d["blocks"]]
    assert sorted(b["blockId"] for b in past) == sorted(ids)
    upcoming = [b for d in plan["days"] if d["date"] >= now for b in d["blocks"]]
    assert concept not in {b["conceptId"] for b in upcoming}
    assert len(upcoming) == len(blocks) - len(ids)


def test_plan_today_is_korean_date(client):
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
    client.get("/plan")
    client.post("/blocks/b-array-1/complete")
    client.post("/blocks/b-pointer-1/complete")
    assert client.get("/plan").json()["todayRemainingMinutes"] == 0


def test_plan_without_profile(client):
    plan = client.get("/plan").json()
    assert plan["dailyMinutes"] == 60
    assert len(plan["days"]) >= 1
    assert plan["days"][0]["date"] == today().isoformat()


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
    ids = [b["blockId"] for b in planned(client.get("/plan").json())]
    check = GRAPH.blocks["b-array-1"].check
    answers = [{"questionId": q, "choice": GRAPH.questions[q].answer} for q in check]
    body = client.post("/blocks/b-array-1/complete", json={"checkAnswers": answers}).json()
    assert body == {
        "blockId": "b-array-1",
        "done": True,
        "correctCount": len(check),
        "totalCount": len(check),
        "results": [
            {"questionId": q, "choice": GRAPH.questions[q].answer, "answer": GRAPH.questions[q].answer, "correct": True}
            for q in check
        ],
        "nextBlockId": ids[ids.index("b-array-1") + 1],
    }
    assert client.get("/blocks/b-array-1").json()["done"] is True
    assert {b["blockId"]: b["done"] for b in planned(client.get("/plan").json())}["b-array-1"] is True


def test_complete_is_per_user(client, login):
    client.get("/plan")
    client.post("/blocks/b-array-1/complete")
    other = {"Authorization": f"Bearer {login('other')}"}
    assert client.get("/blocks/b-array-1", headers=other).json()["done"] is False


def test_complete_without_body(client):
    r = client.post("/blocks/b-array-1/complete")
    assert r.status_code == 200
    assert r.json()["correctCount"] == 0
    assert all(r["choice"] is None and r["correct"] is False for r in r.json()["results"])


def test_complete_tells_which_answers_were_wrong(client):
    check = GRAPH.blocks["b-array-1"].check
    first = GRAPH.questions[check[0]]
    wrong = (first.answer + 1) % len(first.choices)
    body = client.post(
        "/blocks/b-array-1/complete", json={"checkAnswers": [{"questionId": first.id, "choice": wrong}]}
    ).json()
    assert body["correctCount"] == 0
    assert body["results"][0] == {"questionId": first.id, "choice": wrong, "answer": first.answer, "correct": False}
    assert [r["questionId"] for r in body["results"]] == list(check)


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
