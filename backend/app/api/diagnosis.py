from fastapi import APIRouter, Depends, HTTPException

from app.api.mock_data import (
    CONCEPT_NAME,
    CONCEPTS,
    DIAGNOSIS_ORDER,
    MASTERY,
    QUESTION_BY_ID,
    UserState,
    current_user,
)
from app.api.schemas import (
    ConceptResult,
    DiagnosisAnswerRequest,
    DiagnosisResult,
    DiagnosisStep,
    ErrorResponse,
    QuestionOut,
)

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


def question_out(qid: str) -> QuestionOut:
    q = QUESTION_BY_ID[qid]
    return QuestionOut(
        id=q["id"],
        concept_id=q["concept"],
        concept_name=CONCEPT_NAME[q["concept"]],
        prompt=q["prompt"],
        code=q["code"],
        choices=q["choices"],
    )


def step(user: UserState, correct: bool | None) -> DiagnosisStep:
    total = len(DIAGNOSIS_ORDER)
    done = user.diagnosis_index >= total
    return DiagnosisStep(
        done=done,
        correct=correct,
        question=None if done else question_out(DIAGNOSIS_ORDER[user.diagnosis_index]),
        answered_count=user.diagnosis_index,
        max_questions=total,
    )


@router.post("/start", response_model=DiagnosisStep, summary="진단 시작, 첫 문제 반환")
def start(user: UserState = Depends(current_user)):
    user.diagnosis_index = 0
    return step(user, None)


@router.post(
    "/answer",
    response_model=DiagnosisStep,
    responses={400: {"model": ErrorResponse}},
    summary="답 제출 → 다음 문제 또는 종료",
    description="mock은 문제 3개를 고정 순서로 낸다.",
)
def answer(body: DiagnosisAnswerRequest, user: UserState = Depends(current_user)):
    if user.diagnosis_index >= len(DIAGNOSIS_ORDER):
        raise HTTPException(400, "진단이 이미 끝났어요")
    expected_id = DIAGNOSIS_ORDER[user.diagnosis_index]
    if body.question_id != expected_id:
        raise HTTPException(400, "지금 풀고 있는 문제가 아니에요")
    correct = body.choice == QUESTION_BY_ID[expected_id]["answer"]
    user.diagnosis_index += 1
    return step(user, correct)


@router.get("/result", response_model=DiagnosisResult, summary="개념별 mastery (그래프용)")
def result(_: UserState = Depends(current_user)):
    return DiagnosisResult(
        concepts=[
            ConceptResult(**c, mastery=MASTERY[c["id"]][0], source=MASTERY[c["id"]][1])
            for c in CONCEPTS
        ]
    )
