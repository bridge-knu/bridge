from datetime import date, timedelta

import pytest

from app.engine.graph import build_graph
from app.engine.models import ContentSet
from app.engine.plan import available_blocks, block_ids_for, build_plan, today_remaining_minutes

TODAY = date(2026, 11, 20)

# (id, course, prereqs, blocks)
CONCEPTS = [
    ("variable", "C", [], 1),
    ("loop", "C", ["variable"], 1),
    ("array", "C", ["loop"], 1),
    ("function", "C", ["loop"], 1),
    ("pointer", "C", ["array", "function"], 2),
    ("struct", "C", ["variable"], 1),
    ("dynamic_alloc", "C", ["pointer"], 1),
    ("stack", "DS", ["array", "struct"], 1),
    ("linked_list", "DS", ["struct", "dynamic_alloc"], 2),
    ("binary_tree", "DS", ["linked_list"], 2),
]


@pytest.fixture
def g():
    cs = [{"id": i, "name": i, "course": c, "prereqs": p, "stability": 12, "blocks": b}
          for i, c, p, b in CONCEPTS]
    qs = [{"id": f"q-{i}-1", "concept": i, "prompt": "?", "choices": ["o", "x"], "answer": 0}
          for i, *_ in CONCEPTS]
    blocks = [{"id": "b-pointer-1", "concept": "pointer",
               "video": "https://www.youtube.com/watch?v=abc", "videoStart": 0, "videoEnd": 60,
               "practice": {"lang": "c", "starter": "", "expected": ""}}]
    return build_graph(ContentSet(concepts=cs, questions=qs, blocks=blocks))


def _all_low(g, value=0.1):
    return {c: value for c in g.concepts}


def _flat(plan):
    return [b for d in plan.days for b in d.blocks]


# ---- 개발 가이드 5-5 테스트 케이스 ----

def test_prereqs_always_come_first(g):
    plan = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=30), 60)
    seen: list[str] = []
    for b in _flat(plan):
        for p in g.prereqs(b.concept_id):
            if p in {x.concept_id for x in _flat(plan)}:
                assert p in seen, f"{b.concept_id}보다 {p}가 먼저 나와야 함"
        seen.append(b.concept_id)


def test_too_many_blocks_returns_deferred(g):
    # 블록 13개 필요, 2일 × 하루 60분(2블록) = 4블록만 가능
    plan = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=2), 60)
    assert plan.available_blocks == 4
    assert plan.total_blocks <= 4
    assert plan.deferred
    assert plan.message.startswith("시간이 부족해")


# ---- 규칙 ----

def test_only_low_mastery_concepts_are_planned(g):
    mastery = _all_low(g, 0.9)
    mastery["linked_list"] = 0.2
    plan = build_plan(mastery, g, TODAY, TODAY + timedelta(days=30), 60)
    assert {b.concept_id for b in _flat(plan)} == {"linked_list"}
    assert len(_flat(plan)) == 2        # linked_list는 블록 2개


def test_threshold_is_0_6(g):
    mastery = _all_low(g, 0.9)
    mastery["stack"] = 0.6
    mastery["array"] = 0.59
    plan = build_plan(mastery, g, TODAY, TODAY + timedelta(days=30), 60)
    assert {b.concept_id for b in _flat(plan)} == {"array"}


def test_daily_slots_and_dates(g):
    plan = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=30), 90)  # 하루 3블록
    assert all(len(d.blocks) <= 3 for d in plan.days)
    assert [d.date for d in plan.days] == [TODAY + timedelta(days=i) for i in range(len(plan.days))]
    assert [b.order for b in plan.days[0].blocks] == [1, 2, 3]
    assert plan.total_blocks == 13 and not plan.deferred


def test_deferred_never_leaves_kept_concept_without_prereq(g):
    for days in range(0, 8):
        plan = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=days), 60)
        kept = {b.concept_id for b in _flat(plan)}
        deferred = {d.concept_id for d in plan.deferred}
        for c in kept:
            assert not (g.ancestors(c) & deferred), f"{c}의 선수 개념이 미뤄짐"


def test_deferred_starts_from_most_advanced(g):
    plan = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=5), 60)  # 10블록
    # 13블록 필요 → 의존 개념이 없는 것 중 뒤쪽부터: binary_tree(2) → linked_list(2)
    assert [d.concept_id for d in plan.deferred] == ["linked_list", "binary_tree"]
    assert plan.total_blocks == 9


def test_no_time_defers_everything(g):
    plan = build_plan(_all_low(g), g, TODAY, TODAY, 60)
    assert plan.days == []
    assert len(plan.deferred) == len(g.concepts)


def test_available_blocks():
    assert available_blocks(TODAY, TODAY + timedelta(days=10), 120) == 40
    assert available_blocks(TODAY, TODAY - timedelta(days=1), 120) == 0
    assert available_blocks(TODAY, TODAY + timedelta(days=10), 45) == 10   # 45분 → 1블록


def test_block_ids_use_real_blocks_first(g):
    assert block_ids_for(g, "pointer") == ["b-pointer-1", "b-pointer-2"]
    assert block_ids_for(g, "linked_list") == ["b-linked_list-1", "b-linked_list-2"]


def test_today_remaining_minutes(g):
    plan = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=30), 60)
    first = plan.days[0].blocks
    assert today_remaining_minutes(plan, TODAY, set()) == 60
    assert today_remaining_minutes(plan, TODAY, {first[0].block_id}) == 30
    assert today_remaining_minutes(plan, TODAY + timedelta(days=100), set()) == 0


def test_to_dict(g):
    d = build_plan(_all_low(g), g, TODAY, TODAY + timedelta(days=2), 60).to_dict()
    assert set(d) >= {"return_date", "daily_minutes", "days", "deferred", "message"}
    assert d["days"][0]["blocks"][0]["minutes"] == 30
