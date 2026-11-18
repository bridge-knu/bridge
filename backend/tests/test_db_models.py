"""DB 모델 테스트. docker compose의 postgres가 떠 있어야 하고, 없으면 건너뛴다.

각 테스트는 트랜잭션 안에서 실행하고 끝나면 되돌리므로 DB에 데이터가 남지 않는다.
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db import database_url
from app.models import CodeSnapshot, ConceptState, PlanBlock, Profile, User

TABLES = {"users", "profiles", "diagnosis_answers", "concept_states", "plan_blocks", "code_snapshots"}


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(database_url())
    try:
        with eng.connect():
            pass
    except OperationalError:
        pytest.skip("postgres에 연결할 수 없음 (docker compose up -d 필요)")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    conn = engine.connect()
    tx = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    tx.rollback()
    conn.close()


def make_user(db, login_id="tester"):
    user = User(login_id=login_id, pin_hash="hash")
    db.add(user)
    db.flush()
    return user


def test_migration_created_all_tables(engine):
    assert TABLES <= set(inspect(engine).get_table_names())


def test_user_and_profile(db):
    user = make_user(db)
    db.add(
        Profile(
            user_id=user.id,
            completed_courses=[{"course": "C프로그래밍", "grade": "B+"}],
            gap_months=24,
            target_course="DS",
            return_date=dt.date(2027, 3, 2),
            daily_minutes=60,
        )
    )
    db.flush()
    profile = db.get(Profile, user.id)
    assert profile.completed_courses[0]["grade"] == "B+"
    assert user.created_at is not None


def test_login_id_is_unique(db):
    make_user(db, "same")
    with pytest.raises(IntegrityError):
        make_user(db, "same")


def test_mastery_must_be_between_0_and_1(db):
    user = make_user(db)
    db.add(ConceptState(user_id=user.id, concept_id="array", mastery=1.5, source="prior"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_code_snapshot_one_per_block(db):
    user = make_user(db)
    db.add(CodeSnapshot(user_id=user.id, block_id="b-array-1", code="v1"))
    db.flush()
    db.merge(CodeSnapshot(user_id=user.id, block_id="b-array-1", code="v2"))
    db.flush()
    rows = db.scalars(select(CodeSnapshot).where(CodeSnapshot.user_id == user.id)).all()
    assert [r.code for r in rows] == ["v2"]


def test_deleting_user_deletes_their_rows(db):
    user = make_user(db)
    db.add(PlanBlock(user_id=user.id, date=dt.date(2026, 11, 18), order=1, block_id="b-array-1"))
    db.flush()
    db.delete(user)
    db.flush()
    db.expunge_all()
    assert db.scalars(select(PlanBlock).where(PlanBlock.user_id == user.id)).all() == []
