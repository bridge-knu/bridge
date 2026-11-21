from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.diagnosis import question_out
from app.api.errors import ApiError, responses
from app.api.mock_data import BLOCK_BY_ID, BLOCKS, CONCEPT_NAME, QUESTION_BY_ID, UserState, current_user
from app.api.schemas import (
    BlockDetail,
    CompleteRequest,
    CompleteResponse,
    Practice,
    Video,
)
from app.db import get_db
from app.models import CodeSnapshot, User

router = APIRouter(prefix="/blocks", tags=["blocks"])

NOT_FOUND = responses("BLOCK_NOT_FOUND")


def get_block_or_404(block_id: str) -> dict:
    block = BLOCK_BY_ID.get(block_id)
    if block is None:
        raise ApiError("BLOCK_NOT_FOUND")
    return block


@router.get("/{block_id}", response_model=BlockDetail, responses=NOT_FOUND, summary="강의 링크·실습·확인 문제")
def get_block(
    block_id: str,
    user: UserState = Depends(current_user),
    account: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    b = get_block_or_404(block_id)
    saved = db.get(CodeSnapshot, (account.id, block_id))
    return BlockDetail(
        id=b["id"],
        concept_id=b["concept"],
        concept_name=CONCEPT_NAME[b["concept"]],
        minutes=b["minutes"],
        video=Video(**b["video"]),
        practice=Practice(**b["practice"]),
        check_questions=[question_out(q) for q in b["check"]],
        saved_code=saved.code if saved else None,
        saved_at=saved.updated_at if saved else None,
        done=block_id in user.done_blocks,
    )


@router.post(
    "/{block_id}/complete",
    response_model=CompleteResponse,
    responses=NOT_FOUND,
    summary="블록 완료 처리",
    description="확인 문제 답을 함께 보내면 채점한다. 틀려도 완료로 처리한다.",
)
def complete(
    block_id: str,
    body: CompleteRequest | None = None,
    user: UserState = Depends(current_user),
):
    b = get_block_or_404(block_id)
    answers = {a.question_id: a.choice for a in (body.check_answers if body else [])}
    correct = sum(1 for q in b["check"] if answers.get(q) == QUESTION_BY_ID[q]["answer"])
    user.done_blocks.add(block_id)

    ids = [x["id"] for x in BLOCKS]
    rest = [i for i in ids[ids.index(block_id) + 1 :] if i not in user.done_blocks]
    return CompleteResponse(
        block_id=block_id,
        done=True,
        correct_count=correct,
        total_count=len(b["check"]),
        next_block_id=rest[0] if rest else None,
    )
