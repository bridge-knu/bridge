from datetime import date, timedelta

from fastapi import APIRouter, Depends

from app.api.mock_data import BLOCKS, CONCEPT_NAME, UserState, current_user
from app.api.schemas import Plan, PlanBlock, PlanDay

router = APIRouter(prefix="/plan", tags=["plan"])


def build_plan(user: UserState) -> Plan:
    profile = user.profile or {}
    daily = profile.get("daily_minutes", 60)
    return_date = profile.get("return_date", date.today() + timedelta(days=90))
    per_day = max(1, daily // 30)

    days: list[PlanDay] = []
    for i in range(0, len(BLOCKS), per_day):
        chunk = BLOCKS[i : i + per_day]
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
    return Plan(
        return_date=return_date,
        daily_minutes=daily,
        today_remaining_minutes=today_left,
        days=days,
    )


@router.post("/generate", response_model=Plan, summary="역산 플랜 생성")
def generate(user: UserState = Depends(current_user)):
    user.plan_created = True
    return build_plan(user)


@router.get("", response_model=Plan, summary="날짜별 블록 목록, 오늘 남은 시간")
def get_plan(user: UserState = Depends(current_user)):
    return build_plan(user)
