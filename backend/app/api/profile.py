from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models
from app.api.deps import DEMO_LOGIN_ID, get_current_user
from app.api.errors import ApiError, responses
from app.clock import now
from app.api.schemas import Profile, ProfileResponse
from app.db import get_db

router = APIRouter(tags=["profile"])

FIELDS = ("completed_courses", "gap_months", "target_course", "return_date", "daily_minutes")


def load_profile(db: Session, user_id: int) -> Profile | None:
    """저장된 프로필. 아직 입력하지 않았으면 None."""
    row = db.get(models.Profile, user_id)
    if row is None:
        return None
    return Profile.model_validate({f: getattr(row, f) for f in FIELDS})


@router.put(
    "/profile",
    response_model=ProfileResponse,
    responses=responses("DEMO_READ_ONLY"),
    summary="이수 과목·공백·복학일·하루 시간 저장",
    description=(
        "사용자당 1개. 다시 저장하면 덮어쓰고, 다음 GET /plan에서 플랜을 새 값으로 다시 만든다. "
        "공용 데모 계정(demo)은 여러 명이 같이 쓰므로 바꿀 수 없다 (403 DEMO_READ_ONLY)."
    ),
)
def save_profile(
    body: Profile,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 한 명이 demo 프로필을 바꾸면 모든 사람의 demo 복학일·플랜이 바뀌므로 막는다 (체험 계정은 가능)
    if user.login_id == DEMO_LOGIN_ID:
        raise ApiError("DEMO_READ_ONLY")
    values = body.model_dump()
    saved_at = now()
    stmt = insert(models.Profile).values(user_id=user.id, updated_at=saved_at, **values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.Profile.user_id],
        set_={**values, "updated_at": saved_at},
    )
    db.execute(stmt)
    # 복학일·하루 시간이 바뀌었을 수 있으니 다음 GET /plan에서 플랜을 다시 만든다
    db.execute(delete(models.PlanInfo).where(models.PlanInfo.user_id == user.id))
    db.commit()
    return ProfileResponse(**values, updated_at=saved_at)
