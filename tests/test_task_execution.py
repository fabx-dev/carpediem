"""TaskExecution M2: modello, gerarchie planned/actual, variance, conversioni.

Minuti = unita' canonica; pomodori = evidence + snapshot stima. Mai sollevare
su dati invalidi; actual 0 = senza actual (non inventare durate).
"""

import src.domain as domain
import src.models as models
from tests.conftest import make_todo


def test_roundtrip_e_tolleranza():
    e = models.TaskExecution(1, "2026-09-10 09:00", "2026-09-10 10:00", 60, 70, 2, True)
    assert models.TaskExecution.from_dict(e.to_dict()) == e
    bad = models.TaskExecution.from_dict("xx")
    assert (bad.task_id, bad.planned_minutes, bad.completed) == (None, 0, False)
    neg = models.TaskExecution.from_dict({"task_id": 1, "planned_minutes": -5})
    assert neg.planned_minutes == 0


def test_interrotta_rappresentabile():
    e = models.TaskExecution(1, ended_at=None, completed=False)
    assert e.ended_at is None and e.completed is False


def test_resolve_actual_priorita():
    t = make_todo("A", todo_id=1)
    assert domain.resolve_actual_minutes(t) == 0  # senza dati: senza actual
    t.actual_pomo = 2
    assert domain.resolve_actual_minutes(t) == 60  # pomo x 30
    t.actual_minutes = 45
    assert domain.resolve_actual_minutes(t) == 45  # esplicito vince
    t.actual_minutes = -3
    t.actual_pomo = 1
    assert domain.resolve_actual_minutes(t) == 30


def test_resolve_planned_priorita_e_fallback():
    assert domain.resolve_planned_minutes(90, 2) == 90  # slot vince
    assert domain.resolve_planned_minutes(None, 2) == 60  # stima x 30
    assert domain.resolve_planned_minutes(0, 0) == 30  # or-1 come il planner
    assert domain.resolve_planned_minutes("xx", "yy") == 30


def test_variance_none_senza_actual():
    e = models.TaskExecution(1, planned_minutes=60, actual_minutes=0)
    assert domain.execution_variance(e) is None
    e2 = models.TaskExecution(1, planned_minutes=60, actual_minutes=70)
    assert domain.execution_variance(e2) == 10
    e3 = models.TaskExecution(1, planned_minutes=60, actual_minutes=50)
    assert domain.execution_variance(e3) == -10


def test_pomo_minutes_lockstep():
    assert domain.POMO_MINUTES == 30
    assert domain.resolve_actual_minutes(make_todo("A", todo_id=1)) == 0
    t = make_todo("B", todo_id=2)
    t.actual_pomo = 4
    assert domain.resolve_actual_minutes(t) == 120
    assert domain.resolve_planned_minutes(None, 4) == 120


def test_make_execution_puro():
    e = domain.make_execution(7, "s", "e", 30, 40, 1, True)
    assert isinstance(e, models.TaskExecution)
    assert (e.task_id, e.planned_minutes, e.actual_minutes) == (7, 30, 40)
