"""플랜 API. 엔진(app.engine.plan.build_plan)으로 만들고 plan_blocks에 저장한다.

- 이해도: 진단을 끝냈으면 concept_states, 아니면 프로필로 망각 추정한 값
- 플랜이 없으면(처음, 프로필 변경, 진단 다시 끝냄) GET /plan이 새로 만든다
- 날이 바뀌어 지난 날짜에 안 끝낸 블록이 있어도 GET /plan이 오늘부터 다시 배치한다
- 다시 만들어도 이미 끝낸 블록은 완료 표시를 유지한다
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.diagnosis import engine_profile
from app.api.profile import load_profile
from app.api.schemas import DeferredConcept, Plan, PlanBlock, PlanDay
from app.clock import KST, today
from app.content import concept_of_block, get_graph
from app.db import get_db
from app.engine import plan as engine
from app.engine.forgetting import prior_mastery
from app.models import ConceptState, PlanInfo, User
from app.models import PlanBlock as PlanBlockRow

router = APIRouter(prefix="/plan", tags=["plan"])

# 프로필이 없을 때
DEFAULT_DAILY_MINUTES = 60
DEFAULT_DAYS = 90


def plan_settings(db: Session, user_id: int):
    """(복학일, 하루 분). 프로필이 없으면 90일 뒤, 하루 60분."""
    profile = load_profile(db, user_id)
    if profile is None:
        return today() + timedelta(days=DEFAULT_DAYS), DEFAULT_DAILY_MINUTES
    return profile.return_date, profile.daily_minutes


def current_mastery(db: Session, user_id: int) -> dict[str, float]:
    rows = db.scalars(select(ConceptState).where(ConceptState.user_id == user_id)).all()
    if rows:
        return {r.concept_id: r.mastery for r in rows}
    # 진단 전: 목표 과목에 필요한 개념을 망각 추정값으로
    graph = get_graph()
    profile = engine_profile(db, user_id)
    prior = prior_mastery(profile, graph)
    return {c: prior[c] for c in graph.required_for_course(profile["target_course"])}


def block_minutes(block_id: str) -> int:
    block = get_graph().blocks.get(block_id)
    return block.minutes if block else engine.BLOCK_MINUTES


def plan_rows(db: Session, user_id: int) -> list[PlanBlockRow]:
    stmt = select(PlanBlockRow).where(PlanBlockRow.user_id == user_id).order_by(PlanBlockRow.date, PlanBlockRow.order)
    return list(db.scalars(stmt).all())


def generate_plan(db: Session, user_id: int) -> None:
    """오늘부터 다시 배치한다.

    - 어제까지 끝낸 블록은 그 날짜에 기록으로 남기고 새 배치에서 뺀다
    - 블록을 다 끝낸 개념은 배울 개념에서 뺀다 (남은 시간을 끝낸 개념에 쓰지 않게)
    - 오늘 끝낸 블록은 새 배치에서도 완료 표시를 유지한다
    """
    graph = get_graph()
    now = today()
    return_date, daily = plan_settings(db, user_id)
    rows = plan_rows(db, user_id)
    history = [r for r in rows if r.done and r.date < now]
    history_ids = {r.block_id for r in history}
    done_now = {r.block_id: r.done_at for r in rows if r.done and r.date >= now}

    mastery = current_mastery(db, user_id)
    for concept_id in mastery:
        if concept_id in graph.concepts and set(engine.block_ids_for(graph, concept_id)) <= history_ids:
            mastery[concept_id] = max(mastery[concept_id], engine.LEARN_THRESHOLD)
    result = engine.build_plan(mastery, graph, now, return_date, daily)

    # 엔진 순서는 그대로 두고, 어제까지 끝낸 블록만 빼서 오늘부터 다시 채운다
    ordered = [b.block_id for day in result.days for b in day.blocks if b.block_id not in history_ids]
    per_day = max(daily // engine.BLOCK_MINUTES, 1)

    db.execute(delete(PlanBlockRow).where(PlanBlockRow.user_id == user_id, PlanBlockRow.id.not_in([r.id for r in history])))
    db.execute(delete(PlanInfo).where(PlanInfo.user_id == user_id))
    db.flush()
    for i, block_id in enumerate(ordered):
        db.add(
            PlanBlockRow(
                user_id=user_id,
                date=now + timedelta(days=i // per_day),
                order=i % per_day + 1,
                block_id=block_id,
                done=block_id in done_now,
                done_at=done_now.get(block_id),
            )
        )
    deferred = [
        {"concept_id": d.concept_id, "concept_name": d.concept_name, "blocks": d.blocks} for d in result.deferred
    ]
    db.add(PlanInfo(user_id=user_id, deferred=deferred))
    db.commit()


def has_overdue(db: Session, user_id: int) -> bool:
    """어제까지 날짜인데 안 끝낸 블록이 있으면 True (날이 바뀌면 오늘부터 다시 배치)."""
    stmt = select(PlanBlockRow.id).where(
        PlanBlockRow.user_id == user_id, PlanBlockRow.date < today(), PlanBlockRow.done.is_(False)
    )
    return db.scalars(stmt.limit(1)).first() is not None


def read_plan(db: Session, user_id: int) -> Plan:
    graph = get_graph()
    now = today()
    return_date, daily = plan_settings(db, user_id)
    rows = plan_rows(db, user_id)
    info = db.get(PlanInfo, user_id)

    days: list[PlanDay] = []
    for row in rows:
        if not days or days[-1].date != row.date:
            days.append(PlanDay(date=row.date, blocks=[]))
        concept_id = concept_of_block(graph, row.block_id) or ""
        concept = graph.concepts.get(concept_id)
        days[-1].blocks.append(
            PlanBlock(
                order=row.order,
                block_id=row.block_id,
                concept_id=concept_id,
                concept_name=concept.name if concept else row.block_id,
                minutes=block_minutes(row.block_id),
                done=row.done,
            )
        )

    # 오늘 공부할 수 있는 남은 시간 = 하루 가용 시간 - 오늘(한국 날짜) 완료한 블록 시간
    done_today = sum(
        block_minutes(r.block_id) for r in rows if r.done and r.done_at and r.done_at.astimezone(KST).date() == now
    )
    deferred = [DeferredConcept(**d) for d in (info.deferred if info else [])]
    names = ", ".join(d.concept_name for d in deferred)
    return Plan(
        today=now,
        return_date=return_date,
        daily_minutes=daily,
        today_remaining_minutes=max(daily - done_today, 0),
        days=days,
        deferred_concepts=deferred,
        message=f"시간이 부족해 {names}은(는) 복학 후로 미뤘어요" if deferred else None,
    )


@router.post(
    "/generate",
    response_model=Plan,
    summary="역산 플랜 생성",
    description=(
        "진단 결과(없으면 망각 추정값)에서 이해도 0.6 미만인 개념을 선수 개념 먼저 오는 순서로, "
        "오늘부터 복학 전날까지 하루 시간만큼 30분 블록으로 배치한다. 이미 끝낸 블록은 완료 표시를 유지한다."
    ),
)
def generate(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    generate_plan(db, user.id)
    return read_plan(db, user.id)


@router.get(
    "",
    response_model=Plan,
    summary="날짜별 블록 목록, 오늘 남은 시간",
    description="플랜이 없거나 프로필·진단이 바뀌었거나 지난 날짜에 안 끝낸 블록이 있으면 오늘부터 새로 만들어서 준다.",
)
def get_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.get(PlanInfo, user.id) is None or has_overdue(db, user.id):
        generate_plan(db, user.id)
    return read_plan(db, user.id)
