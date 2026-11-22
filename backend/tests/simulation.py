"""가상 프로필 270개로 엔진(망각 추정 → 진단 → 역산 플랜)을 돌려 보는 시뮬레이션.

실행: backend 폴더에서 `python -m tests.simulation`

- 프로필: 공백 개월(0,6,12,18,24,36) × C 성적(A,B,C,F,미이수) × 하루 시간(30,60,120분)
  × 복학까지 남은 기간(1,3,6개월) = 270개. 목표 과목은 자료구조.
- 진단 응답: 각 개념을 망각 추정값(prior) 확률로 맞힌다고 가정한다. 시드 고정이라 결과가 매번 같다.
- 엔진 코드(app/engine)는 호출만 하고 수정하지 않는다.
- 실제 사용자 데이터가 아니라 가상 프로필이다. 발표·README에 그렇게 적는다.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import product
from pathlib import Path

from app.engine import diagnosis as diag
from app.engine.forgetting import prior_mastery
from app.engine.graph import Graph, load_graph
from app.engine.plan import Plan, build_plan

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content"

GAPS = [0, 6, 12, 18, 24, 36]
GRADES = ["A", "B", "C", "F", "미이수"]
DAILY = [30, 60, 120]
MONTHS_LEFT = [1, 3, 6]
SEED = 20261123
TODAY = date(2026, 11, 23)

# 등급 대표값 (A → A0처럼 API가 받는 14개 값 중 하나로)
GRADE_VALUE = {"A": "A0", "B": "B0", "C": "C0", "F": "F"}


@dataclass
class Result:
    gap: int
    grade: str
    daily: int
    months_left: int
    asked: list[str]           # 출제된 개념 순서
    plan: Plan
    order_violations: int      # 선수 개념보다 먼저 배치된 경우
    deferred_prereq_violations: int  # 선수 개념은 미뤘는데 그 위 개념은 배치된 경우


def make_profile(gap: int, grade: str, daily: int, months_left: int) -> dict:
    courses = [] if grade == "미이수" else [{"course": "C", "grade": GRADE_VALUE[grade]}]
    return {
        "completedCourses": courses,
        "gapMonths": gap,
        "targetCourse": "DS",
        "returnDate": (TODAY + timedelta(days=30 * months_left)).isoformat(),
        "dailyMinutes": daily,
    }


def run_diagnosis(profile: dict, graph: Graph, rng: random.Random):
    """prior 확률로 맞히는 가상 학생. (끝난 진단 상태, 출제 개념 순서)"""
    prior = prior_mastery(profile, graph)
    state = diag.start_diagnosis(profile, graph)
    asked = []
    while True:
        q = diag.next_question(state, graph)
        if q is None:
            break
        asked.append(q.concept)
        correct = rng.random() < prior[q.concept]
        diag.apply_answer(state, q.id, correct, graph)
    return state, asked


def check_plan(plan: Plan, graph: Graph) -> tuple[int, int]:
    """(순서 위반 수, 미룬 선수 개념 위에 배치된 개념 수)"""
    position: dict[str, int] = {}
    i = 0
    for day in plan.days:
        for b in day.blocks:
            position.setdefault(b.concept_id, i)
            i += 1
    deferred = {d.concept_id for d in plan.deferred}

    order = 0
    on_deferred = 0
    for cid, pos in position.items():
        for p in graph.prereqs(cid):
            if p in position and position[p] > pos:
                order += 1
            if p in deferred:
                on_deferred += 1
    return order, on_deferred


def run_simulation(graph: Graph | None = None) -> list[Result]:
    graph = graph or load_graph(CONTENT_DIR)
    rng = random.Random(SEED)
    results = []
    for gap, grade, daily, months in product(GAPS, GRADES, DAILY, MONTHS_LEFT):
        profile = make_profile(gap, grade, daily, months)
        state, asked = run_diagnosis(profile, graph, rng)
        return_date = TODAY + timedelta(days=30 * months)
        plan = build_plan(state.mastery, graph, TODAY, return_date, daily)
        order, on_deferred = check_plan(plan, graph)
        results.append(Result(gap, grade, daily, months, asked, plan, order, on_deferred))
    return results


def summarize(results: list[Result], graph: Graph) -> str:
    name = {cid: c.name for cid, c in graph.concepts.items()}
    n = len(results)
    lines = [f"가상 프로필 {n}개 시뮬레이션 (시드 {SEED}, 목표 과목 자료구조)", ""]

    counts = [len(r.asked) for r in results]
    diagnosable = len(diag.diagnosable_concepts(graph, "DS"))
    required = len(graph.required_for_course("DS"))
    lines += [
        "## 1. 진단 문항 수",
        f"- 평균 {sum(counts) / n:.1f}문항 (최소 {min(counts)}, 최대 {max(counts)}) "
        f"/ 진단 대상 C 개념 {diagnosable}개, 목표까지 필요한 개념 {required}개",
        f"- 0문항으로 끝난 프로필 {counts.count(0)}개 (이미 다 아는 것으로 추정)",
        "",
        "| 공백 \\ 성적 | " + " | ".join(GRADES) + " |",
        "|---" * (len(GRADES) + 1) + "|",
    ]
    for gap in GAPS:
        row = []
        for g in GRADES:
            c = [len(r.asked) for r in results if r.gap == gap and r.grade == g]
            row.append(f"{sum(c) / len(c):.1f}")
        lines.append(f"| {gap}개월 | " + " | ".join(row) + " |")

    lines += ["", "## 2. 공백 기간별 첫 출제 개념 (가장 많이 나온 것)", "",
              "| 공백 | 첫 출제 개념 | 비율 |", "|---|---|---|"]
    for gap in GAPS:
        firsts = Counter(r.asked[0] for r in results if r.gap == gap and r.asked)
        total = sum(1 for r in results if r.gap == gap)
        if firsts:
            cid, k = firsts.most_common(1)[0]
            lines.append(f"| {gap}개월 | {name[cid]} | {k}/{total} |")
        else:
            lines.append(f"| {gap}개월 | (출제 없음) | 0/{total} |")

    lines += ["", "## 2-1. 공백 기간별 진단 결과", "",
              "| 공백 | 다시 봐야 할 C 개념 (10개 중) | 전체 학습 블록 (자료구조 포함) |", "|---|---|---|"]
    for gap in GAPS:
        rs = [r for r in results if r.gap == gap]
        concepts = [sum(1 for c in {b.concept_id for d in r.plan.days for b in d.blocks} | {d.concept_id for d in r.plan.deferred}
                        if graph.concepts[c].course == "C") for r in rs]
        blocks = [r.plan.total_blocks for r in rs]
        lines.append(f"| {gap}개월 | {sum(concepts) / len(rs):.1f}개 | {sum(blocks) / len(rs):.1f}개 |")

    def deferred_rate(rs):
        d = sum(1 for r in rs if r.plan.deferred)
        return f"{d}/{len(rs)} ({100 * d / len(rs):.0f}%)"

    lines += ["", "## 3. 미룬 개념이 생긴 비율",
              f"- 전체 {deferred_rate(results)}", "",
              "| 하루 \\ 복학까지 | " + " | ".join(f"{m}개월" for m in MONTHS_LEFT) + " |",
              "|---" * (len(MONTHS_LEFT) + 1) + "|"]
    for daily in DAILY:
        row = [deferred_rate([r for r in results if r.daily == daily and r.months_left == m])
               for m in MONTHS_LEFT]
        lines.append(f"| {daily}분 | " + " | ".join(row) + " |")

    by_concept = Counter(d.concept_id for r in results for d in r.plan.deferred)
    if by_concept:
        top = ", ".join(f"{name[c]} {k}회" for c, k in by_concept.most_common(5))
        lines.append(f"- 가장 많이 미뤄진 개념: {top}")

    max_blocks = max(r.plan.total_blocks + sum(d.blocks for d in r.plan.deferred) for r in results)
    lines.append(f"- 참고: 가장 많이 필요한 프로필도 블록 {max_blocks}개라, 하루 30분 × 1개월(30블록) 안에 다 들어감")

    order = sum(r.order_violations for r in results)
    on_def = sum(r.deferred_prereq_violations for r in results)
    lines += ["", "## 4. 선수 개념 순서 검사",
              f"- 선수 개념보다 먼저 배치된 경우: {order}건",
              f"- 미룬 선수 개념 위에 배치된 개념: {on_def}건"]
    return "\n".join(lines)


def short_period_check(graph: Graph) -> str:
    """추가 확인: 복학이 1·2주 남은 경우 (270개와 별도). 미루기 규칙이 실제로 동작하는지 본다."""
    rng = random.Random(SEED)
    lines = ["", "## 추가 확인: 복학까지 1·2주 남은 경우 (공백·성적 30개 조합 × 하루 30/60/120분, 270개와 별도)", "",
             "| 하루 \\ 복학까지 | 1주 | 2주 |", "|---|---|---|"]
    order = on_def = 0
    for daily in DAILY:
        row = []
        for days in (7, 14):
            rs = []
            for gap, grade in product(GAPS, GRADES):
                profile = make_profile(gap, grade, daily, 1)
                state, _ = run_diagnosis(profile, graph, rng)
                plan = build_plan(state.mastery, graph, TODAY, TODAY + timedelta(days=days), daily)
                o, d = check_plan(plan, graph)
                order += o
                on_def += d
                rs.append(plan)
            k = sum(1 for p in rs if p.deferred)
            row.append(f"{k}/{len(rs)} ({100 * k / len(rs):.0f}%)")
        lines.append(f"| {daily}분 | " + " | ".join(row) + " |")
    lines.append(f"- 이 경우에도 순서 위반 {order}건, 미룬 선수 개념 위 배치 {on_def}건")
    return "\n".join(lines)


if __name__ == "__main__":
    g = load_graph(CONTENT_DIR)
    print(summarize(run_simulation(g), g))
    print(short_period_check(g))
