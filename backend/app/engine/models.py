"""content/*.json 데이터 모델과 검증.

concepts.json  : 개념 지도 (노드 + 선수 관계)
questions.json : 진단·확인 문제
blocks.json    : 30분 학습 블록 (강의 구간 + 실습 + 확인 문제)

각 파일은 개별 모델로 형식을 검사하고, ContentSet에서
파일 간 참조(없는 개념, 없는 문제 등)를 한 번 더 검사한다.
사이클 검사와 위상 정렬은 graph.py(load_graph)에서 한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"


class _Base(BaseModel):
    # JSON의 camelCase 키(videoStart 등)와 파이썬 이름을 모두 허용,
    # 오타 난 키는 조용히 무시하지 않고 에러로 알린다.
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Concept(_Base):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    course: Literal["C", "DS"]  # C: C프로그래밍, DS: 자료구조
    prereqs: list[str] = Field(default_factory=list)
    stability: float = Field(gt=0)  # 망각 곡선의 S(개월). 기초 36, 까다로운 개념 12
    blocks: int = Field(ge=1, le=3)  # 이 개념에 필요한 30분 블록 수

    @model_validator(mode="after")
    def _check_prereqs(self) -> Concept:
        if self.id in self.prereqs:
            raise ValueError(f"개념 '{self.id}'가 자기 자신을 선수 개념으로 가짐")
        if len(set(self.prereqs)) != len(self.prereqs):
            raise ValueError(f"개념 '{self.id}'의 prereqs에 중복이 있음")
        return self


class Question(_Base):
    id: str = Field(pattern=ID_PATTERN)
    concept: str
    type: Literal["choice"] = "choice"
    prompt: str = Field(min_length=1)
    code: str | None = None  # 코드 문제일 때 하이라이트해서 보여줄 코드
    choices: list[str] = Field(min_length=2)
    answer: int = Field(ge=0)  # choices의 0부터 시작하는 인덱스

    @model_validator(mode="after")
    def _check_answer(self) -> Question:
        if self.answer >= len(self.choices):
            raise ValueError(
                f"문제 '{self.id}'의 answer({self.answer})가 보기 개수({len(self.choices)})를 벗어남"
            )
        if len(set(self.choices)) != len(self.choices):
            raise ValueError(f"문제 '{self.id}'에 같은 보기가 중복됨")
        return self


class Practice(_Base):
    lang: Literal["c", "python"]
    starter: str
    expected: str  # 정답 코드를 실행했을 때의 표준 출력 (줄바꿈 포함)


class Block(_Base):
    id: str = Field(pattern=ID_PATTERN)
    concept: str
    minutes: int = Field(default=30, gt=0)
    video: str = Field(pattern=r"^https://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)\S+$")
    video_start: int = Field(alias="videoStart", ge=0)  # 초 단위
    video_end: int = Field(alias="videoEnd", gt=0)  # 초 단위
    practice: Practice
    check: list[str] = Field(default_factory=list)  # 블록 끝에 푸는 확인 문제 id

    @model_validator(mode="after")
    def _check_video_range(self) -> Block:
        if self.video_end <= self.video_start:
            raise ValueError(
                f"블록 '{self.id}'의 videoEnd({self.video_end})가 videoStart({self.video_start})보다 커야 함"
            )
        return self


class ContentSet(_Base):
    """세 파일을 묶어서 파일 간 참조를 검사한다."""

    concepts: list[Concept]
    questions: list[Question]
    blocks: list[Block]

    @model_validator(mode="after")
    def _check_references(self) -> ContentSet:
        errors: list[str] = []

        def unique_ids(items, kind: str) -> set[str]:
            seen: set[str] = set()
            for item in items:
                if item.id in seen:
                    errors.append(f"{kind} id 중복: '{item.id}'")
                seen.add(item.id)
            return seen

        concept_ids = unique_ids(self.concepts, "개념")
        question_ids = unique_ids(self.questions, "문제")
        unique_ids(self.blocks, "블록")

        for c in self.concepts:
            for p in c.prereqs:
                if p not in concept_ids:
                    errors.append(f"개념 '{c.id}'의 선수 개념 '{p}'가 concepts.json에 없음")

        question_concept = {q.id: q.concept for q in self.questions}
        for q in self.questions:
            if q.concept not in concept_ids:
                errors.append(f"문제 '{q.id}'의 개념 '{q.concept}'가 concepts.json에 없음")

        for b in self.blocks:
            if b.concept not in concept_ids:
                errors.append(f"블록 '{b.id}'의 개념 '{b.concept}'가 concepts.json에 없음")
            for qid in b.check:
                if qid not in question_ids:
                    errors.append(f"블록 '{b.id}'의 확인 문제 '{qid}'가 questions.json에 없음")
                elif question_concept[qid] != b.concept:
                    errors.append(
                        f"블록 '{b.id}'의 확인 문제 '{qid}'는 다른 개념('{question_concept[qid]}')의 문제임"
                    )

        if errors:
            raise ValueError("콘텐츠 참조 오류:\n- " + "\n- ".join(errors))
        return self


def load_content(content_dir: str | Path) -> ContentSet:
    """content 폴더의 JSON 3개를 읽어 검증된 ContentSet으로 돌려준다."""
    base = Path(content_dir)

    def read(name: str):
        with open(base / name, encoding="utf-8") as f:
            return json.load(f)

    return ContentSet(
        concepts=read("concepts.json"),
        questions=read("questions.json"),
        blocks=read("blocks.json"),
    )
