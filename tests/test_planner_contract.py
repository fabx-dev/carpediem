"""Contratti M1 del Planning Foundation: pipeline, tipi e invarianti.

Fissa il contratto pubblico del boundary src/planner prima di qualunque
estensione (M2+): firme, ordine della pipeline propose(), invarianti di
DayPlan/ScheduledDayPlan, nessuna dipendenza UI. Non duplicano i test di
equivalenza legacy (test_planner.py) né gli unit di scoring/constraints/
capacity/explain: qui solo il contratto del service.
"""

from datetime import datetime

import src.planner.capacity as capacity_mod
import src.planner.constraints as constraints_mod
import src.planner.scoring as scoring_mod
from src.models import Priority
from src.planner import Planner
from src.planner.models import DayPlan, ScheduledDayPlan
from tests.conftest import make_todo

TODAY = "2026-09-10"


def _scenario():
    return [
        make_todo("A-ritardo", todo_id=1, due="2026-09-09", priority=Priority.LOW),
        make_todo("B-oggi", todo_id=2, due="2026-09-10", priority=Priority.HIGH),
        make_todo("C-fatto", todo_id=3, due="2026-09-10"),
        make_todo("D-nodue", todo_id=4, priority=Priority.MEDIUM),
    ]


def test_propose_pipeline_e_firme():
    todos = _scenario()
    todos[2].done = True
    plan = Planner(todos, today=TODAY, hours=6.0, factor=None).propose()
    assert isinstance(plan, DayPlan)
    assert str(plan.day) == TODAY
    # hard-excluded invisibili: il completato non e' in nessuna sezione
    ids = {it.todo_id for it in plan.items}
    assert 3 not in ids
    # eleggibili tutti presenti esattamente una volta tra le sezioni
    assert sorted(ids) == [1, 2, 4]
    assert len(plan.planned) + len(plan.cut) + len(plan.skipped) == len(plan.items)


def test_capacity_e_factor_nel_dayplan():
    todos = _scenario()
    plan = Planner(todos, today=TODAY, hours=6.0, factor=None).propose()
    assert plan.capacity_pomo == 6.0 / 0.5
    assert plan.planned_pomo == sum(it.estimate_pomo for it in plan.planned)
    assert plan.factor is None  # nessun dato: nessuna calibrazione disponibile


def test_mandatory_puo_sforare_senza_invariante():
    todos = [make_todo(f"Scaduto{i}", todo_id=i, due="2026-09-01") for i in range(1, 6)]
    plan = Planner(todos, today=TODAY, hours=0.5, factor=None).propose()
    assert all(it.mandatory for it in plan.planned)
    assert plan.planned_pomo > plan.capacity_pomo


def test_legacy_solo_via_to_legacy():
    todos = _scenario()
    plan = Planner(todos, today=TODAY).propose()
    legacy = plan.to_legacy()
    assert [(i, s) for i, s, _r in legacy] == [
        (it.todo_id, it.score) for it in plan.items
    ]


def test_schedule_thin_wrapper_e_invarianti():
    todos = _scenario()
    plan = Planner(todos, today=TODAY, hours=6.0).propose()
    start = datetime(2026, 9, 10, 9, 0)
    end = datetime(2026, 9, 10, 18, 0)
    sched = Planner.schedule(plan, [(start, end)])
    assert isinstance(sched, ScheduledDayPlan)
    assert sched.plan == plan
    # scheduled+unscheduled coprono esattamente plan.planned
    assert {s.item.todo_id for s in sched.scheduled} | {
        it.todo_id for it in sched.unscheduled
    } == {it.todo_id for it in plan.planned}
    # cut/skipped mai schedulati
    fuori = {it.todo_id for it in plan.cut} | {it.todo_id for it in plan.skipped}
    assert not (fuori & {s.item.todo_id for s in sched.scheduled})


def test_pipeline_usa_tutti_gli_stadi():
    # ogni stadio contribuisce: senza scoring niente merito, senza
    # constraints niente skip, senza capacity niente tagli
    todos = [
        make_todo("Skip", todo_id=1, plan_skip=TODAY),
        make_todo("Nodue", todo_id=2),
    ]
    plan = Planner(todos, today=TODAY, hours=0.5, factor=None).propose()
    by_id = {it.todo_id: it for it in plan.items}
    assert any(k == "plan_skipped" for k, _p in by_id[1].reasons)  # constraints
    assert by_id[2].score >= 0  # scoring
    assert plan.capacity_pomo == 1.0  # capacity


def test_sottomoduli_raggiungibili_dal_boundary():
    assert callable(scoring_mod.score_all)
    assert callable(constraints_mod.is_eligible)
    assert callable(constraints_mod.partition)
    assert callable(capacity_mod.allocate)
    assert callable(capacity_mod.total)
