import math

import pytest
from pydantic import ValidationError

from app.engine.forgetting import Profile, normalize_grade, prior_mastery
from app.engine.graph import build_graph
from app.engine.models import ContentSet


def _concept(cid, prereqs=(), course="C", stability=12):
    return {"id": cid, "name": cid, "course": course, "prereqs": list(prereqs),
            "stability": stability, "blocks": 1}


@pytest.fixture
def g():
    concepts = [
        _concept("variable", stability=36),            # 기초
        _concept("loop", ["variable"], stability=36),  # 기초
        _concept("pointer", ["loop"], stability=12),   # 까다로운 개념
        _concept("linked_list", ["pointer"], course="DS"),
    ]
    questions = [{"id": f"q-{c['id']}", "concept": c["id"], "prompt": "?",
                  "choices": ["a", "b"], "answer": 0} for c in concepts]
    return build_graph(ContentSet(concepts=concepts, questions=questions, blocks=[]))


def _profile(grade="A0", gap=0, course="C"):
    # API에서 오는 camelCase 그대로
    return {"completedCourses": [{"course": course, "grade": grade}], "gapMonths": gap,
            "targetCourse": "DS"}


def test_gap_0_grade_a(g):
    prior = prior_mastery(_profile("A+", gap=0), g)
    # 공백 0개월 + A → C 개념은 전부 0.9 (진단 후보 기준 0.8 이상 → 거의 안 물어봄)
    assert prior["variable"] == prior["loop"] == prior["pointer"] == 0.9
    # 자료구조는 아직 안 들었으므로 미이수
    assert prior["linked_list"] == 0.1


def test_gap_24_months(g):
    prior = prior_mastery(_profile("A0", gap=24), g)
    assert prior["variable"] == round(0.9 * math.exp(-24 / 36), 4)   # ≈ 0.46
    assert prior["pointer"] == round(0.9 * math.exp(-24 / 12), 4)    # ≈ 0.12
    # 2년이면 기초도 0.8 아래로 떨어져서 기초 개념부터 물어보게 된다
    assert all(v < 0.8 for v in prior.values())
    # 까다로운 개념이 기초보다 더 많이 잊혀진다
    assert prior["pointer"] < prior["loop"]


def test_grade_lowers_prior(g):
    a = prior_mastery(_profile("A0", gap=6), g)["variable"]
    b = prior_mastery(_profile("B+", gap=6), g)["variable"]
    c = prior_mastery(_profile("C-", gap=6), g)["variable"]
    assert a > b > c


def test_not_completed_is_flat(g):
    prior = prior_mastery({"completedCourses": [], "gapMonths": 0}, g)
    assert set(prior.values()) == {0.1}


@pytest.mark.parametrize("raw, expected", [
    ("A+", "A"), ("A0", "A"), ("A-", "A"),
    ("B+", "B"), ("B0", "B"), ("C-", "C"),
    ("D+", None), ("F", None), ("P", "B"),
])
def test_normalize_grade(raw, expected):
    assert normalize_grade(raw) == expected


def test_fail_counts_as_not_completed(g):
    assert prior_mastery(_profile("F"), g)["variable"] == 0.1


def test_pass_counts_as_b(g):
    assert prior_mastery(_profile("P"), g)["variable"] == 0.75


def test_retake_uses_best_grade(g):
    profile = {"completedCourses": [{"course": "C", "grade": "F"}, {"course": "C", "grade": "B0"}],
               "gapMonths": 0}
    assert prior_mastery(profile, g)["variable"] == 0.75


@pytest.mark.parametrize("bad", [
    {"completedCourses": [{"course": "C", "grade": "Z"}], "gapMonths": 0},     # 없는 성적
    {"completedCourses": [{"course": "C"}], "gapMonths": 0},                  # 성적 누락
    {"completedCourses": [{"course": "JAVA", "grade": "A0"}], "gapMonths": 0},  # 없는 과목
    {"completedCourses": [], "gapMonths": 121},                              # 공백 범위
    {"completedCourses": [], "gapMonths": 0, "dailyMinutes": 10},             # 하루 시간 범위
])
def test_invalid_profile_is_rejected(bad):
    with pytest.raises(ValidationError):
        Profile.model_validate(bad)


def test_snake_case_also_accepted():
    p = Profile.model_validate({"completed_courses": [{"course": "C", "grade": "A0"}], "gap_months": 3})
    assert p.gap_months == 3
