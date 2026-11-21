"""DB 테이블 (개발 가이드 4장 DB 표).

개념·문제·블록 같은 콘텐츠는 DB에 넣지 않고 content/*.json에 둔다.
그래서 concept_id, question_id, block_id는 외래 키가 아니라 문자열이다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ID = String(64)  # content/*.json의 id 길이


def user_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def created_now() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_now() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    """짧은 아이디 + PIN 로그인."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login_id: Mapped[str] = mapped_column(String(30), unique=True)
    pin_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = created_now()


class Profile(Base):
    """진단·플랜 입력값. 사용자당 1개."""

    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    completed_courses: Mapped[list] = mapped_column(JSONB, server_default="[]")
    gap_months: Mapped[int] = mapped_column(Integer)
    target_course: Mapped[str] = mapped_column(String(30))
    return_date: Mapped[dt.date] = mapped_column(Date)
    daily_minutes: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[dt.datetime] = updated_now()


class DiagnosisAnswer(Base):
    """진단 기록. 답을 낼 때마다 한 줄."""

    __tablename__ = "diagnosis_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_fk()
    question_id: Mapped[str] = mapped_column(ID)
    concept_id: Mapped[str] = mapped_column(ID)
    correct: Mapped[bool] = mapped_column(Boolean)
    answered_at: Mapped[dt.datetime] = created_now()


class ConceptState(Base):
    """개념별 이해도. 그래프 색깔에 쓴다."""

    __tablename__ = "concept_states"
    __table_args__ = (
        CheckConstraint("mastery >= 0 AND mastery <= 1", name="mastery_range"),
        CheckConstraint("source IN ('prior', 'diagnosed')", name="source_values"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ID, primary_key=True)
    mastery: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[dt.datetime] = updated_now()


class PlanBlock(Base):
    """날짜별 30분 블록. 플랜을 다시 만들면 사용자의 행을 지우고 새로 넣는다."""

    __tablename__ = "plan_blocks"
    __table_args__ = (UniqueConstraint("user_id", "date", "order", name="uq_plan_blocks_day_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = user_fk()
    date: Mapped[dt.date] = mapped_column(Date)
    order: Mapped[int] = mapped_column(Integer)
    block_id: Mapped[str] = mapped_column(ID)
    done: Mapped[bool] = mapped_column(Boolean, server_default="false")
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 오늘 남은 시간 계산용


class PlanInfo(Base):
    """플랜 한 벌의 정보. 사용자당 1개. 없으면 GET /plan이 플랜을 새로 만든다.

    프로필을 바꾸거나 진단을 다시 끝내면 지워서, 다음 GET /plan에서 새 값으로 다시 만들게 한다.
    """

    __tablename__ = "plan_infos"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    deferred: Mapped[list] = mapped_column(JSONB, server_default="[]")  # 미룬 개념 [{concept_id, concept_name, blocks}]
    created_at: Mapped[dt.datetime] = created_now()


class DiagnosisSession(Base):
    """진행 중이거나 마지막으로 끝낸 진단의 엔진 상태 (DiagnosisState.to_dict()). 사용자당 1개."""

    __tablename__ = "diagnosis_sessions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[dt.datetime] = updated_now()


class CodeSnapshot(Base):
    """자동 저장. 블록당 1개를 덮어쓴다."""

    __tablename__ = "code_snapshots"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    block_id: Mapped[str] = mapped_column(ID, primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = updated_now()
