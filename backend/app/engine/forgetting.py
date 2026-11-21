"""망각 추정: 진단을 어디서부터 시작할지 정하는 사전 이해도(prior).

이수한 과목의 개념은 "당시 성적"에서 시작해 공백 기간만큼 잊혀진다고 본다.
에빙하우스 망각 곡선을 단순화한 식:

    prior = base(성적) × e^(-공백개월 / S)

- base: A=0.9, B=0.75, C=0.6, 미이수=0.1
- S(안정성): 개념마다 다름. 기초(변수, 반복문) 36, 까다로운 개념(포인터, 재귀) 12 등.
  값은 concepts.json의 stability.
- 미이수 과목의 개념은 공백과 상관없이 0.1.

수치는 가정이며 테스터 데이터로 보정할 예정이다.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .graph import Graph

Course = Literal["C", "DS"]
Grade = Literal["A+", "A0", "A-", "B+", "B0", "B-", "C+", "C0", "C-", "D+", "D0", "D-", "F", "P"]

BASE = {"A": 0.9, "B": 0.75, "C": 0.6}
NOT_COMPLETED = 0.1


class _CamelModel(BaseModel):
    # API는 camelCase(completedCourses), 엔진 안에서는 snake_case(completed_courses).
    # 둘 다 받을 수 있게 해서 API 계층이 그대로 넘겨도 되게 한다.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class CompletedCourse(_CamelModel):
    course: Course
    grade: Grade


class Profile(_CamelModel):
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    gap_months: int = Field(ge=0, le=120)
    target_course: Course = "DS"
    return_date: date | None = None
    daily_minutes: int | None = Field(default=None, ge=30, le=600)


def normalize_grade(grade: str) -> str | None:
    """원래 성적을 엔진용 A/B/C로 바꾼다. 미이수로 볼 성적(D, F)은 None.

    A+, A0, A- → A / B+, B0, B- → B / C+, C0, C- → C
    D+, D0, D-, F → None (미이수 취급) / P → B
    """
    if grade == "P":
        return "B"
    letter = grade[0]
    return letter if letter in BASE else None


def course_bases(profile: Profile) -> dict[str, float]:
    """과목별 base 값. 같은 과목이 여러 번 있으면(재수강) 가장 좋은 성적을 쓴다."""
    bases: dict[str, float] = {}
    for cc in profile.completed_courses:
        letter = normalize_grade(cc.grade)
        value = BASE[letter] if letter else NOT_COMPLETED
        bases[cc.course] = max(bases.get(cc.course, 0.0), value)
    return bases


def prior_mastery(profile: Profile | dict, graph: Graph) -> dict[str, float]:
    """개념 id → 사전 이해도(0~1). 그래프의 모든 개념에 대해 계산한다."""
    if not isinstance(profile, Profile):
        profile = Profile.model_validate(profile)

    bases = course_bases(profile)
    result: dict[str, float] = {}
    for cid in graph.topological_order():
        concept = graph.concepts[cid]
        base = bases.get(concept.course)
        if base is None or base == NOT_COMPLETED:
            result[cid] = NOT_COMPLETED
        else:
            result[cid] = round(base * math.exp(-profile.gap_months / concept.stability), 4)
    return result
