"""Decisioni M3: decide() come lettura del DayPlan, refine da scheduler.

Niente secondo scoring, niente pesi toccati, legacy invariato. Confidence
solo con stima calibrata (livelli M2), altrimenti None. CONSTRAINED solo
mandatory senza slot valido.
"""

from datetime import datetime

import src.planner.decisions as dec
from src.models import Priority
from src.planner import Planner, decide, primary_reason, refine_with_schedule
from src.planner.models import TimeWindow
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _scenario(hours=0.5):
    todos = [
        make_todo("A-ritardo", todo_id=1, due="2026-09-01"),
        make_todo("B-nodue", todo_id=2),
        make_todo("C-skip", todo_id=3, plan_skip=TODAY),
    ]
    return todos, Planner(todos, today=TODAY, hours=hours).propose()


def test_mapping_tre_sezioni():
    todos, plan = _scenario()
    by_id = {d.todo_id: d for d in decide(plan, todos)}
    assert by_id[1].decision == dec.SCHEDULED
    assert by_id[2].decision == dec.NOT_SCHEDULED
    assert by_id[3].decision == dec.DEFERRED
    assert {d.todo_id for d in decide(plan, todos)} == {1, 2, 3}


def test_non_eleggibili_mai_decisioni():
    todos = [make_todo("Fatto", todo_id=1)]
    todos[0].done = True
    plan = Planner(todos, today=TODAY).propose()
    assert decide(plan, todos) == ()


def test_evidence_dati_reali():
    todos = [
        make_todo("A", todo_id=1, due="2026-09-01", priority=Priority.HIGH),
        make_todo("B", todo_id=2),
    ]
    plan = Planner(todos, today=TODAY).propose()
    by_id = {d.todo_id: d for d in decide(plan, todos)}
    a = by_id[1].evidence
    assert a["due"] == "2026-09-01" and a["priority"] == "alta"
    assert a["overdue"] is True and a["mandatory"] is True
    assert a["score"] == 120 and (a["rank"], a["rank_of"]) == (1, 2)
    assert a["estimate_pomo"] == 1 and a["estimate_minutes"] == 30
    assert a["capacity_pomo"] == 12.0
    b = by_id[2].evidence
    assert b["due"] == "" and b["overdue"] is False and b["mandatory"] is False


def test_reasons_invariate_e_legacy_invariato():
    todos, plan = _scenario()
    before = plan.to_legacy()
    decisions = decide(plan, todos)
    assert [list(d.reasons) for d in decisions] == [r for _i, _s, r in before]
    assert plan.to_legacy() == before


def test_determinismo():
    todos, plan = _scenario()
    assert decide(plan, todos) == decide(plan, todos)


def test_confidence_none_senza_calibration():
    todos, plan = _scenario()
    assert all(d.confidence is None for d in decide(plan, todos))


def _seed_calibrati(n, actual_pomo=4):
    todos = []
    for i in range(1, n + 1):
        t = make_todo(f"F{i}", todo_id=100 + i, stima_pomo=2)
        t.done = True
        t.completed_at = "2026-09-12 10:00"
        t.actual_pomo = actual_pomo
        todos.append(t)
    todos.append(make_todo("Attivo", todo_id=1, stima_pomo=2, due=TODAY))
    return todos


def test_confidence_con_stima_calibrata():
    for n, level in ((5, "LOW"), (10, "MEDIUM"), (30, "HIGH")):
        todos = _seed_calibrati(n)
        plan = Planner(todos, today=TODAY).propose()
        by_id = {d.todo_id: d for d in decide(plan, todos, sample_count=n)}
        assert by_id[1].confidence == level
        assert any(k == "plan_calibrated" for k, _p in by_id[1].reasons)


def test_confidence_none_senza_sample_count():
    todos = _seed_calibrati(10)
    plan = Planner(todos, today=TODAY).propose()
    by_id = {d.todo_id: d for d in decide(plan, todos)}
    assert by_id[1].confidence is None


def test_refine_slot_e_constrained():
    todos = [
        make_todo("M", todo_id=1, due="2026-09-01", stima_pomo=4),
        make_todo("B", todo_id=2, stima_pomo=1),
    ]
    plan = Planner(todos, today=TODAY).propose()
    decisions = decide(plan, todos)
    sched = Planner.schedule(
        plan, [TimeWindow(datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 10, 0))]
    )
    refined = refine_with_schedule(decisions, sched)
    by_id = {d.todo_id: d for d in refined}
    # M (2h) non entra in 1h: mandatory senza slot -> CONSTRAINED
    assert by_id[1].decision == dec.CONSTRAINED
    assert by_id[2].decision == dec.SCHEDULED
    assert by_id[2].evidence["slot_start"] == "2026-09-10 09:00"
    assert by_id[2].evidence["slot_end"] == "2026-09-10 09:30"
    # input non mutato (frozen semantico)
    assert all(a == b for a, b in zip(decisions, decide(plan, todos)))
    assert decisions[0].decision == dec.SCHEDULED


def test_constrained_mai_overlap_ne_orari_inventati():
    todos = [make_todo(f"S{i}", todo_id=i, due="2026-09-01") for i in range(1, 4)]
    plan = Planner(todos, today=TODAY).propose()
    sched = Planner.schedule(
        plan, [TimeWindow(datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 9, 30))]
    )
    slots = [(s.start, s.end) for s in sched.scheduled]
    for a_start, a_end in slots:
        for b_start, b_end in slots:
            assert not (a_start < b_end and b_start < a_end) or (a_start, a_end) == (
                b_start,
                b_end,
            )
    refined = refine_with_schedule(decide(plan, todos), sched)
    assert [d.decision for d in refined].count(dec.CONSTRAINED) >= 1
    for d in refined:
        assert "slot_start" not in (d.evidence or {}) or d.decision == dec.SCHEDULED


def test_refine_none_e_non_scheduled_invariati():
    todos, plan = _scenario()
    decisions = decide(plan, todos)
    assert refine_with_schedule(decisions, None) == decisions
    sched = Planner.schedule(
        plan, [TimeWindow(datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 18, 0))]
    )
    refined = {d.todo_id: d for d in refine_with_schedule(decisions, sched)}
    assert refined[2].decision == dec.NOT_SCHEDULED
    assert refined[3].decision == dec.DEFERRED


def test_primary_reason_flag_prima_e_none():
    todos, plan = _scenario()
    by_id = {d.todo_id: d for d in decide(plan, todos)}
    assert primary_reason(by_id[2]) == ("plan_cut", {})
    assert primary_reason(by_id[3]) == ("plan_skipped", {})
    assert primary_reason(by_id[1]) == ("plan_overdue", {})
    empty = dec.PlanningDecision(9, dec.SCHEDULED, (), {}, None)
    assert primary_reason(empty) is None
