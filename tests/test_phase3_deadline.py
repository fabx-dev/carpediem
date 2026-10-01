"""Phase 3 Step P3-2 — D2: deadline orarie nello scheduler.

Tabella golden docs/planner-phase3-plan.md §5: solo due-date == plan.day +
orario vincola (bordo inclusivo); scaduti/futuri/senza-ora identici a prima.
E-equivalenza date-only pinnata: con sole date, la mappa non cambia nulla.
"""

from datetime import date, datetime

from src.planner.models import DayPlan, PlanItem, TimeWindow, todo_to_task
from src.planner.scheduler import deadlines_for, schedule
from tests.conftest import make_todo

DAY = date(2026, 9, 10)
TODAY_S = "2026-09-10"


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(2026, 9, 10, h1, m1), datetime(2026, 9, 10, h2, m2))


def _plan(*items):
    return DayPlan(day=DAY, planned=tuple(items))


def _item(tid, pomo=2):
    return PlanItem(tid, 10, (), pomo, False)


def _sched(items, deadlines, avail=None, busy=()):
    return schedule(
        _plan(*items),
        avail if avail is not None else [_win(9, 0, 18, 0)],
        busy,
        deadlines,
    )


def _hhmm(sched):
    return [
        (s.item.todo_id, s.start.strftime("%H:%M"), s.end.strftime("%H:%M"))
        for s in sched.scheduled
    ]


def test_oggi_10_con_2pomo():
    d = {1: (TODAY_S, "10:00")}
    s = _sched([_item(1)], d)
    assert _hhmm(s) == [(1, "09:00", "10:00")]
    assert s.unscheduled == ()


def test_oggi_0930_con_2pomo_unscheduled():
    d = {1: (TODAY_S, "09:30")}
    s = _sched([_item(1)], d)
    assert s.scheduled == () and [it.todo_id for it in s.unscheduled] == [1]


def test_bordo_inclusivo_0930_con_1pomo():
    d = {1: (TODAY_S, "09:30")}
    s = _sched([_item(1, 1)], d)
    assert _hhmm(s) == [(1, "09:00", "09:30")]


def test_scaduto_futuro_e_senza_ora_invariati():
    cases = [
        ({1: ("2026-09-09", "10:00")}, [(1, "09:00", "10:00")]),  # scaduto: merito
        ({1: ("2026-09-11", "10:00")}, [(1, "09:00", "10:00")]),  # futuro
        ({1: (TODAY_S, "")}, [(1, "09:00", "10:00")]),  # senza ora
        ({1: ("xx", "10:00")}, [(1, "09:00", "10:00")]),  # garbage data
        ({1: (TODAY_S, "xx")}, [(1, "09:00", "10:00")]),  # garbage ora
        ({}, [(1, "09:00", "10:00")]),  # mappa assente/vuota
    ]
    for d, expected in cases:
        s = _sched([_item(1)], d)
        assert _hhmm(s) == expected, d
        assert s.unscheduled == ()


def test_mezzanotte_passata_unscheduled():
    s = _sched([_item(1)], {1: (TODAY_S, "00:30")})
    assert s.scheduled == () and [it.todo_id for it in s.unscheduled] == [1]


def test_busy_oltre_scadenza_unscheduled():
    d = {1: (TODAY_S, "10:00")}
    busy = [_win(9, 0, 12, 0)]
    s = _sched([_item(1, 1)], d, busy=busy)
    assert s.scheduled == ()  # il buco 12+ e' oltre la scadenza
    s2 = _sched([_item(1, 1)], {}, busy=busy)
    assert _hhmm(s2) == [(1, "12:00", "12:30")]  # senza vincolo: dopo il busy


def test_primo_fit_rispetta_ordine_e_deadline():
    # A senza vincolo prende 09-10; B (scadenza 10:30, 1🍅) va 10-10:30.
    d = {2: (TODAY_S, "10:30")}
    s = _sched([_item(1), _item(2, 1)], d)
    assert _hhmm(s) == [(1, "09:00", "10:00"), (2, "10:00", "10:30")]


def test_deadlines_for_dai_task():
    todos = [
        make_todo("A", todo_id=1, due="2026-09-10 10:00"),
        make_todo("B", todo_id=2, due="2026-09-10"),
        make_todo("N", todo_id=None, due="2026-09-10 10:00"),
    ]
    assert deadlines_for(todos) == {1: (TODAY_S, "10:00"), 2: (TODAY_S, "")}
    views = [todo_to_task(t) for t in todos[:2]]
    assert deadlines_for(views) == deadlines_for(todos[:2])
    assert deadlines_for(None) == {} and deadlines_for("xx") == {}


def test_e_date_only_identico_con_e_senza_mappa():
    todos = [
        make_todo("A", todo_id=1, due="2026-09-09"),
        make_todo("B", todo_id=2, due=TODAY_S),
        make_todo("C", todo_id=3),
    ]
    from src.planner import Planner

    plan = Planner(todos, today=TODAY_S, hours=6.0).propose()
    avail = [_win(9, 0, 18, 0)]
    assert schedule(plan, avail, ()) == schedule(plan, avail, (), deadlines_for(todos))
