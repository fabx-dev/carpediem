"""Fixture deterministiche M1: congelano i comportamenti critici del planner.

A parità di input il risultato deve essere riproducibile: ogni scenario ha
l'output atteso esplicito (formato to_legacy per propose(), slot HH:MM per
schedule()). Se un'implementazione futura cambia uno di questi output, il
test deve rompersi e il cambiamento va giustificato, mai silenziato.
"""

from datetime import datetime

from src.models import Priority
from src.planner import Planner
from src.planner.models import TimeWindow
from tests.conftest import make_todo

TODAY = "2026-09-10"
DAY = (2026, 9, 10)


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(*DAY, h1, m1), datetime(*DAY, h2, m2))


def test_overdue():
    todos = [
        make_todo("A", todo_id=1, due="2026-09-01"),
        make_todo("B", todo_id=2, due=TODAY),
    ]
    assert Planner(todos, today=TODAY).propose().to_legacy() == [
        (1, 110, [("plan_overdue", {})]),
        (2, 70, [("plan_due_today", {})]),
    ]


def test_due_today():
    todos = [make_todo("A", todo_id=1, due=TODAY), make_todo("B", todo_id=2)]
    assert Planner(todos, today=TODAY).propose().to_legacy() == [
        (1, 70, [("plan_due_today", {})]),
        (2, 10, []),
    ]


def test_due_tomorrow():
    todos = [
        make_todo("A", todo_id=1, due="2026-09-11", priority=Priority.HIGH),
        make_todo("B", todo_id=2, priority=Priority.LOW),
    ]
    assert Planner(todos, today=TODAY).propose().to_legacy() == [
        (1, 50, [("plan_due_tomorrow", {}), ("plan_prio", {})]),
        (2, 0, []),
    ]


def test_priorita():
    todos = [
        make_todo("Hi", todo_id=1, priority=Priority.HIGH),
        make_todo("Lo", todo_id=2, priority=Priority.LOW),
    ]
    assert Planner(todos, today=TODAY).propose().to_legacy() == [
        (1, 20, [("plan_prio", {})]),
        (2, 0, []),
    ]


def test_capacita_insufficiente():
    todos = [make_todo(f"T{i}", todo_id=i) for i in range(1, 8)]
    assert Planner(todos, today=TODAY, hours=1.0).propose().to_legacy() == [
        (1, 10, []),
        (2, 10, []),
        *[(i, 10, [("plan_cut", {})]) for i in range(3, 8)],
    ]


def test_busy_windows():
    todos = [
        make_todo("A", todo_id=1, stima_pomo=4),
        make_todo("B", todo_id=2, stima_pomo=4),
    ]
    plan = Planner(todos, today=TODAY).propose()
    sched = Planner.schedule(plan, [_win(9, 0, 18, 0)], [_win(9, 0, 12, 0)])
    assert [
        (s.item.todo_id, s.start.strftime("%H:%M"), s.end.strftime("%H:%M"))
        for s in sched.scheduled
    ] == [
        (1, "12:00", "14:00"),
        (2, "14:00", "16:00"),
    ]
    assert sched.unscheduled == ()


def test_mandatory_non_schedulabile():
    todos = [
        make_todo(f"S{i}", todo_id=i, due="2026-09-01", stima_pomo=4)
        for i in range(1, 4)
    ]
    plan = Planner(todos, today=TODAY).propose()
    assert all(it.mandatory for it in plan.planned)
    sched = Planner.schedule(plan, [_win(9, 0, 10, 0)])
    assert sched.scheduled == ()
    assert [it.todo_id for it in sched.unscheduled] == [1, 2, 3]


def test_saltati():
    todos = [
        make_todo("S", todo_id=1, plan_skip=TODAY),
        make_todo("A", todo_id=2),
    ]
    assert Planner(todos, today=TODAY).propose().to_legacy() == [
        (2, 10, []),
        (1, 10, [("plan_skipped", {})]),
    ]


def test_stime_elevate():
    todos = [
        make_todo("Big", todo_id=1, stima_pomo=10),
        make_todo("Small", todo_id=2, stima_pomo=1),
    ]
    plan = Planner(todos, today=TODAY).propose()
    assert plan.to_legacy() == [(1, 10, []), (2, 10, [])]
    assert {it.todo_id: it.estimate_pomo for it in plan.items} == {1: 10, 2: 1}


def test_piu_progetti():
    todos = [
        make_todo("A", todo_id=1, project="alfa"),
        make_todo("B", todo_id=2, project="alfa"),
        make_todo("C", todo_id=3, project="beta"),
    ]
    assert Planner(todos, today=TODAY).propose().to_legacy() == [
        (1, 10, []),
        (2, 10, []),
        (3, 10, []),
    ]
