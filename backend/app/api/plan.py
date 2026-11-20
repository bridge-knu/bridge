from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.mock_data import BLOCKS, CONCEPT_NAME, UserState, current_user
from app.api.profile import load_profile
from app.api.schemas import DeferredConcept, Plan, PlanBlock, PlanDay, Profile
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/plan", tags=["plan"])


def build_plan(user: UserState, profile: Profile | None) -> Plan:
    daily = profile.daily_minutes if profile else 60
    return_date = profile.return_date if profile else date.today() + timedelta(days=90)
    per_day = max(1, daily // 30)

    # 엔진과 같은 규칙: 복학 전날까지 쓸 수 있는 블록 수를 넘으면 뒤쪽 개념부터 미룬다
    budget = max((return_date - date.today()).days, 0) * per_day
    planned, deferred = BLOCKS[:budget], BLOCKS[budget:]

    days: list[PlanDay] = []
    for i in range(0, len(planned), per_day):
        chunk = planned[i : i + per_day]
        days.append(
            PlanDay(
                date=date.today() + timedelta(days=len(days)),
                blocks=[
                    PlanBlock(
                        order=n,
                        block_id=b["id"],
                        concept_id=b["concept"],
                        concept_name=CONCEPT_NAME[b["concept"]],
                        minutes=b["minutes"],
                        done=b["id"] in user.done_blocks,
                    )
                    for n, b in enumerate(chunk, start=1)
                ],
            )
        )

    today_left = sum(b.minutes for b in days[0].blocks if not b.done) if days else 0
    deferred_concepts = [
        DeferredConcept(concept_id=b["concept"], concept_name=CONCEPT_NAME[b["concept"]], blocks=1)
        for b in deferred
    ]
    names = ", ".join(d.concept_name for d in deferred_concepts)
    return Plan(
        return_date=return_date,
        daily_minutes=daily,
        today_remaining_minutes=today_left,
        days=days,
        deferred_concepts=deferred_concepts,
        message=f"시간이 부족해 {names}은(는) 복학 후로 미뤘어요" if deferred_concepts else None,
    )


@router.post("/generate", response_model=Plan, summary="역산 플랜 생성")
def generate(
    user: UserState = Depends(current_user),
    account: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.plan_created = True
    return build_plan(user, load_profile(db, account.id))


@router.get("", response_model=Plan, summary="날짜별 블록 목록, 오늘 남은 시간")
def get_plan(
    user: UserState = Depends(current_user),
    account: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_plan(user, load_profile(db, account.id))
