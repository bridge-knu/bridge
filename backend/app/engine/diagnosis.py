"""적응형 진단.

목표 과목에 필요한 선수 개념에서 출발해, 틀리면 더 기초로 내려가고
맞으면 그 아래는 안다고 보고 건너뛴다. 문제는 최대 10개.

규칙 (개발 가이드 5-3)
1. 목표 과목의 선수 개념 중 prior가 0.8 미만인 것만 후보 (0.8 이상은 안다고 가정)
2. 후보 중 그래프에서 가장 위(목표에 가까운) 개념부터 출제
3. 맞음 → mastery 0.9, 그 개념의 선수 개념도 안다고 보고 후보에서 제거
4. 틀림 → mastery 0.2, 그 개념의 직접 선수 개념을 다음 출제 대상으로
5. 후보가 없거나 10문제가 되면 종료. 출제 안 된 개념은 prior 값 유지

목표 과목 자체의 개념(예: 자료구조의 스택)은 앞으로 배울 내용이라 진단하지 않고 prior 그대로 둔다.

API 계층에서의 사용 순서
    state = start_diagnosis(profile, graph)
    q = next_question(state, graph)          # None이면 바로 결과
    state = apply_answer(state, q.id, correct, graph)
    q = next_question(state, graph) ...
    result_concepts(state, graph)            # GET /diagnosis/result
정답 판정(correct = choice == question.answer)은 API 계층에서 한다.
state는 to_dict()/from_dict()로 DB나 메모리에 저장할 수 있다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .forgetting import Profile, prior_mastery
from .graph import Graph
from .models import Question

MAX_QUESTIONS = 10
KNOWN_THRESHOLD = 0.8     # prior가 이 이상이면 안다고 보고 묻지 않는다
CORRECT_MASTERY = 0.9
WRONG_MASTERY = 0.2
INFERRED_MASTERY = 0.8    # 상위 개념을 맞혀서 안다고 본 선수 개념의 최소 이해도


@dataclass
class DiagnosisState:
    target_course: str
    mastery: dict[str, float]               # 개념 id → 현재 이해도
    source: dict[str, str]                  # 개념 id → "prior" | "diagnosed"
    candidates: list[str]                   # 아직 물어볼 수 있는 개념
    priority: list[str] = field(default_factory=list)  # 틀린 개념의 직접 선수 개념 (먼저 출제)
    asked_questions: list[str] = field(default_factory=list)
    current_question_id: str | None = None
    answered_count: int = 0
    max_questions: int = MAX_QUESTIONS

    @property
    def done(self) -> bool:
        return self.current_question_id is None and (
            self.answered_count >= self.max_questions or not self.candidates
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DiagnosisState:
        return cls(**data)


def diagnosable_concepts(graph: Graph, target_course: str) -> set[str]:
    """진단 대상: 목표 과목을 듣는 데 필요한 개념 중 목표 과목 바깥의 선수 개념.

    목표 과목에 바깥 선수 개념이 없으면(예: 목표가 C) 목표 과목 개념 자체를 진단한다.
    처음 배우거나 재수강하는 학생이 어디까지 아는지 확인하기 위해서다.
    """
    required = graph.required_for_course(target_course)
    outside = {c for c in required if graph.concepts[c].course != target_course}
    return outside or required


def start_diagnosis(profile: Profile | dict, graph: Graph,
                    max_questions: int = MAX_QUESTIONS) -> DiagnosisState:
    if not isinstance(profile, Profile):
        profile = Profile.model_validate(profile)
    prior = prior_mastery(profile, graph)
    target = profile.target_course
    required = graph.required_for_course(target)

    candidates = [c for c in graph.topological_order(diagnosable_concepts(graph, target))
                  if prior[c] < KNOWN_THRESHOLD]
    return DiagnosisState(
        target_course=target,
        mastery={c: prior[c] for c in graph.topological_order(required)},
        source={c: "prior" for c in graph.topological_order(required)},
        candidates=candidates,
        max_questions=max_questions,
    )


def _pick_concept(state: DiagnosisState, graph: Graph) -> str | None:
    # 틀린 개념의 직접 선수 개념이 있으면 그것부터 (깊은 것 = 목표에 가까운 것 먼저)
    while state.priority:
        cid = state.priority.pop(0)
        if cid in state.candidates:
            return cid
    if not state.candidates:
        return None
    # 그래프에서 가장 위(깊이가 큰 = 목표에 가까운) 개념. 같으면 위상 정렬에서 뒤쪽
    order = {c: i for i, c in enumerate(graph.topological_order())}
    return max(state.candidates, key=lambda c: (graph.depth(c), order[c]))


def next_question(state: DiagnosisState, graph: Graph) -> Question | None:
    """다음 문제. 끝났으면 None. 이미 출제 중인 문제가 있으면 그 문제를 그대로 돌려준다."""
    if state.current_question_id is not None:
        return graph.questions[state.current_question_id]
    while state.answered_count < state.max_questions:
        cid = _pick_concept(state, graph)
        if cid is None:
            return None
        unasked = [q for q in graph.questions_by_concept.get(cid, [])
                   if q.id not in state.asked_questions]
        if not unasked:
            # 이 개념에 낼 문제가 없으면 후보에서 빼고 다음 개념으로
            state.candidates.remove(cid)
            continue
        question = unasked[0]
        state.current_question_id = question.id
        state.asked_questions.append(question.id)
        return question
    return None


def apply_answer(state: DiagnosisState, question_id: str, correct: bool,
                 graph: Graph) -> DiagnosisState:
    """답을 반영한다. question_id가 지금 문제가 아니면 ValueError."""
    if state.current_question_id is None:
        raise ValueError("진행 중인 문제가 없어요")
    if question_id != state.current_question_id:
        raise ValueError("지금 풀고 있는 문제가 아니에요")

    cid = graph.questions[question_id].concept
    state.current_question_id = None
    state.answered_count += 1
    if cid in state.candidates:
        state.candidates.remove(cid)
    state.source[cid] = "diagnosed"

    if correct:
        state.mastery[cid] = CORRECT_MASTERY
        # 선수 개념은 안다고 보고 더 묻지 않는다
        for a in graph.ancestors(cid):
            if a in state.candidates:
                state.candidates.remove(a)
                state.mastery[a] = max(state.mastery[a], INFERRED_MASTERY)
                state.source[a] = "diagnosed"
    else:
        state.mastery[cid] = WRONG_MASTERY
        # 직접 선수 개념을 다음 출제 대상으로 (목표에 가까운 것 먼저)
        prereqs = [p for p in graph.prereqs(cid) if p in state.candidates]
        prereqs.sort(key=lambda p: graph.depth(p), reverse=True)
        state.priority = prereqs + [p for p in state.priority if p not in prereqs]
    return state


def result_concepts(state: DiagnosisState, graph: Graph) -> list[dict]:
    """GET /diagnosis/result의 concepts 모양 (위상 정렬 순서, 선수 개념이 먼저)."""
    out = []
    for cid in graph.topological_order(set(state.mastery)):
        c = graph.concepts[cid]
        out.append({
            "id": cid,
            "name": c.name,
            "course": c.course,
            "prereqs": list(c.prereqs),
            "mastery": round(state.mastery[cid], 4),
            "source": state.source[cid],
        })
    return out
