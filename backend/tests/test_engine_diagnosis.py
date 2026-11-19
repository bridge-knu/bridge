import pytest

from app.engine.diagnosis import (
    DiagnosisState,
    apply_answer,
    next_question,
    result_concepts,
    start_diagnosis,
)
from app.engine.graph import build_graph
from app.engine.models import ContentSet

# (id, course, prereqs, stability)
CONCEPTS = [
    ("variable", "C", [], 36),
    ("operator", "C", ["variable"], 36),
    ("condition", "C", ["operator"], 36),
    ("loop", "C", ["condition"], 36),
    ("function", "C", ["loop"], 24),
    ("array", "C", ["loop"], 24),
    ("pointer", "C", ["array", "function"], 12),
    ("struct", "C", ["variable"], 18),
    ("dynamic_alloc", "C", ["pointer"], 12),
    ("recursion", "C", ["function"], 12),
    ("stack", "DS", ["array", "struct"], 18),
    ("linked_list", "DS", ["struct", "dynamic_alloc"], 12),
    ("binary_tree", "DS", ["linked_list", "recursion"], 12),
]


def _graph(concepts=CONCEPTS, questions_per_concept=2):
    cs = [{"id": i, "name": i, "course": c, "prereqs": p, "stability": s, "blocks": 1}
          for i, c, p, s in concepts]
    qs = [{"id": f"q-{i}-{n}", "concept": i, "prompt": "?", "choices": ["o", "x"], "answer": 0}
          for i, *_ in concepts for n in range(1, questions_per_concept + 1)]
    return build_graph(ContentSet(concepts=cs, questions=qs, blocks=[]))


@pytest.fixture
def g():
    return _graph()


def _profile(gap, grade="A0"):
    return {"completedCourses": [{"course": "C", "grade": grade}], "gapMonths": gap,
            "targetCourse": "DS"}


def _run(state, g, answer_fn):
    """끝날 때까지 문제를 풀고, 출제된 개념 순서를 돌려준다."""
    asked = []
    while (q := next_question(state, g)) is not None:
        asked.append(q.concept)
        apply_answer(state, q.id, answer_fn(q), g)
    return asked


# ---- 개발 가이드 5-5 테스트 케이스 ----

def test_gap_0_grade_a_asks_almost_nothing(g):
    state = start_diagnosis(_profile(0), g)
    assert next_question(state, g) is None
    assert state.done
    assert state.answered_count == 0


def test_short_gap_asks_only_hard_concepts(g):
    # 2개월: 기초(S=36)는 0.8 이상이라 안 묻고, 까다로운 개념(S=12)만 후보
    state = start_diagnosis(_profile(2), g)
    assert set(state.candidates) == {"pointer", "dynamic_alloc", "recursion"}


def test_gap_24_months_includes_basics(g):
    state = start_diagnosis(_profile(24), g)
    assert "variable" in state.candidates
    assert "operator" in state.candidates


def test_all_wrong_goes_down_to_most_basic_within_10(g):
    state = start_diagnosis(_profile(24), g)
    asked = _run(state, g, lambda q: False)
    assert "variable" in asked              # 가장 기초까지 내려감
    assert len(asked) <= 10
    assert state.done


def test_never_more_than_10_questions():
    chain = [("c0", "C", [], 12)] + [(f"c{i}", "C", [f"c{i-1}"], 12) for i in range(1, 15)]
    chain.append(("target", "DS", ["c14"], 12))
    g = _graph(chain)
    state = start_diagnosis(_profile(24), g)
    asked = _run(state, g, lambda q: False)
    assert len(asked) == 10
    assert state.done


# ---- 규칙 ----

def test_first_question_is_closest_to_target(g):
    state = start_diagnosis(_profile(24), g)
    q = next_question(state, g)
    assert q.concept == "dynamic_alloc"     # 가장 깊은 선수 개념


def test_wrong_goes_to_direct_prereq(g):
    state = start_diagnosis(_profile(24), g)
    q = next_question(state, g)                      # dynamic_alloc
    apply_answer(state, q.id, False, g)
    assert state.mastery["dynamic_alloc"] == 0.2
    assert next_question(state, g).concept == "pointer"


def test_correct_skips_prereqs(g):
    state = start_diagnosis(_profile(24), g)
    q = next_question(state, g)                      # dynamic_alloc
    apply_answer(state, q.id, True, g)
    assert state.mastery["dynamic_alloc"] == 0.9
    # dynamic_alloc의 선수 개념(pointer, array, loop ... variable)은 더 묻지 않음
    assert set(state.candidates) == {"struct", "recursion"}
    assert state.mastery["variable"] >= 0.8
    assert state.source["variable"] == "diagnosed"


def test_target_course_concepts_are_not_asked(g):
    state = start_diagnosis({"completedCourses": [], "gapMonths": 0, "targetCourse": "DS"}, g)
    asked = _run(state, g, lambda q: True)
    assert not {"stack", "linked_list", "binary_tree"} & set(asked)


def test_wrong_question_id_is_rejected(g):
    state = start_diagnosis(_profile(24), g)
    next_question(state, g)
    with pytest.raises(ValueError, match="지금 풀고 있는 문제가 아니에요"):
        apply_answer(state, "q-variable-1", True, g)


def test_answer_without_question_is_rejected(g):
    state = start_diagnosis(_profile(24), g)
    with pytest.raises(ValueError, match="진행 중인 문제가 없어요"):
        apply_answer(state, "q-variable-1", True, g)


def test_next_question_is_stable_until_answered(g):
    state = start_diagnosis(_profile(24), g)
    assert next_question(state, g).id == next_question(state, g).id


# ---- 결과·저장 ----

def test_result_concepts_shape_and_order(g):
    state = start_diagnosis(_profile(24), g)
    q = next_question(state, g)
    apply_answer(state, q.id, False, g)
    concepts = result_concepts(state, g)
    ids = [c["id"] for c in concepts]
    for c in concepts:
        for p in c["prereqs"]:
            assert ids.index(p) < ids.index(c["id"])
        assert set(c) == {"id", "name", "course", "prereqs", "mastery", "source"}
    by_id = {c["id"]: c for c in concepts}
    assert by_id["dynamic_alloc"] == {**by_id["dynamic_alloc"], "mastery": 0.2, "source": "diagnosed"}
    assert by_id["stack"]["source"] == "prior"   # 목표 과목 개념은 prior 그대로
    assert by_id["stack"]["mastery"] == 0.1


def test_state_round_trip(g):
    state = start_diagnosis(_profile(24), g)
    q = next_question(state, g)
    restored = DiagnosisState.from_dict(state.to_dict())
    apply_answer(restored, q.id, True, g)
    assert restored.answered_count == 1
