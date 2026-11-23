"""진단 API. 엔진(app.engine.diagnosis)을 호출만 하고, 상태는 DB에 저장한다.

- diagnosis_sessions: 진행 중(또는 마지막으로 끝낸) 진단의 엔진 상태
- diagnosis_answers: 답을 낼 때마다 한 줄
- concept_states: 진단이 끝나면 개념별 이해도 (플랜이 읽는다)
"""

from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.deps import DEMO_LOGIN_ID, get_current_user
from app.api.errors import ApiError, responses
from app.api.profile import load_profile
from app.api.schemas import (
    ConceptResult,
    DiagnosisAnswerRequest,
    DiagnosisResult,
    DiagnosisStep,
    QuestionOut,
)
from app.clock import now
from app.content import get_graph
from app.db import get_db
from app.engine import diagnosis as engine
from app.engine.graph import Graph
from app.models import ConceptState, DiagnosisAnswer, DiagnosisSession, PlanInfo, User

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

# 프로필을 입력하기 전에 진단을 시작하면: 이수 과목 없음, 목표 자료구조
DEFAULT_PROFILE = {"completed_courses": [], "gap_months": 0, "target_course": "DS"}


def engine_profile(db: Session, user_id: int) -> dict:
    profile = load_profile(db, user_id)
    return profile.model_dump() if profile else dict(DEFAULT_PROFILE)


def question_out(graph: Graph, question_id: str) -> QuestionOut:
    q = graph.questions[question_id]
    return QuestionOut(
        id=q.id,
        concept_id=q.concept,
        concept_name=graph.concepts[q.concept].name,
        prompt=q.prompt,
        code=q.code,
        choices=list(q.choices),
    )


def load_state(db: Session, user_id: int) -> engine.DiagnosisState | None:
    row = db.get(DiagnosisSession, user_id)
    return engine.DiagnosisState.from_dict(row.state) if row else None


def save_state(db: Session, user_id: int, state: engine.DiagnosisState) -> None:
    values = {"state": state.to_dict(), "updated_at": now()}
    stmt = insert(DiagnosisSession).values(user_id=user_id, **values)
    db.execute(stmt.on_conflict_do_update(index_elements=[DiagnosisSession.user_id], set_=values))
    if state.done:
        save_concept_states(db, user_id, state)


def save_concept_states(db: Session, user_id: int, state: engine.DiagnosisState) -> None:
    """진단 결과를 개념별 이해도로 저장하고, 예전 결과로 만든 플랜은 다음 GET /plan에서 다시 만들게 한다."""
    db.execute(delete(ConceptState).where(ConceptState.user_id == user_id))
    db.add_all(
        ConceptState(user_id=user_id, concept_id=cid, mastery=m, source=state.source[cid])
        for cid, m in state.mastery.items()
    )
    db.execute(delete(PlanInfo).where(PlanInfo.user_id == user_id))


def advance(db: Session, user_id: int, state: engine.DiagnosisState, correct: bool | None) -> DiagnosisStep:
    """다음 문제를 정하고(엔진이 상태에 기록) 저장한 뒤 응답을 만든다."""
    graph = get_graph()
    question = engine.next_question(state, graph)
    save_state(db, user_id, state)
    db.commit()
    return DiagnosisStep(
        done=question is None,
        correct=correct,
        question=question_out(graph, question.id) if question else None,
        answered_count=state.answered_count,
        max_questions=state.max_questions,
    )


@router.post(
    "/start",
    response_model=DiagnosisStep,
    responses=responses("DIAGNOSIS_FINISHED"),
    summary="진단 시작, 첫 문제 반환",
    description=(
        "프로필(이수 과목·성적·공백)로 망각 추정을 해서 시작점을 정한다. 다시 시작하면 처음부터 새로 한다. "
        "물어볼 개념이 없으면 바로 done: true. "
        "공용 데모 계정(demo)은 여러 명이 같이 쓰므로 다시 시작할 수 없다 (400 DIAGNOSIS_FINISHED)."
    ),
)
def start(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 한 명이 demo로 진단을 시작하고 나가면 다른 사람이 결과를 못 보므로 막는다 (체험 계정은 가능)
    if user.login_id == DEMO_LOGIN_ID:
        raise ApiError("DIAGNOSIS_FINISHED")
    state = engine.start_diagnosis(engine_profile(db, user.id), get_graph())
    return advance(db, user.id, state, None)


@router.post(
    "/answer",
    response_model=DiagnosisStep,
    responses=responses("DIAGNOSIS_FINISHED", "QUESTION_MISMATCH"),
    summary="답 제출 → 다음 문제 또는 종료",
    description="틀리면 선수 개념으로 내려가고, 맞으면 그 아래는 안다고 보고 건너뛴다. 최대 10문제.",
)
def answer(body: DiagnosisAnswerRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    graph = get_graph()
    state = load_state(db, user.id)
    if state is None:
        raise ApiError("QUESTION_MISMATCH")
    if state.done:
        raise ApiError("DIAGNOSIS_FINISHED")
    if body.question_id != state.current_question_id or body.question_id not in graph.questions:
        raise ApiError("QUESTION_MISMATCH")

    question = graph.questions[body.question_id]
    correct = body.choice == question.answer
    engine.apply_answer(state, question.id, correct, graph)
    db.add(DiagnosisAnswer(user_id=user.id, question_id=question.id, concept_id=question.concept, correct=correct))
    return advance(db, user.id, state, correct)


@router.get(
    "/result",
    response_model=DiagnosisResult,
    responses=responses("DIAGNOSIS_NOT_FINISHED"),
    summary="개념별 mastery (그래프용)",
    description=(
        "목표 과목에 필요한 개념 전체를 선수 개념이 먼저 오는 순서로 준다. "
        "진단을 시작하지 않았거나 끝내지 않았으면 400 DIAGNOSIS_NOT_FINISHED."
    ),
)
def result(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    state = load_state(db, user.id)
    if state is None or not state.done:
        raise ApiError("DIAGNOSIS_NOT_FINISHED")
    return DiagnosisResult(concepts=[ConceptResult(**c) for c in engine.result_concepts(state, get_graph())])
