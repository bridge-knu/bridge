import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.engine.models import Block, Concept, ContentSet, Question, load_content

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"


@pytest.fixture
def sample() -> ContentSet:
    return load_content(CONTENT_DIR)


def _raw(sample: ContentSet) -> dict:
    return copy.deepcopy(sample.model_dump(by_alias=True))


def test_content_loads(sample):
    assert len(sample.concepts) == 22
    assert {c.course for c in sample.concepts} == {"C", "DS"}
    # 개념마다 진단 문제 2개 이상
    for c in sample.concepts:
        assert sum(q.concept == c.id for q in sample.questions) >= 2, c.id
    assert sample.blocks[0].video_start == 0


def test_unknown_prereq_is_error(sample):
    raw = _raw(sample)
    raw["concepts"][1]["prereqs"].append("ghost")
    with pytest.raises(ValidationError, match="선수 개념 'ghost'"):
        ContentSet(**raw)


def test_duplicate_id_is_error(sample):
    raw = _raw(sample)
    raw["questions"].append(raw["questions"][0])
    with pytest.raises(ValidationError, match="문제 id 중복"):
        ContentSet(**raw)


def test_block_check_must_exist(sample):
    raw = _raw(sample)
    raw["blocks"][0]["check"] = ["q-nothing"]
    with pytest.raises(ValidationError, match="q-nothing"):
        ContentSet(**raw)


def test_block_check_must_be_same_concept(sample):
    raw = _raw(sample)
    raw["blocks"][0]["check"] = ["q-pointer-2"]
    with pytest.raises(ValidationError, match="다른 개념"):
        ContentSet(**raw)


def test_self_prereq_is_error():
    with pytest.raises(ValidationError, match="자기 자신"):
        Concept(id="pointer", name="포인터", course="C", prereqs=["pointer"], stability=12, blocks=1)


def test_answer_out_of_range_is_error():
    with pytest.raises(ValidationError, match="answer"):
        Question(id="q-x", concept="array", prompt="?", choices=["a", "b"], answer=2)


def test_video_range_is_checked():
    with pytest.raises(ValidationError, match="videoEnd"):
        Block(
            id="b-x",
            concept="array",
            video="https://www.youtube.com/watch?v=abc",
            videoStart=100,
            videoEnd=50,
            practice={"lang": "c", "starter": "", "expected": ""},
        )


def test_unknown_field_is_error():
    with pytest.raises(ValidationError):
        Concept(id="array", name="배열", course="C", stability=24, blocks=1, prereq=["x"])
