"""Phase 5 Step P5-3 — F1: feasibility-first (docs/planner-phase5-plan.md §3).

Lo scheduler colloca prima le voci con scadenza odierna (stable: il resto
dell'ordine di merito resta quello del DayPlan, mai riordinato, mai
riscored). Senza scadenze la sequenza e' identica a prima (E3).
"""

from datetime import date, datetime

from src.planner.models import DayPlan, PlanItem, TimeWindow
from src.planner.scheduler import schedule
from tests.conftest import make_todo

DAY = date(2026, 9, 10)
TODAY_S = "2026-09-10"


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(2026, 9, 10, h1, m1), datetime(2026, 9, 10, h2, m2))


def _plan(*items):
    return DayPlan(day=DAY, planned=tuple(items))


def _hhmm(sched):
    return [
        (s.item.todo_id, s.start.strftime("%H:%M"), s.end.strftime("%H:%M"))
        for s in sched.scheduled
    ]


def test_stranding_risolto():
    """A libera capiente (8 pomo) prima per merito + B stretta (scadenza
    10:00, 1 pomo): legacy stranderebbe B, feasibility colloca entrambe."""
    a = PlanItem(1, 100, (), 8, False)
    b = PlanItem(2, 10, (), 1, False)
    d = {2: (TODAY_S, "10:00")}
    s = schedule(_plan(a, b), [_win(9, 0, 18, 0)], (), d)
    assert _hhmm(s) == [(2, "09:00", "09:30"), (1, "09:30", "13:30")]
    assert s.unscheduled == ()


def test_impossibile_resta_unscheduled():
    b = PlanItem(2, 10, (), 4, True)  # 2h non entrano entro le 09:30
    s = schedule(_plan(b), [_win(9, 0, 18, 0)], (), {2: (TODAY_S, "09:30")})
    assert s.scheduled == () and [it.todo_id for it in s.unscheduled] == [2]


def test_dayplan_non_riordinato_ordine_interno_intatto():
    """A chiavi pari (entrambe vincolate o entrambe libere) vale l'ordine
    DayPlan — mai re-scoring, mai riordino merito. Il DayPlan non si tocca."""
    x = PlanItem(1, 50, (), 1, False)
    y = PlanItem(2, 90, (), 1, False)
    d = {1: (TODAY_S, "12:00"), 2: (TODAY_S, "12:00")}
    plan = _plan(x, y)
    s = schedule(plan, [_win(9, 0, 18, 0)], (), d)
    assert _hhmm(s) == [(1, "09:00", "09:30"), (2, "09:30", "10:00")]
    assert [it.todo_id for it in plan.planned] == [1, 2]
    s2 = schedule(plan, [_win(9, 0, 18, 0)], (), {})
    assert _hhmm(s2) == _hhmm(s)  # senza vincoli: stessa sequenza


def test_senza_scadenze_identico_a_prima():
    items = [PlanItem(1, 30, (), 2, False), PlanItem(2, 10, (), 4, False)]
    avail = [_win(9, 0, 12, 0)]
    assert schedule(_plan(*items), avail, (), None) == schedule(
        _plan(*items), avail, (), {}
    )
    s = schedule(_plan(*items), avail, (), {})
    assert _hhmm(s) == [(1, "09:00", "10:00"), (2, "10:00", "12:00")]


def test_end_to_end_con_timed_dues():
    """Via pipeline reale: C overdue (100+) precede B per merito ma B ha la
    scadenza stretta — feasibility la colloca prima, C slitta restando
    pianificata. Selezione (DayPlan) invariata."""
    from src.planner import Planner

    todos = [
        make_todo("C", todo_id=1, due="2026-09-01", stima_pomo=8),
        make_todo("B", todo_id=2, due=f"{TODAY_S} 10:00", stima_pomo=1),
    ]
    plan = Planner(todos, today=TODAY_S, hours=9.0).propose()
    assert [it.todo_id for it in plan.planned] == [1, 2]  # selezione invariata
    from src.planner.scheduler import deadlines_for

    s = Planner.schedule(plan, [_win(9, 0, 18, 0)], (), deadlines_for(todos))
    assert _hhmm(s) == [(2, "09:00", "09:30"), (1, "09:30", "13:30")]
    legacy = Planner.schedule(plan, [_win(9, 0, 18, 0)], ())
    by_id = {x.item.todo_id: x for x in legacy.scheduled}
    assert (
        by_id[2].end.strftime("%H:%M") == "13:30"
    )  # prima: dentro, ma OLTRE la scadenza
