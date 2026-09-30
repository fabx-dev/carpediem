"""Property-based testing del Planner con Hypothesis (P1 §13).

Proprieta' forti e semplici, insiemi piccoli e veloci (CI-safe):
determinismo, niente duplicati, coerenza interna del DayPlan.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import src.planner.service as svc
from tests.conftest import make_todo

TODAY = "2026-09-30"

_states = st.sampled_from(["attivo", "attivo", "attivo", "done", "paused"])
_dues = st.sampled_from(["", "2026-09-29", TODAY, "2026-10-05"])
_stime = st.integers(min_value=0, max_value=6)


@st.composite
def _task_sets(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    todos = []
    for i in range(n):
        state = draw(_states)
        kw = {}
        if state == "done":
            kw["done"] = True
        elif state == "paused":
            kw["paused"] = True
        todos.append(
            make_todo(
                f"T{i}",
                todo_id=i + 1,
                due=draw(_dues),
                stima_pomo=draw(_stime),
                **kw,
            )
        )
    return todos


def _plan(todos):
    return svc.Planner(todos, today=TODAY, hours=6.0, factor=1.0).propose()


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(_task_sets())
def test_determinismo(todos):
    assert _plan(todos) == _plan(todos)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(_task_sets())
def test_niente_duplicati_e_coerenza_sezioni(todos):
    plan = _plan(todos)
    all_ids = [it.todo_id for it in plan.items]
    assert len(all_ids) == len(set(all_ids))
    assert tuple(plan.items) == (*plan.planned, *plan.cut, *plan.skipped)
    assert plan.planned_pomo == sum(it.estimate_pomo for it in plan.planned)


@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(_task_sets())
def test_solo_eleggibili_nel_piano(todos):
    plan = _plan(todos)
    live = {t.id for t in todos if t.state == "attivo"}
    for it in plan.items:
        assert it.todo_id in live
