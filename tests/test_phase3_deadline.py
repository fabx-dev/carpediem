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
    # P5-3 (feasibility-first): B vincolata (scadenza 10:30, 1🍅) si colloca
    # prima di A libera, anche se A precede per merito. Il DayPlan non si
    # tocca: cambia solo la sequenza di collocazione.
    d = {2: (TODAY_S, "10:30")}
    items = [_item(1), _item(2, 1)]
    s = _sched(items, d)
    assert _hhmm(s) == [(2, "09:00", "09:30"), (1, "09:30", "10:30")]
    assert [it.todo_id for it in s.plan.planned] == [1, 2]


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


def test_due_time_sempre_formato_valido():
    """G2: due_time e' '' o HH:MM con range reali su qualunque input,
    mai garbage che lo scheduler non saprebbe interpretare."""
    import re

    ok = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    dues = [
        "2026-09-10 10:00",
        "2026-09-10",
        "",
        "xx",
        None,
        "2026-09-10 99:99",
        "2026-09-10 1:2",
        "2026-09-10 10:00:00",
        " 2026-09-10 23:59 ",
    ]
    for i, due in enumerate(dues):
        v = todo_to_task(make_todo("T", todo_id=i + 1, due=due))
        assert v.due_time == "" or ok.match(v.due_time), (due, v.due_time)


def test_p1_placeable_congiunzione():
    """P1 (P4-4): fit + entro-scadenza come congiunti nominati."""
    from datetime import timedelta

    from src.planner.scheduler import _placeable

    slot = _win(9, 0, 18, 0)
    assert _placeable(slot, timedelta(minutes=30), None) is True
    assert _placeable(slot, timedelta(hours=9), None) is True
    assert _placeable(slot, timedelta(hours=9, minutes=1), None) is False
    limit = datetime(2026, 9, 10, 10, 0)
    assert _placeable(slot, timedelta(minutes=60), limit) is True
    assert _placeable(slot, timedelta(minutes=61), limit) is False
    assert _placeable(slot, timedelta(0), datetime(2026, 9, 10, 8, 0)) is False


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


def test_b3_una_cifra_padded_come_storage():
    """B3: H:MM al boundary planner come models._normalize_due (pad),
    mai vincolo orario perso. Grammatica non allargata oltre."""
    from src.planner.models import _due_time_part

    assert _due_time_part("2026-09-10 9:00") == "09:00"
    assert _due_time_part("2026-09-10 09:00") == "09:00"
    assert _due_time_part("2026-09-10 1:2") == ""
    assert _due_time_part("2026-09-10 24:00") == ""
    assert _due_time_part("2026-09-10 10:00:00") == ""
    v = todo_to_task(make_todo("T", todo_id=99, due="2026-09-10 9:00"))
    assert (v.due, v.due_time) == ("2026-09-10", "09:00")
