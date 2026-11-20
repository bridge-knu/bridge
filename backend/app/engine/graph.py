"""개념 그래프.

개념 하나가 노드, "A를 알아야 B를 이해한다"가 간선(A → B)이다.
concepts.json의 prereqs가 간선 정보이고, 그래프는 사이클이 없어야(DAG) 한다.

load_graph()  : content 폴더를 읽어 검증된 Graph를 만든다.
Graph         : 선수 개념 / 후속 개념 / 위상 정렬 / 깊이 등 조회 함수 모음.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .models import Block, Concept, ContentSet, Question, load_content


class GraphError(ValueError):
    """콘텐츠를 그래프로 만들 수 없을 때. errors에 사람이 읽을 메시지 목록이 들어 있다."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("개념 그래프 오류:\n- " + "\n- ".join(errors))


@dataclass
class Graph:
    concepts: dict[str, Concept]
    questions: dict[str, Question]
    blocks: dict[str, Block]
    # 개념 id → 그 개념의 문제 / 블록 (파일에 적힌 순서)
    questions_by_concept: dict[str, list[Question]] = field(default_factory=dict)
    blocks_by_concept: dict[str, list[Block]] = field(default_factory=dict)
    # 개념 id → 바로 다음에 오는 개념들 (prereqs의 역방향)
    _dependents: dict[str, list[str]] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    # ---- 기본 조회 -------------------------------------------------

    def prereqs(self, concept_id: str) -> list[str]:
        """직접 선수 개념."""
        return list(self.concepts[concept_id].prereqs)

    def dependents(self, concept_id: str) -> list[str]:
        """이 개념을 직접 선수 개념으로 가진 개념들."""
        return list(self._dependents.get(concept_id, []))

    def ancestors(self, concept_id: str) -> set[str]:
        """이 개념을 이해하는 데 필요한 모든 선수 개념 (간접 포함, 자기 자신 제외)."""
        return self._walk(concept_id, self.prereqs)

    def descendants(self, concept_id: str) -> set[str]:
        """이 개념에 기대는 모든 후속 개념 (간접 포함, 자기 자신 제외)."""
        return self._walk(concept_id, self.dependents)

    def dependent_count(self, concept_id: str) -> int:
        """이 개념에 의존하는 개념 수. 플랜이 넘칠 때 무엇을 먼저 뺄지 정하는 데 쓴다."""
        return len(self.descendants(concept_id))

    def topological_order(self, concept_ids: set[str] | None = None) -> list[str]:
        """선수 개념이 항상 먼저 오는 순서. concept_ids를 주면 그 개념들만 같은 규칙으로 정렬."""
        if concept_ids is None:
            return list(self._order)
        return [c for c in self._order if c in concept_ids]

    def depth(self, concept_id: str) -> int:
        """선수 개념이 없는 기초 개념이 0, 선수 개념 사슬이 길수록 커진다."""
        memo: dict[str, int] = {}

        def d(cid: str) -> int:
            if cid not in memo:
                ps = self.concepts[cid].prereqs
                memo[cid] = 0 if not ps else 1 + max(d(p) for p in ps)
            return memo[cid]

        return d(concept_id)

    def concepts_of_course(self, course: str) -> list[str]:
        return [c for c in self._order if self.concepts[c].course == course]

    def required_for_course(self, course: str) -> set[str]:
        """목표 과목을 듣는 데 필요한 개념: 그 과목의 개념 + 모든 선수 개념."""
        result: set[str] = set()
        for cid in self.concepts_of_course(course):
            result.add(cid)
            result |= self.ancestors(cid)
        return result

    # ---- 내부 -------------------------------------------------------

    @staticmethod
    def _walk(start: str, step) -> set[str]:
        seen: set[str] = set()
        stack = list(step(start))
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(step(cur))
        return seen


