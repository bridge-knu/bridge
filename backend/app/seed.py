"""심사위원용 데모 계정. 서버가 시작할 때 없으면 만든다.

프로필까지 넣어 두어서 로그인하면 바로 플랜 화면으로 간다.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, User
from app.security import hash_pin

DEMO_LOGIN_ID = "demo"
DEMO_PIN = "0000"


DEMO_PROFILE = {
    "completed_courses": [{"course": "C", "grade": "B0"}],
    "gap_months": 24,
    "target_course": "DS",
    "return_date": dt.date(2027, 3, 2),
    "daily_minutes": 60,
}


def ensure_demo_user(db: Session) -> None:
    user = db.scalar(select(User).where(User.login_id == DEMO_LOGIN_ID))
    if user is None:
        user = User(login_id=DEMO_LOGIN_ID, pin_hash=hash_pin(DEMO_PIN))
        db.add(user)
        db.flush()
    if db.get(Profile, user.id) is None:
        db.add(Profile(user_id=user.id, **DEMO_PROFILE))
    db.commit()
