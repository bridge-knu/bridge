"""블록 학습 API. 블록 내용은 content/blocks.json, 완료 여부는 plan_blocks에 저장한다."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.diagnosis import question_out
from app.api.errors import ApiError, responses
from app.api.schemas import (
    BlockDetail,
    CheckResult,
    CompleteRequest,
    CompleteResponse,
    Practice,
    Video,
)
from app.clock import now
from app.content import get_graph
from app.db import get_db
from app.engine.models import Block
from app.models import CodeSnapshot, PlanBlock, User

router = APIRouter(prefix="/blocks", tags=["blocks"])

NOT_FOUND = responses("BLOCK_NOT_FOUND")


def get_block_or_404(block_id: str) -> Block:
    block = get_graph().blocks.get(block_id)
    if block is None:
        raise ApiError("BLOCK_NOT_FOUND")
    return block


def plan_rows(db: Session, user_id: int) -> list[PlanBlock]:
    stmt = select(PlanBlock).where(PlanBlock.user_id == user_id).order_by(PlanBlock.date, PlanBlock.order)
    return list(db.scalars(stmt).all())


@router.get("/{block_id}", response_model=BlockDetail, responses=NOT_FOUND, summary="강의 링크·실습·확인 문제")
def get_block(block_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    graph = get_graph()
    b = get_block_or_404(block_id)
    saved = db.get(CodeSnapshot, (user.id, block_id))
    done = db.scalar(
        select(PlanBlock.id).where(PlanBlock.user_id == user.id, PlanBlock.block_id == block_id, PlanBlock.done)
    )
    return BlockDetail(
        id=b.id,
        concept_id=b.concept,
        concept_name=graph.concepts[b.concept].name,
        minutes=b.minutes,
        video=Video(url=b.video, start=b.video_start, end=b.video_end),
        practice=Practice(lang=b.practice.lang, starter=b.practice.starter, expected=b.practice.expected),
        check_questions=[question_out(graph, q) for q in b.check],
        saved_code=saved.code if saved else None,
        saved_at=saved.updated_at if saved else None,
        done=done is not None,
    )


@router.post(
    "/{block_id}/complete",
    response_model=CompleteResponse,
    responses=NOT_FOUND,
    summary="블록 완료 처리",
    description=(
        "확인 문제 답을 함께 보내면 채점하고, results에 문제별로 보낸 답·정답·맞았는지를 준다. 틀려도 완료로 처리한다. "
        "nextBlockId는 플랜에서 이 블록 다음의 아직 안 끝낸 블록 (없으면 null)."
    ),
)
def complete(
    block_id: str,
    body: CompleteRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    graph = get_graph()
    b = get_block_or_404(block_id)
    answers = {a.question_id: a.choice for a in (body.check_answers if body else [])}
    results = [
        CheckResult(
            question_id=q,
            choice=answers.get(q),
            answer=graph.questions[q].answer,
            correct=answers.get(q) == graph.questions[q].answer,
        )
        for q in b.check
    ]

    # 처음 끝낸 시각만 남긴다 (오늘 남은 시간 계산용)
    db.execute(
        update(PlanBlock)
        .where(PlanBlock.user_id == user.id, PlanBlock.block_id == block_id, PlanBlock.done.is_(False))
        .values(done=True, done_at=now())
    )
    db.commit()

    ids = [r.block_id for r in plan_rows(db, user.id)]
    done_ids = {r.block_id for r in plan_rows(db, user.id) if r.done}
    after = ids[ids.index(block_id) + 1 :] if block_id in ids else ids
    rest = [i for i in after if i not in done_ids]
    return CompleteResponse(
        block_id=block_id,
        done=True,
        correct_count=sum(r.correct for r in results),
        total_count=len(b.check),
        results=results,
        next_block_id=rest[0] if rest else None,
    )
