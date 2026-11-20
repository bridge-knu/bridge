"""심사위원용 데모 계정. 서버가 시작할 때 없으면 만든다."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_pin

DEMO_LOGIN_ID = "demo"
DEMO_PIN = "0000"


def ensure_demo_user(db: Session) -> None:
    if db.scalar(select(User).where(User.login_id == DEMO_LOGIN_ID)) is None:
        db.add(User(login_id=DEMO_LOGIN_ID, pin_hash=hash_pin(DEMO_PIN)))
        db.commit()
