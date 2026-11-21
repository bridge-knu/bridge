from pathlib import Path

import pytest

from app.engine.graph import GraphError, build_graph, load_graph
from app.engine.models import ContentSet

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"


def _concept(cid, prereqs=(), course="C", stability=12):
    return {"id": cid, "name": cid, "course": course, "prereqs": list(prereqs),
            "stability": stability, "blocks": 1}


def _question(cid, n=1):
    return {"id": f"q-{cid}-{n}", "concept": cid, "prompt": "?", "choices": ["a", "b"], "answer": 0}


def _content(concepts, questions=None):
    if questions is None:
        questions = [_question(c["id"]) for c in concepts]
    return ContentSet(concepts=concepts, questions=questions, blocks=[])


# 학습 순서: variable → array → pointer → linked_list, pointer는 function도 필요
#           linked_list → stack(DS)
@pytest.fixture
def g():
    return build_graph(_content([
        _concept("variable", stability=36),
        _concept("array", ["variable"]),
        _concept("function", ["variable"]),
        _concept("pointer", ["array", "function"]),
        _concept("linked_list", ["pointer"], course="DS"),
        _concept("stack", ["array"], course="DS"),
    ]))


def test_sample_content_loads():
    graph = load_graph(CONTENT_DIR)
    assert graph.topological_order() == ["array", "pointer", "linked_list"]


def test_topological_order_puts_prereqs_first(g):
    order = g.topological_order()
    for cid in order:
        for p in g.prereqs(cid):
            assert order.index(p) < order.index(cid)
    assert order[0] == "variable"


def test_topological_order_subset(g):
    assert g.topological_order({"linked_list", "array"}) == ["array", "linked_list"]


def test_ancestors_and_descendants(g):
    assert g.ancestors("linked_list") == {"pointer", "array", "function", "variable"}
    assert g.ancestors("variable") == set()
    assert g.descendants("array") == {"pointer", "linked_list", "stack"}
    assert g.dependent_count("variable") == 5
    assert g.dependent_count("linked_list") == 0


def test_depth(g):
    assert g.depth("variable") == 0
    assert g.depth("pointer") == 2
    assert g.depth("linked_list") == 3


def test_required_for_course(g):
    assert g.required_for_course("DS") == {
        "linked_list", "stack", "pointer", "array", "function", "variable"}
    # 위상 정렬 순서: stack은 array만 있으면 되므로 linked_list보다 먼저
    assert g.concepts_of_course("DS") == ["stack", "linked_list"]


def test_cycle_is_error():
    with pytest.raises(GraphError, match="사이클"):
        build_graph(_content([
            _concept("a", ["c"]),
            _concept("b", ["a"]),
            _concept("c", ["b"]),
        ]))


def test_missing_prereq_is_error(tmp_path):
    (tmp_path / "concepts.json").write_text(
        '[{"id":"a","name":"a","course":"C","prereqs":["ghost"],"stability":12,"blocks":1}]',
        encoding="utf-8")
    (tmp_path / "questions.json").write_text(
        '[{"id":"q-a-1","concept":"a","prompt":"?","choices":["x","y"],"answer":0}]',
        encoding="utf-8")
    (tmp_path / "blocks.json").write_text("[]", encoding="utf-8")
    with pytest.raises(GraphError, match="ghost"):
        load_graph(tmp_path)


def test_concept_without_question_is_error():
    content = _content([_concept("a"), _concept("b", ["a"])], questions=[_question("a")])
    with pytest.raises(GraphError, match="'b'에 진단 문제가 없음"):
        build_graph(content)
    # 개념 지도만 먼저 검사할 때는 통과
    assert build_graph(content, require_questions=False).topological_order() == ["a", "b"]


def test_questions_grouped_by_concept(g):
    assert [q.id for q in g.questions_by_concept["pointer"]] == ["q-pointer-1"]
