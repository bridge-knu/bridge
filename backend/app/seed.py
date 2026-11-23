"""심사위원용 데모 계정.

- 공용 데모 계정(demo / 0000): 서버가 시작할 때 없으면 만들고, 처음 상태로 되돌린다.
  (프로필은 데모 값으로, 블록 완료 표시·저장한 코드는 지우고, 진단이 중간에 멈춰 있으면 다시 채움)
  프로필 저장·진단 다시 시작은 API에서 막는다. 블록 완료·코드 저장은 체험에 필요해서 막지 않는다.
- 체험 계정(demo-xxxxxx): 로그인 화면의 "체험하기"를 누를 때마다 새로 만든다.
  여러 명이 demo 하나를 같이 쓰면 한 명이 진단을 다시 할 때 다른 사람 결과도 바뀌기 때문이다.

둘 다 프로필과 진단 결과까지 넣어 두어서 로그인하면 바로 플랜·개념 그래프를 볼 수 있다.
진단은 "기초(안정성 24개월 이상)는 맞히고 까다로운 개념은 틀리는" 학생으로 엔진을 실제로 돌려서 만든다.
"""

import datetime as dt
import secrets

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DEMO_LOGIN_ID
from app.api.diagnosis import engine_profile, load_state, save_state
from app.content import get_graph
from app.engine import diagnosis as engine
from app.models import CodeSnapshot, PlanBlock, PlanInfo, Profile, User
from app.security import hash_pin

DEMO_PIN = "0000"
TRIAL_PREFIX = "demo-"


DEMO_PROFILE = {
    "completed_courses": [{"course": "C", "grade": "B0"}],
    "gap_months": 24,
    "target_course": "DS",
    "return_date": dt.date(2027, 3, 2),
    "daily_minutes": 60,
}


def fill_demo_data(db: Session, user_id: int) -> None:
    """프로필과 진단 결과가 없으면 데모 값으로 채운다."""
    if db.get(Profile, user_id) is None:
        db.add(Profile(user_id=user_id, **DEMO_PROFILE))
        db.flush()
    # 진단이 없거나 중간에 멈춰 있으면(예전에 누가 demo로 다시 시작하고 나감) 다시 채운다
    state = load_state(db, user_id)
    if state is None or not state.done:
        seed_demo_diagnosis(db, user_id)


def ensure_demo_user(db: Session) -> None:
    user = db.scalar(select(User).where(User.login_id == DEMO_LOGIN_ID))
    if user is None:
        user = User(login_id=DEMO_LOGIN_ID, pin_hash=hash_pin(DEMO_PIN))
        db.add(user)
        db.flush()
    reset_demo_profile(db, user.id)
    reset_demo_activity(db, user.id)
    fill_demo_data(db, user.id)
    db.commit()


def reset_demo_profile(db: Session, user_id: int) -> None:
    """공용 demo 프로필이 바뀌어 있으면 데모 값으로 되돌리고, 다음 GET /plan에서 플랜을 다시 만들게 한다."""
    row = db.get(Profile, user_id)
    if row is None or all(getattr(row, k) == v for k, v in DEMO_PROFILE.items()):
        return
    for k, v in DEMO_PROFILE.items():
        setattr(row, k, v)
    db.execute(delete(PlanInfo).where(PlanInfo.user_id == user_id))
    db.flush()


def reset_demo_activity(db: Session, user_id: int) -> None:
    """공용 demo에 남은 블록 완료 표시와 저장한 코드를 지운다.

    다음 사람이 "완료", "오늘 남은 시간 0분"이나 남이 쓴 코드(정답일 수도 있음)를 보지 않게 한다.
    플랜은 다음 GET /plan에서 오늘부터 새로 만든다.
    """
    db.execute(delete(CodeSnapshot).where(CodeSnapshot.user_id == user_id))
    db.execute(delete(PlanBlock).where(PlanBlock.user_id == user_id))
    db.execute(delete(PlanInfo).where(PlanInfo.user_id == user_id))
    db.flush()


def create_trial_user(db: Session) -> User:
    """데모 데이터를 채운 체험 계정을 새로 만든다.

    PIN은 아무도 모르는 임의 값이라 이 계정에는 받은 토큰으로만 들어갈 수 있다.
    """
    for _ in range(5):
        user = User(login_id=TRIAL_PREFIX + secrets.token_hex(3), pin_hash=hash_pin(secrets.token_hex(16)))
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            # 같은 아이디가 이미 있으면 다른 아이디로 다시
            db.rollback()
            continue
        fill_demo_data(db, user.id)
        db.commit()
        return user
    raise RuntimeError("체험 계정 아이디를 만들지 못했어요")


def seed_demo_diagnosis(db: Session, user_id: int) -> None:
    graph = get_graph()
    state = engine.start_diagnosis(engine_profile(db, user_id), graph)
    while (question := engine.next_question(state, graph)) is not None:
        knows = graph.concepts[question.concept].stability >= 24
        engine.apply_answer(state, question.id, knows, graph)
    save_state(db, user_id, state)
