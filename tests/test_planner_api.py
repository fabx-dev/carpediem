"""Freeze test del contratto pubblico v2 (Phase 7 v1, F0 time-aware v2).

Congela: versione, superficie promessa, campi/default/ordine dei due
contratti, costruzione kwargs minima, frozen su tutte le classi promesse.
Ogni fallimento qui = cambio breaking deliberato -> bump
PLANNER_CONTRACT_VERSION + aggiornare docs/planner-api.md, mai fixare il
test per farlo passare in silenzio.
"""

import dataclasses
from datetime import date

import src.planner as p
from src.planner import models as m


def test_contract_version_e_2():
    assert p.PLANNER_CONTRACT_VERSION == 2
    assert m.PLANNER_CONTRACT_VERSION == 2


PROMISED = {
    "plan",
    "PlanningRequest",
    "PlanningResult",
    "TaskView",
    "DayPlan",
    "PlanItem",
    "ScheduledDayPlan",
    "ScheduledItem",
    "TimeWindow",
    "FixedEvent",
    "PlanningDecision",
    "PlanAlternative",
    "PlanDiagnostic",
    "ExecutionFeedback",
    "BLOCKED_USER_SKIP",
    "BLOCKED_CAPACITY",
    "BLOCKED_DEADLINE",
    "BLOCKED_BUSY",
    "BLOCKED_WINDOW",
    "BLOCKED_DURATION",
    "BLOCKED_TASKS",
    "BLOCKED_KINDS",
    "DIAG_OVERFLOW",
    "DIAG_CONSTRAINED",
    "DIAG_NO_AVAIL",
    "DIAG_KINDS",
    "DETAIL_KEYS",
    "SCHEDULED",
    "NOT_SCHEDULED",
    "DEFERRED",
    "CONSTRAINED",
    "PLANNER_CONTRACT_VERSION",
}


def test_superficie_promessa_esposta():
    assert PROMISED <= set(p.__all__), PROMISED - set(p.__all__)


def test_campi_request_congelati():
    names = [f.name for f in dataclasses.fields(m.PlanningRequest)]
    assert names == [
        "day",
        "tasks",
        "capacity_pomo",
        "factor",
        "availability",
        "busy",
        "now",
        "sample_count",
    ]


def test_campi_result_congelati():
    names = [f.name for f in dataclasses.fields(m.PlanningResult)]
    assert names == [
        "request",
        "plan",
        "scheduled",
        "decisions",
        "alternatives",
        "diagnostics",
    ]


def test_costruzione_kwargs_minima():
    req = m.PlanningRequest(day=date(2026, 10, 2))
    assert req.tasks == () and req.capacity_pomo == 0.0
    assert req.factor is None and req.now is None
    res = p.plan(req)
    assert res.request is req and res.scheduled is None
    assert res.decisions == () and res.alternatives == ()
    assert res.diagnostics == ()


def test_classi_promesse_frozen():
    from src.planner import decisions as d

    for cls in (
        m.PlanningRequest,
        m.PlanningResult,
        m.TaskView,
        m.DayPlan,
        m.PlanItem,
        m.ScheduledDayPlan,
        m.ScheduledItem,
        m.TimeWindow,
        m.FixedEvent,
        d.PlanningDecision,
        m.PlanAlternative,
        m.PlanDiagnostic,
        m.ExecutionFeedback,
    ):
        assert dataclasses.is_dataclass(cls), cls
        assert cls.__dataclass_params__.frozen, cls


def test_fail_fast_day_invalido_congelato():
    import pytest

    with pytest.raises(ValueError):
        m.PlanningRequest(day="non-una-data")
