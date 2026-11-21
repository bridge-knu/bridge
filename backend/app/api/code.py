from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.blocks import NOT_FOUND, get_block_or_404
from app.api.deps import get_current_user
from app.clock import now
from app.api.schemas import CodeSaveRequest, CodeSaveResponse
from app.db import get_db
from app.models import CodeSnapshot, User

router = APIRouter(tags=["code"])


@router.put(
    "/code/{block_id}",
    response_model=CodeSaveResponse,
    responses=NOT_FOUND,
    summary="코드 자동 저장 (블록당 1개, 덮어쓰기)",
    description="화면은 입력이 멈추고 3초 뒤에 호출한다. 저장한 코드는 GET /blocks/{blockId}의 savedCode로 돌아온다.",
)
def save_code(
    block_id: str,
    body: CodeSaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_block_or_404(block_id)
    saved_at = now()
    stmt = insert(CodeSnapshot).values(user_id=user.id, block_id=block_id, code=body.code, updated_at=saved_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=[CodeSnapshot.user_id, CodeSnapshot.block_id],
        set_={"code": body.code, "updated_at": saved_at},
    )
    db.execute(stmt)
    db.commit()
    return CodeSaveResponse(block_id=block_id, updated_at=saved_at)
