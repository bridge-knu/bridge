from fastapi import APIRouter, Depends

from app.api.errors import ApiError, responses

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
    user.diagnosis_done = False
    return step(user, None)


@router.post(
    "/answer",
    response_model=DiagnosisStep,
    responses=responses("DIAGNOSIS_FINISHED", "QUESTION_MISMATCH"),
    summary="답 제출 → 다음 문제 또는 종료",
    description="mock은 문제 3개를 고정 순서로 낸다.",
)
def answer(body: DiagnosisAnswerRequest, user: UserState = Depends(current_user)):
    if user.diagnosis_index >= len(DIAGNOSIS_ORDER):
        raise ApiError("DIAGNOSIS_FINISHED")
    expected_id = DIAGNOSIS_ORDER[user.diagnosis_index]
    if body.question_id != expected_id:
        raise ApiError("QUESTION_MISMATCH")
    correct = body.choice == QUESTION_BY_ID[expected_id]["answer"]
    user.diagnosis_index += 1
    user.diagnosis_done = user.diagnosis_index >= len(DIAGNOSIS_ORDER)
    return step(user, correct)


@router.get(
    "/result",
    response_model=DiagnosisResult,
    responses=responses("DIAGNOSIS_NOT_FINISHED"),
    summary="개념별 mastery (그래프용)",
    description="진단을 시작하지 않았거나 끝내지 않았으면 400 DIAGNOSIS_NOT_FINISHED.",
)
def result(user: UserState = Depends(current_user)):
    if not user.diagnosis_done:
        raise ApiError("DIAGNOSIS_NOT_FINISHED")
    return DiagnosisResult(
        concepts=[
            ConceptResult(**c, mastery=MASTERY[c["id"]][0], source=MASTERY[c["id"]][1])
            for c in CONCEPTS
        ]
    )
