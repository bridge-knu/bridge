"""API 요청·응답 스키마.

JSON 필드는 camelCase로 주고받는다 (파이썬 코드에서는 snake_case).
오류 응답은 FastAPI 기본 형태인 {"detail": "안내 문구"}를 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorResponse(CamelModel):
    detail: str


# ---- 인증 ----


class LoginRequest(CamelModel):
    login_id: str = Field(min_length=1, max_length=30, examples=["demo"])
    pin: str = Field(pattern=r"^\d{4}$", examples=["0000"])


class LoginResponse(CamelModel):
    token: str
    is_new_user: bool


# ---- 프로필 ----


class CompletedCourse(CamelModel):
    course: str = Field(examples=["C프로그래밍"])
    grade: str | None = Field(default=None, examples=["B+"])


class Profile(CamelModel):
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    gap_months: int = Field(ge=0, le=120, examples=[24])
    target_course: str = Field(examples=["DS"])
    return_date: date = Field(examples=["2027-03-02"])
    daily_minutes: int = Field(ge=30, le=600, examples=[120])


class ProfileResponse(Profile):
    updated_at: datetime


# ---- 진단 ----


class QuestionOut(CamelModel):
    """화면에 보여줄 문제. 정답은 내려주지 않는다."""

    id: str
    concept_id: str
    concept_name: str
    prompt: str
    code: str | None = None
    choices: list[str]


class DiagnosisAnswerRequest(CamelModel):
    question_id: str
    choice: int = Field(ge=0)


class DiagnosisStep(CamelModel):
    """진단 시작·답 제출 응답. done이 true이면 question은 null."""

    done: bool
    correct: bool | None = Field(default=None, description="방금 낸 답의 정답 여부 (start에서는 null)")
    question: QuestionOut | None
    answered_count: int
    max_questions: int


class ConceptResult(CamelModel):
    id: str
    name: str
    course: str
    prereqs: list[str]
    mastery: float = Field(ge=0, le=1, description="0~1. 그래프 색깔에 사용")
    source: Literal["prior", "diagnosed"] = Field(
        description="prior: 망각 추정값, diagnosed: 진단 문제로 확인한 값"
    )


class DiagnosisResult(CamelModel):
    concepts: list[ConceptResult]


# ---- 플랜 ----


class PlanBlock(CamelModel):
    order: int
    block_id: str
    concept_id: str
    concept_name: str
    minutes: int
    done: bool


class PlanDay(CamelModel):
    date: date
    blocks: list[PlanBlock]


class Plan(CamelModel):
    return_date: date
    daily_minutes: int
    today_remaining_minutes: int
    days: list[PlanDay]


# ---- 블록 학습 ----


class Video(CamelModel):
    url: str
    start: int = Field(description="초")
    end: int = Field(description="초")


class Practice(CamelModel):
    lang: Literal["c", "python"]
    starter: str
    expected: str = Field(description="정답 코드를 실행했을 때의 표준 출력")


class BlockDetail(CamelModel):
    id: str
    concept_id: str
    concept_name: str
    minutes: int
    video: Video
    practice: Practice
    check_questions: list[QuestionOut]
    saved_code: str | None = Field(description="마지막으로 저장된 코드. 없으면 null")
    saved_at: datetime | None
    done: bool


class CheckAnswer(CamelModel):
    question_id: str
    choice: int = Field(ge=0)


class CompleteRequest(CamelModel):
    check_answers: list[CheckAnswer] = Field(default_factory=list)


class CompleteResponse(CamelModel):
    block_id: str
    done: bool
    correct_count: int
    total_count: int
    next_block_id: str | None


# ---- 코드 저장·실행 ----


class CodeSaveRequest(CamelModel):
    code: str = Field(max_length=65536)


class CodeSaveResponse(CamelModel):
    block_id: str
    updated_at: datetime


class RunRequest(CamelModel):
    lang: Literal["c", "python"]
    code: str = Field(max_length=65536)
    stdin: str = Field(default="", max_length=65536)
    block_id: str | None = Field(default=None, description="블록 실습이면 넣는다. 정답 출력과 비교")


class RunAccepted(CamelModel):
    job_id: str


class RunResult(CamelModel):
    job_id: str
    status: Literal["queued", "running", "done"]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    duration_ms: int | None = None
    matches_expected: bool | None = Field(
        default=None, description="blockId를 보냈고 실행이 끝났을 때만 true/false"
    )
