"""API 요청·응답 스키마.

JSON 필드는 camelCase로 주고받는다 (파이썬 코드에서는 snake_case).
오류 응답은 FastAPI 기본 형태인 {"detail": "안내 문구"}를 쓴다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorResponse(CamelModel):
    detail: str = Field(description="사용자에게 보여 줄 안내 문구")
    code: str = Field(description="화면 분기용 오류 코드 (README 참고)")


# ---- 인증 ----


class LoginRequest(CamelModel):
    # 제어 문자(NUL, 줄바꿈 등)는 받지 않는다. NUL은 PostgreSQL에 저장할 수 없다
    login_id: str = Field(min_length=1, max_length=30, pattern=r"^[^\x00-\x1f\x7f]+$", examples=["demo"])
    pin: str = Field(pattern=r"^\d{4}$", examples=["0000"])


class LoginResponse(CamelModel):
    token: str
    is_new_user: bool


# ---- 프로필 ----


# 과목 코드. content/concepts.json의 course와 같다 (C: C프로그래밍, DS: 자료구조).
CourseCode = Literal["C", "DS"]

# 성적 원본 값. D/F → 미이수, P → B 같은 정규화는 엔진이 한다.
Grade = Literal["A+", "A0", "A-", "B+", "B0", "B-", "C+", "C0", "C-", "D+", "D0", "D-", "F", "P"]


class CompletedCourse(CamelModel):
    """성적은 받은 그대로 저장한다 (A+, B0, P 등). 정규화는 엔진이 한다."""

    course: CourseCode = Field(examples=["C"])
    grade: Grade = Field(examples=["A+"])


class Profile(CamelModel):
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    gap_months: int = Field(ge=0, le=120, examples=[24])
    target_course: CourseCode = Field(examples=["DS"])
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


class DeferredConcept(CamelModel):
    """복학일까지 시간이 부족해 복학 후로 미룬 개념."""

    concept_id: str
    concept_name: str
    blocks: int = Field(description="이 개념에 필요했던 30분 블록 수")


class Plan(CamelModel):
    today: date = Field(description="서버 기준 오늘 날짜 (한국 시간). 화면은 브라우저 날짜 대신 이 값을 쓴다")
    return_date: date
    daily_minutes: int
    today_remaining_minutes: int = Field(
        description="오늘 공부할 수 있는 남은 시간(분) = 하루 가용 시간 - 오늘 완료한 블록 시간 (최소 0)"
    )
    days: list[PlanDay]
    deferred_concepts: list[DeferredConcept] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="미룬 개념이 있을 때만 안내 문구 (예: 시간이 부족해 연결 리스트은(는) 복학 후로 미뤘어요)",
    )


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


class CheckResult(CamelModel):
    """확인 문제 하나의 채점 결과. 화면에서 맞은 문제·틀린 문제와 정답을 보여 줄 때 쓴다."""

    question_id: str
    choice: int | None = Field(description="보낸 답 (안 보냈으면 null)")
    answer: int = Field(description="정답 보기 번호 (0부터)")
    correct: bool


class CompleteResponse(CamelModel):
    block_id: str
    done: bool
    correct_count: int
    total_count: int
    results: list[CheckResult] = Field(description="확인 문제 순서대로 문제별 채점 결과")
    next_block_id: str | None


# ---- 코드 저장·실행 ----


class CodeSaveRequest(CamelModel):
    code: str = Field(max_length=65536)

    @field_validator("code")
    @classmethod
    def _no_nul(cls, v: str) -> str:
        # PostgreSQL 텍스트에는 NUL 문자를 저장할 수 없어서 500이 난다. 요청 단계에서 422로 거부한다
        if "\x00" in v:
            raise ValueError("코드에 NUL 문자를 넣을 수 없어요")
        return v


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
