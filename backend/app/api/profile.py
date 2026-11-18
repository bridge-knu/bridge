from fastapi import APIRouter, Depends

from app.api.mock_data import UserState, current_user, now
from app.api.schemas import Profile, ProfileResponse

router = APIRouter(tags=["profile"])


@router.put("/profile", response_model=ProfileResponse, summary="이수 과목·공백·복학일·하루 시간 저장")
def save_profile(body: Profile, user: UserState = Depends(current_user)):
    user.profile = body.model_dump()
    return ProfileResponse(**user.profile, updated_at=now())
