from fastapi import APIRouter, Depends

from app.api.blocks import NOT_FOUND, get_block_or_404
from app.api.mock_data import UserState, current_user, now
from app.api.schemas import CodeSaveRequest, CodeSaveResponse

router = APIRouter(tags=["code"])


@router.put(
    "/code/{block_id}",
    response_model=CodeSaveResponse,
    responses=NOT_FOUND,
    summary="코드 자동 저장 (블록당 1개, 덮어쓰기)",
)
def save_code(block_id: str, body: CodeSaveRequest, user: UserState = Depends(current_user)):
    get_block_or_404(block_id)
    saved_at = now()
    user.code[block_id] = (body.code, saved_at)
    return CodeSaveResponse(block_id=block_id, updated_at=saved_at)
