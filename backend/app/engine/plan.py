"""역산 플랜: 복학일까지 남은 시간에 맞춰 30분 블록을 날짜별로 배치한다.

규칙 (개발 가이드 5-4)
1. 배울 개념 고르기: mastery가 0.6 미만인 개념
2. 순서 정하기: 위상 정렬 (선수 개념이 먼저)
3. 시간 예산: (복학일까지 남은 일수) × (하루 가용 분 ÷ 30) = 쓸 수 있는 블록 수
4. 배치: 개념마다 필요한 블록 수(1~3개)를 순서대로 날짜에 채움
5. 넘치면: "이 개념에 의존하는 개념 수"가 적은 것부터 빼고, 미룬 개념으로 알려줌

블록 id는 blocks.json에 있으면 그 id를, 없으면 "b-{개념 id}-{번호}" 규칙으로 만든다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .graph import Graph

LEARN_THRESHOLD = 0.6   # 이 미만이면 배울 개념
BLOCK_MINUTES = 30


@dataclass
class PlanBlock:
    order: int            # 그날 안에서의 순서 (1부터)
    block_id: str
    concept_id: str
    concept_name: str
    minutes: int = BLOCK_MINUTES


@dataclass
class PlanDay:
    date: date
    blocks: list[PlanBlock] = field(default_factory=list)


@dataclass
class DeferredConcept:
    concept_id: str
    concept_name: str
    blocks: int           # 이 개념에 필요했던 블록 수


@dataclass
class Plan:
    return_date: date
    daily_minutes: int
    days: list[PlanDay]
    deferred: list[DeferredConcept]   # 시간이 부족해 복학 후로 미룬 개념
    total_blocks: int                 # 배치한 블록 수
    available_blocks: int             # 쓸 수 있었던 블록 수

    @property
    def message(self) -> str | None:
        if not self.deferred:
            return None
        names = ", ".join(d.concept_name for d in self.deferred)
        return f"시간이 부족해 {names}은(는) 복학 후로 미뤘어요"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["message"] = self.message
        return d


def block_ids_for(graph: Graph, concept_id: str) -> list[str]:
    """개념에 필요한 블록 id 목록 (concept.blocks 개수만큼)."""
    need = graph.concepts[concept_id].blocks
    real = [b.id for b in graph.blocks_by_concept.get(concept_id, [])]
    ids = real[:need]
    n = len(ids)
    while len(ids) < need:
        n += 1
        candidate = f"b-{concept_id}-{n}"
        if candidate not in ids:
            ids.append(candidate)
    return ids


def available_blocks(today: date, return_date: date, daily_minutes: int) -> int:
    days = max((return_date - today).days, 0)
    return days * (daily_minutes // BLOCK_MINUTES)


def build_plan(mastery: dict[str, float], graph: Graph, today: date,
               return_date: date, daily_minutes: int) -> Plan:
    """mastery(개념 id → 이해도)로 오늘부터 복학 전날까지의 플랜을 만든다."""
    learn = {c for c, m in mastery.items() if c in graph.concepts and m < LEARN_THRESHOLD}
    budget = available_blocks(today, return_date, daily_minutes)
    order = graph.topological_order()
    position = {c: i for i, c in enumerate(order)}

    def cost(concepts: set[str]) -> int:
        return sum(graph.concepts[c].blocks for c in concepts)

    # 넘치면 의존하는 개념 수가 적은 것부터 뺀다.
    # 남은 배울 개념 중에서 세므로, 빼는 개념은 항상 다른 배울 개념의 선수 개념이 아니다.
    deferred_ids: list[str] = []
    while learn and cost(learn) > budget:
        def dependents_in_learn(c: str) -> int:
            return len(graph.descendants(c) & learn)
        # 의존 개념 수가 같으면 더 뒤(목표 쪽, 어려운) 개념부터 미룬다
        victim = min(learn, key=lambda c: (dependents_in_learn(c), -position[c]))
        learn.remove(victim)
        deferred_ids.append(victim)

    slots_per_day = daily_minutes // BLOCK_MINUTES
    days: list[PlanDay] = []
    current: PlanDay | None = None
    for cid in graph.topological_order(learn):
        for bid in block_ids_for(graph, cid):
            if current is None or len(current.blocks) >= slots_per_day:
                current = PlanDay(date=today + timedelta(days=len(days)))
                days.append(current)
            current.blocks.append(PlanBlock(
                order=len(current.blocks) + 1,
                block_id=bid,
                concept_id=cid,
                concept_name=graph.concepts[cid].name,
            ))

    deferred = [DeferredConcept(c, graph.concepts[c].name, graph.concepts[c].blocks)
                for c in sorted(deferred_ids, key=position.get)]
    return Plan(
        return_date=return_date,
        daily_minutes=daily_minutes,
        days=days,
        deferred=deferred,
        total_blocks=sum(len(d.blocks) for d in days),
        available_blocks=budget,
    )


def today_remaining_minutes(plan: Plan, today: date, done_block_ids: set[str]) -> int:
    """오늘 날짜 블록 중 아직 안 끝낸 블록의 분 합계 (GET /plan의 todayRemainingMinutes)."""
    for day in plan.days:
        if day.date == today:
            return sum(b.minutes for b in day.blocks if b.block_id not in done_block_ids)
    return 0
