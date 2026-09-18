"""Contratto del boundary Planner (Fase 1: delega pura a plan_day)."""

from src.models import Priority
from src.plan import plan_day
from src.planner import Planner
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _scenario():
    return [
        make_todo("A-ritardo", todo_id=1, due="2026-09-09", priority=Priority.LOW),
        make_todo("B-oggi", todo_id=2, due="2026-09-10", priority=Priority.HIGH),
        make_todo("C-domani", todo_id=3, due="2026-09-11", priority=Priority.HIGH),
        make_todo("D-nodue", todo_id=4, priority=Priority.MEDIUM),
        make_todo("E-pianificato", todo_id=5, planned_for=TODAY),
        make_todo("F-scartato", todo_id=6, plan_skip=TODAY),
        make_todo("G-stimato", todo_id=7, stima_pomo=3),
    ]


def test_propose_equivale_plan_day():
    todos = _scenario()
    expected = plan_day(todos, today=TODAY, hours=6.0, factor=None)
    actual = Planner(todos, today=TODAY, hours=6.0, factor=None).propose()
    assert actual == expected


def test_propose_propaga_today():
    todos = _scenario()
    assert Planner(todos, today=TODAY).propose() == plan_day(todos, today=TODAY)
    assert Planner(todos, today="2026-09-11").propose() == plan_day(
        todos, today="2026-09-11"
    )


def test_propose_propaga_hours():
    todos = _scenario()
    for hours in (0, 0.5, 1.0, 2.5, 6.0):
        assert Planner(todos, today=TODAY, hours=hours).propose() == plan_day(
            todos, today=TODAY, hours=hours
        )


def test_propose_propaga_factor():
    todos = _scenario()
    for factor in (None, 0.5, 2.0, 3.0, "xx"):
        assert Planner(todos, today=TODAY, factor=factor).propose() == plan_day(
            todos, today=TODAY, factor=factor
        )


def test_propose_non_muta_input_e_non_altera_vincoli():
    todos = _scenario()
    before = [(t.id, t.planned_for, t.plan_skip) for t in todos]
    plan = Planner(todos, today=TODAY, hours=1.0, factor=2.0).propose()
    assert [(t.id, t.planned_for, t.plan_skip) for t in todos] == before
    reasons = {t_id: [k for k, _p in r] for t_id, _s, r in plan}
    assert "plan_cut" in reasons[4]  # capacita' 2 pomodori: D-nodue tagliato
    assert "plan_skipped" in reasons[6]
    assert "plan_overdue" in reasons[1]


def test_propose_lista_vuota():
    assert Planner([], today=TODAY).propose() == plan_day([], today=TODAY) == []