def _find_cycle(concepts: dict[str, Concept]) -> list[str] | None:
    """사이클이 있으면 ['a', 'b', 'c', 'a'] 같은 경로를, 없으면 None을 돌려준다."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {cid: WHITE for cid in concepts}
    path: list[str] = []

    def visit(cid: str) -> list[str] | None:
        color[cid] = GRAY
        path.append(cid)
        for p in concepts[cid].prereqs:
            if p not in concepts:
                continue  # 없는 개념 참조는 따로 보고
            if color[p] == GRAY:
                return path[path.index(p):] + [p]
            if color[p] == WHITE:
                found = visit(p)
                if found:
                    return found
        path.pop()
        color[cid] = BLACK
        return None

    for cid in concepts:
        if color[cid] == WHITE:
            found = visit(cid)
            if found:
                return found
    return None


def _topological_sort(concepts: dict[str, Concept]) -> list[str]:
    """Kahn 알고리즘. 같은 단계에서는 concepts.json에 적힌 순서를 유지한다."""
    position = {cid: i for i, cid in enumerate(concepts)}
    indegree = {cid: len(c.prereqs) for cid, c in concepts.items()}
    dependents: dict[str, list[str]] = {cid: [] for cid in concepts}
    for cid, c in concepts.items():
        for p in c.prereqs:
            dependents[p].append(cid)

    ready = deque(sorted((c for c in concepts if indegree[c] == 0), key=position.get))
    order: list[str] = []
    while ready:
        cur = ready.popleft()
        order.append(cur)
        released = []
        for nxt in dependents[cur]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                released.append(nxt)
        # 새로 준비된 개념도 파일 순서대로 넣는다
        for nxt in sorted(released, key=position.get):
            ready.append(nxt)
    return order


def build_graph(content: ContentSet, require_questions: bool = True) -> Graph:
    concepts = {c.id: c for c in content.concepts}
    errors: list[str] = []

    for c in content.concepts:
        for p in c.prereqs:
            if p not in concepts:
                errors.append(f"개념 '{c.id}'의 선수 개념 '{p}'가 없음")

    cycle = _find_cycle(concepts)
    if cycle:
        # prereqs 방향(B → A: B를 알려면 A가 필요)을 학습 순서(A → B)로 뒤집어 보여준다
        errors.append("선수 관계에 사이클이 있음: " + " → ".join(reversed(cycle)))

    questions_by_concept: dict[str, list[Question]] = {cid: [] for cid in concepts}
    for q in content.questions:
        questions_by_concept.setdefault(q.concept, []).append(q)
    blocks_by_concept: dict[str, list[Block]] = {cid: [] for cid in concepts}
    for b in content.blocks:
        blocks_by_concept.setdefault(b.concept, []).append(b)

    if require_questions:
        for cid in concepts:
            if not questions_by_concept[cid]:
                errors.append(f"개념 '{cid}'에 진단 문제가 없음")

    if errors:
        raise GraphError(errors)

    order = _topological_sort(concepts)
    dependents: dict[str, list[str]] = {cid: [] for cid in concepts}
    for cid in order:
        for p in concepts[cid].prereqs:
            dependents[p].append(cid)

    return Graph(
        concepts=concepts,
        questions={q.id: q for q in content.questions},
        blocks={b.id: b for b in content.blocks},
        questions_by_concept=questions_by_concept,
        blocks_by_concept=blocks_by_concept,
        _dependents=dependents,
        _order=order,
    )


def load_graph(path: str | Path, require_questions: bool = True) -> Graph:
    """content 폴더를 읽어 Graph를 만든다.

    사이클, 없는 개념 참조, 문제가 없는 개념이 있으면 GraphError를 낸다.
    require_questions=False는 문제를 쓰기 전 개념 지도만 검사할 때 쓴다.
    """
    try:
        content = load_content(path)
    except ValidationError as e:
        raise GraphError([err["msg"] for err in e.errors()]) from e
    return build_graph(content, require_questions=require_questions)
