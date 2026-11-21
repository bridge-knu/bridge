"""심사위원용 데모 계정. 서버가 시작할 때 없으면 만든다.

프로필과 진단 결과까지 넣어 두어서 로그인하면 바로 플랜·개념 그래프를 볼 수 있다.
진단은 "기초(안정성 24개월 이상)는 맞히고 까다로운 개념은 틀리는" 학생으로 엔진을 실제로 돌려서 만든다.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.diagnosis import engine_profile, save_state
from app.content import get_graph
from app.engine import diagnosis as engine
from app.models import DiagnosisSession, Profile, User
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
        db.flush()
    if db.get(DiagnosisSession, user.id) is None:
        seed_demo_diagnosis(db, user.id)
    db.commit()


def seed_demo_diagnosis(db: Session, user_id: int) -> None:
    graph = get_graph()
    state = engine.start_diagnosis(engine_profile(db, user_id), graph)
    while (question := engine.next_question(state, graph)) is not None:
        knows = graph.concepts[question.concept].stability >= 24
        engine.apply_answer(state, question.id, knows, graph)
    save_state(db, user_id, state)
