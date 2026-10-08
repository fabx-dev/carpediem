"""Invarianti del Planner (P1 §12): fissano il comportamento reale, mai nuovo.

Il planner NON viene modificato in questa fase: questi test falliscono se
un refactor ne altera algoritmo, vincoli o determinismo.
"""

import sys
from datetime import datetime, timedelta

import carpediem.planner.replan  # noqa: F401  (registra sys.modules)
import carpediem.planner.service as svc
from carpediem.planner.capacity import POMO_HOURS
from carpediem.planner.models import TimeWindow
from tests.conftest import make_todo

replan_mod = sys.modules["carpediem.planner.replan"]

TODAY = "2026-09-30"


def _todos():
    return [
        make_todo("scaduto", todo_id=1, due="2026-09-29", stima_pomo=2),
        make_todo("oggi", todo_id=2, due=TODAY, stima_pomo=1),
        make_todo("futuro", todo_id=3, due="2026-10-05", stima_pomo=4),
        make_todo("nodate", todo_id=4, stima_pomo=1),
        make_todo("fatto", todo_id=5, done=True, stima_pomo=2),
        make_todo("sospeso", todo_id=6, paused=True, stima_pomo=2),
    ]


def _plan(todos=None, hours=6.0):
    return svc.Planner(
        todos if todos is not None else _todos(), today=TODAY, hours=hours, factor=1.0
    ).propose()


def _ids(items):
    return [it.todo_id for it in items]


def test_pianificati_sono_eleggibili_ed_esistono():
    todos = _todos()
    live = {t.id for t in todos if t.state == "attivo"}
    for it in _plan(todos).items:
        assert it.todo_id in live


def test_completati_e_sospesi_non_riappaiono():
    plan = _plan()
    assert 5 not in _ids(plan.items)
    assert 6 not in _ids(plan.items)


def test_nessun_duplicato_tra_sezioni():
    plan = _plan()
    all_ids = _ids(plan.items)
    assert len(all_ids) == len(set(all_ids))
    assert set(_ids(plan.planned)).isdisjoint(_ids(plan.cut))
    assert set(_ids(plan.planned)).isdisjoint(_ids(plan.skipped))


def test_determinismo_stessi_input():
    assert _plan() == _plan()


def test_capacita_rappresentata_correttamente():
    plan = _plan(hours=6.0)
    assert plan.capacity_pomo == 6.0 / POMO_HOURS
    assert plan.planned_pomo == sum(it.estimate_pomo for it in plan.planned)


def test_slot_rispettano_durate_e_vincoli():
    plan = _plan()
    day = datetime(2026, 9, 30)
    avail = (TimeWindow(day.replace(hour=9), day.replace(hour=18)),)
    busy = (TimeWindow(day.replace(hour=12), day.replace(hour=13)),)
    sched = svc.Planner.schedule(plan, avail, busy)
    assert {s.item.todo_id for s in sched.scheduled} | {
        i.todo_id for i in sched.unscheduled
    } == set(_ids(plan.planned))
    for s in sched.scheduled:
        assert s.end - s.start == timedelta(hours=POMO_HOURS * s.item.estimate_pomo)
        assert not (s.start < busy[0].end and busy[0].start < s.end)
    starts = sorted(s.start for s in sched.scheduled)
    for a, b in zip(starts, starts[1:]):
        assert a < b  # first-fit: slot distinti e ordinati


def test_replan_senza_duplicati_e_deterministico():
    todos = _todos()
    day = datetime(2026, 9, 30)
    avail = (TimeWindow(day.replace(hour=9), day.replace(hour=18)),)
    now = day.replace(hour=10)
    first = replan_mod.replan(todos, TODAY, 6.0, avail, now=now)
    second = replan_mod.replan(todos, TODAY, 6.0, avail, now=now)
    assert first == second
    ids = [mv.todo_id for mv in first.moves]
    assert len(ids) == len(set(ids))
