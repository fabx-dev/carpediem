"""Phase 2 Step P2-1 — U1/U2: PlanningRequest/PlanningResult.

Forme di lavoro interne (instabili fino a Phase 7): normalizzazione,
fail-fast sul giorno, frozen, discipline campi. Nessun consumer ancora —
la facade arriva in P2-2."""

import dataclasses
from datetime import date, datetime

import pytest

from src.planner.models import (
    PlanningRequest,
    PlanningResult,
    TaskView,
    TimeWindow,
    todo_to_task,
)
from tests.conftest import make_todo

TODAY = date(2026, 9, 10)

EXPECTED_REQUEST_FIELDS = [
    "day",
    "tasks",
    "capacity_pomo",
    "factor",
    "availability",
    "busy",
    "now",
    "sample_count",
]

EXPECTED_RESULT_FIELDS = ["request", "plan", "scheduled", "decisions"]


def test_u1_liste_campi_esatte():
    """Fail-closed come T2: ogni campo richiede un consumer Phase-2 reale."""
    assert [f.name for f in dataclasses.fields(PlanningRequest)] == (
        EXPECTED_REQUEST_FIELDS
    )
    assert [f.name for f in dataclasses.fields(PlanningResult)] == (
        EXPECTED_RESULT_FIELDS
    )


def test_u1_frozen():
    req = PlanningRequest(day=TODAY)
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.capacity_pomo = 99.0  # type: ignore[misc]


def test_u1_normalizza_misto_e_contenitori():
    todos = [
        make_todo("A", todo_id=1, due="2026-09-10"),
        todo_to_task(make_todo("B", todo_id=2)),
    ]
    req = PlanningRequest(
        day=TODAY,
        tasks=todos,
        availability=[
            TimeWindow(datetime(2026, 9, 10, 9, 0), datetime(2026, 9, 10, 18, 0))
        ],
    )
    assert all(isinstance(t, TaskView) for t in req.tasks)
    assert [t.id for t in req.tasks] == [1, 2]
    assert isinstance(req.tasks, tuple)
    assert isinstance(req.availability, tuple) and len(req.availability) == 1
    assert req.busy == () and req.factor is None


def test_u1_giorno_fail_fast():
    assert PlanningRequest(day=datetime(2026, 9, 10, 23, 59)).day == TODAY
    with pytest.raises(ValueError):
        PlanningRequest(day="2026-09-10")
    with pytest.raises(ValueError):
        PlanningRequest(day=None)
    with pytest.raises(ValueError):
        PlanningRequest(day=TODAY, tasks=None)


def test_u1_capacita_coercizione():
    assert PlanningRequest(day=TODAY, capacity_pomo=12.0).capacity_pomo == 12.0
    assert PlanningRequest(day=TODAY, capacity_pomo=-3).capacity_pomo == 0.0
    assert PlanningRequest(day=TODAY, capacity_pomo="xx").capacity_pomo == 0.0


def test_u2_result_eco_e_default():
    from src.planner import Planner

    todos = [make_todo("A", todo_id=1, due="2026-09-10")]
    req = PlanningRequest(day=TODAY, tasks=todos, capacity_pomo=12.0)
    plan = Planner(todos, today="2026-09-10", hours=6.0).propose()
    res = PlanningResult(request=req, plan=plan)
    assert res.request is req  # eco identica, tracciabilita'
    assert res.plan == plan
    assert res.scheduled is None  # senza availability: decisione, non slot
    assert res.decisions == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.plan = plan  # type: ignore[misc]
