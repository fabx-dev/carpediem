"""Phase 6 Step P6-1 — D1: tipi diagnostici (piano revisionato §3 X-What).

Forme frozen, vocabolari chiusi fail-closed, niente campi futuribili.
Nessun consumer ancora (diagnose in P6-2)."""

import dataclasses

import pytest

from carpediem.planner import models as m


def test_d1_liste_campi_esatte():
    assert [f.name for f in dataclasses.fields(m.PlanAlternative)] == [
        "todo_id",
        "decision",
        "blocked_by",
        "detail",
    ]
    assert [f.name for f in dataclasses.fields(m.PlanDiagnostic)] == [
        "kind",
        "detail",
    ]
    assert [f.name for f in dataclasses.fields(m.PlanningResult)] == [
        "request",
        "plan",
        "scheduled",
        "decisions",
        "alternatives",
        "diagnostics",
    ]


def test_d1_vocabolari_chiusi():
    assert m.BLOCKED_KINDS == frozenset(
        {"user_skip", "capacity", "deadline", "busy", "window", "duration", "tasks"}
    )
    assert m.DIAG_KINDS == frozenset(
        {"overflow", "constrained_mandatory", "empty_availability"}
    )
    assert m.DETAIL_KEYS == frozenset(
        {
            "needed_min",
            "deadline",
            "busy_titles",
            "task_ids",
            "estimate_pomo",
            "capacity_pomo",
            "planned_pomo",
            "over_pomo",
            "count",
            "todo_ids",
            "planned_count",
            # F2: dimensioni dei buchi (task atomici non collocabili).
            "max_gap_min",
            "gap_count",
        }
    )


def test_d1_frozen_e_default():
    a = m.PlanAlternative(1, "not_scheduled", m.BLOCKED_CAPACITY, {"estimate_pomo": 2})
    assert a.detail == {"estimate_pomo": 2}
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.blocked_by = m.BLOCKED_BUSY  # type: ignore[misc]
    d = m.PlanDiagnostic("overflow", {"over_pomo": 3})
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.kind = "x"  # type: ignore[misc]


def test_b11_probe_order_documentato():
    """B11: _PROBE_ORDER e docstring PlanAlternative allineati (tasks incluso)."""
    import carpediem.planner.diagnostics as dg
    import carpediem.planner.models as m

    assert dg._PROBE_ORDER == (
        m.BLOCKED_DURATION,
        m.BLOCKED_TASKS,
        m.BLOCKED_DEADLINE,
        m.BLOCKED_BUSY,
        m.BLOCKED_WINDOW,
    )
    assert "tasks" in m.PlanAlternative.__doc__
