"""Outcome di scheduling: mapping blocked_by -> tre stati + casi §14."""

from datetime import date, datetime

from carpediem.planner import outcomes as o
from carpediem.planner.decisions import decide
from carpediem.planner.diagnostics import diagnose
from carpediem.planner.models import (
    DETAIL_KEYS,
    DayPlan,
    PlanItem,
    PlanningRequest,
    PlanningResult,
    TimeWindow,
)
from carpediem.planner.outcomes import OUT_ELIGIBLE, OUT_OUTSIDE, OUT_SCHEDULED
from carpediem.planner.scheduler import schedule

DAY = date(2026, 10, 8)
TODAY_S = "2026-10-08"


def at(h, m=0):
    return datetime(2026, 10, 8, h, m)


def win(sh, eh, sm=0, em=0):
    return TimeWindow(at(sh, sm), at(eh, em))


def item(tid, pomo=1, score=10):
    return PlanItem(tid, score, (), pomo, False)


def make_plan(*items):
    return DayPlan(
        day=DAY,
        planned=tuple(items),
        capacity_pomo=12.0,
        planned_pomo=sum(i.estimate_pomo for i in items),
    )


def result_of(plan, avail, busy=(), deadlines=None, tasks=()):
    sched = schedule(plan, avail, busy, deadlines)
    req = PlanningRequest(day=DAY, tasks=tuple(tasks), capacity_pomo=12.0)
    alts, diags = diagnose(PlanningResult(request=req, plan=plan, scheduled=sched))
    return sched, {a.todo_id: a for a in alts}, diags


def outcome_of_sched(sched, alts, tid):
    scheduled = any(s.item.todo_id == tid for s in sched.scheduled)
    alt = alts.get(tid)
    return o.outcome_of(scheduled=scheduled, blocked_by=alt.blocked_by if alt else None)


def test_1_schedulable_e_scheduled():
    plan = make_plan(item(1))
    sched, alts, _ = result_of(plan, [win(9, 12)])
    assert [s.item.todo_id for s in sched.scheduled] == [1]
    assert outcome_of_sched(sched, alts, 1) == OUT_SCHEDULED
    assert alts == {}


def test_2_atomico_lungo_vs_max_gap_outside():
    plan = make_plan(item(1, pomo=3))  # 90m
    avail = [win(9, 12)]
    busy = [win(9, 10, 30, 0), win(10, 11, 30, 30)]  # 3 buchi da 30m
    sched, alts, _ = result_of(plan, avail, busy)
    assert sched.scheduled == ()
    assert outcome_of_sched(sched, alts, 1) == OUT_OUTSIDE
    assert alts[1].detail["max_gap_min"] == 30


def test_3_gara_persa_eligible():
    plan = make_plan(item(1, score=50), item(2, score=10))
    sched, alts, _ = result_of(plan, [win(9, 9, 0, 30)])
    assert [s.item.todo_id for s in sched.scheduled] == [1]
    assert outcome_of_sched(sched, alts, 1) == OUT_SCHEDULED
    assert alts[2].blocked_by == "tasks"
    assert outcome_of_sched(sched, alts, 2) == OUT_ELIGIBLE


def test_4_disponibilita_trascorsa_outside():
    from carpediem.planner.time_model import clip_future

    plan = make_plan(item(1))
    future = clip_future([win(9, 10)], at(12))
    assert future == []
    sched, alts, diags = result_of(plan, future)
    assert sched.scheduled == ()
    assert outcome_of_sched(sched, alts, 1) == OUT_OUTSIDE
    assert alts[1].blocked_by == "window"
    assert alts[1].detail["max_gap_min"] == 0
    assert any(d.kind == "empty_availability" for d in diags)


def test_5_somma_buchi_non_basta_outside():
    plan = make_plan(item(1, pomo=2))  # 60m
    avail = [win(9, 10)]
    busy = [win(9, 10, 40, 0)]  # buco solo 09:00-09:40 = 40m < 60m
    sched, alts, _ = result_of(plan, avail, busy)
    assert sched.scheduled == ()
    assert outcome_of_sched(sched, alts, 1) == OUT_OUTSIDE
    assert alts[1].detail["max_gap_min"] == 40


def test_6_7_max_gap_e_gap_count_esatti():
    plan = make_plan(item(1, pomo=3))
    avail = [win(9, 12), win(14, 15)]
    busy = [win(9, 10, 30, 0)]
    # Buchi: 09:00-09:30 (30m), 10:00-12:00 (120m), 14:00-15:00 (60m).
    sched, alts, _ = result_of(plan, avail, busy)
    assert [(s.item.todo_id, s.start) for s in sched.scheduled] == [(1, at(10))]
    plan2 = make_plan(item(2, pomo=6))  # 180m: max 120m < 180m
    sched2, alts2, _ = result_of(plan2, avail, busy)
    assert sched2.scheduled == ()
    assert alts2[2].detail["max_gap_min"] == 120
    assert alts2[2].detail["gap_count"] == 3
    assert outcome_of_sched(sched2, alts2, 2) == OUT_OUTSIDE


def test_8_nessuno_split():
    plan = make_plan(item(1, pomo=3))
    avail = [win(9, 12)]
    busy = [win(9, 10, 30, 0), win(10, 11, 30, 30)]
    sched, _, _ = result_of(plan, avail, busy)
    assert len(sched.scheduled) + len(sched.unscheduled) == 1


def test_9_evidence_coerente_con_classificazione():
    plan = make_plan(item(1, score=50), item(2, score=10), item(3, pomo=6))
    avail = [win(9, 9, 0, 30)]  # un solo buco da 30m
    sched, alts, _ = result_of(plan, avail)
    for alt in alts.values():
        assert set((alt.detail or {})) <= DETAIL_KEYS
        assert o.classify(alt.blocked_by) in (OUT_ELIGIBLE, OUT_OUTSIDE)
    kinds = {tid: outcome_of_sched(sched, alts, tid) for tid in (1, 2, 3)}
    assert kinds[1] == OUT_SCHEDULED
    assert kinds[2] == OUT_ELIGIBLE
    assert kinds[3] == OUT_OUTSIDE


def test_10_determinismo():
    plan = make_plan(item(1, score=50), item(2, score=10), item(3, pomo=6))
    avail = [win(9, 10)]

    def run():
        sched, alts, _ = result_of(plan, avail)
        return (
            [(s.item.todo_id, s.start, s.end) for s in sched.scheduled],
            sorted((tid, outcome_of_sched(sched, alts, tid)) for tid in (1, 2, 3)),
        )

    assert run() == run()


def test_mapping_unitario_tutti_i_kind():
    assert o.classify("tasks") == OUT_ELIGIBLE
    for kind in ("duration", "deadline", "busy", "window"):
        assert o.classify(kind) == OUT_OUTSIDE
    for kind in ("capacity", "user_skip", "", None, "buco_nero"):
        assert o.classify(kind) == OUT_OUTSIDE
    assert o.outcome_of(scheduled=True, blocked_by="window") == OUT_SCHEDULED
    assert o.OUTCOMES == frozenset(
        {"scheduled", "unsched_eligible", "outside_availability"}
    )


def test_decide_non_cambia_con_outcomes():
    plan = make_plan(item(1, score=50), item(2, score=10))
    (d1, d2) = decide(plan, [])
    assert (d1.decision, d2.decision) == ("scheduled", "scheduled")
