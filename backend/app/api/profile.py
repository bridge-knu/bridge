from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import models
from app.api.deps import get_current_user
from app.api.mock_data import now
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
    summary="이수 과목·공백·복학일·하루 시간 저장",
    description="사용자당 1개. 다시 저장하면 덮어쓴다.",
)
def save_profile(
    body: Profile,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    values = body.model_dump()
    saved_at = now()
    stmt = insert(models.Profile).values(user_id=user.id, updated_at=saved_at, **values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[models.Profile.user_id],
        set_={**values, "updated_at": saved_at},
    )
    db.execute(stmt)
    db.commit()
    return ProfileResponse(**values, updated_at=saved_at)
