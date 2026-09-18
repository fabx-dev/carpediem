"""Test DayPlan (Fase 3: Planner.propose() -> modello esplicito, senza Textual)."""

from dataclasses import FrozenInstanceError

import pytest

from src.models import Priority
from src.plan import plan_day
from src.planner import DayPlan, PlanItem, Planner
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _by_id(plan):
    return {it.todo_id: it for it in plan.items}


def test_propose_restituisce_dayplan_immutabile():
    plan = Planner([make_todo("A", todo_id=1)], today=TODAY).propose()
    assert isinstance(plan, DayPlan)
    assert isinstance(plan.planned, tuple) and isinstance(plan.items, tuple)
    with pytest.raises(FrozenInstanceError):
        plan.planned_pomo = 99  # type: ignore[misc]


def test_planned_con_id_score_reasons_estimate_mandatory():
    todos = [
        make_todo(
            "O", todo_id=1, due="2026-09-01", priority=Priority.HIGH, stima_pomo=2
        ),
        make_todo("B", todo_id=2, stima_pomo=3),
    ]
    plan = Planner(todos, today=TODAY, hours=6.0).propose()
    assert [it.todo_id for it in plan.planned] == [1, 2]
    first = plan.planned[0]
    assert isinstance(first, PlanItem)
    assert (first.score, first.estimate_pomo, first.mandatory) == (120, 2, True)
    assert ("plan_overdue", {}) in first.reasons
    assert _by_id(plan)[2].mandatory is False


def test_skipped_distinti_e_cut_rappresentati():
    todos = [
        make_todo("S", todo_id=1, plan_skip=TODAY),
        make_todo("A", todo_id=2),
        make_todo("B", todo_id=3),
    ]
    plan = Planner(todos, today=TODAY, hours=0.5).propose()  # 1 pomo
    assert [it.todo_id for it in plan.skipped] == [1]
    assert [it.todo_id for it in plan.planned] == [2]
    assert [it.todo_id for it in plan.cut] == [3]
    assert any(k == "plan_skipped" for k, _p in plan.skipped[0].reasons)
    assert any(k == "plan_cut" for k, _p in plan.cut[0].reasons)
    assert not plan.planned[0].reasons or all(
        k != "plan_cut" for k, _p in plan.planned[0].reasons
    )


def test_capacity_e_mandatory_che_sfora():
    big = make_todo("Big", todo_id=1, due="2026-09-01", stima_pomo=50)
    plan = Planner([big], today=TODAY, hours=1.0).propose()  # capacita' 2 pomo
    assert plan.capacity_pomo == 2.0
    assert plan.planned_pomo == 50  # il mandatory sfora: nessun invariante
    assert plan.planned_pomo > plan.capacity_pomo
    assert [it.todo_id for it in plan.planned] == [1]


def test_factor_memorizzato_normalizzato():
    assert (
        Planner([make_todo("A", todo_id=1)], today=TODAY, factor=99.0).propose().factor
        == 3.0
    )
    assert (
        Planner([make_todo("A", todo_id=1)], today=TODAY, factor="xx").propose().factor
        is None
    )
    assert Planner([make_todo("A", todo_id=1)], today=TODAY).propose().factor is None


def test_hard_excluded_non_compaiono():
    todos = [
        make_todo("D", todo_id=1, done=True),
        make_todo("P", todo_id=2, paused=True),
        make_todo("N", todo_id=None),
        make_todo("A", todo_id=3),
    ]
    plan = Planner(todos, today=TODAY).propose()
    assert [it.todo_id for it in plan.items] == [3]


def test_day_e_determinismo():
    todos = [make_todo("A", todo_id=1), make_todo("B", todo_id=2, due=TODAY)]
    plan = Planner(todos, today=TODAY, hours=1.0, factor=2.0).propose()
    assert str(plan.day) == TODAY
    assert Planner(todos, today=TODAY, hours=1.0, factor=2.0).propose() == plan


def _matrix():
    rich = [
        make_todo("O", todo_id=1, due="2026-09-01", stima_pomo=2),
        make_todo("T", todo_id=2, due=TODAY, plan_skip=TODAY),
        make_todo("P", todo_id=3, planned_for=TODAY, stima_pomo=4),
        make_todo("F", todo_id=4, due="2026-09-11"),
        make_todo("X", todo_id=5, done=True),
        make_todo("N", todo_id=None),
    ]
    return [
        ([], {}),
        ([make_todo("A", todo_id=1)], {}),
        (rich, {}),
        (rich, {"hours": 0}),
        (rich, {"hours": "x"}),
        (rich, {"hours": 0.5}),
        (rich, {"factor": 2.0}),
        (rich, {"factor": "xx"}),
        (rich, {"factor": 99.0}),
        (rich, {"today": "2026-09-11"}),
    ]


@pytest.mark.parametrize("todos,kwargs", _matrix())
def test_to_legacy_equivale_plan_day(todos, kwargs):
    kw = dict(kwargs)
    today = kw.pop("today", TODAY)
    plan = Planner(todos, today=today, **kw).propose()
    assert plan.to_legacy() == plan_day(todos, today, **kw)


def test_to_legacy_con_calibrazione_reale():
    todos = []
    for i, (est, act) in enumerate([(2, 4), (2, 4), (1, 2), (3, 6), (1, 2)], start=1):
        t = make_todo(f"D{i}", todo_id=i, stima_pomo=est, actual_pomo=act)
        t.done = True
        t.completed_at = "2026-09-09 10:00"
        todos.append(t)
    todos.append(make_todo("N", todo_id=6, stima_pomo=2))
    plan = Planner(todos, today=TODAY).propose()
    assert plan.factor == 2.0
    assert plan.to_legacy() == plan_day(todos, TODAY)
