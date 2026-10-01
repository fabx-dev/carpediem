"""Phase 1 Step 1 — T2: TaskView projection (docs/planner-phase1-plan.md §5).

TaskView e' una proiezione/compat, non il futuro Task canonico: questi test
fissano la disciplina (lista campi esatta, frozen, totalita' del
convertitore, normalizzazioni fedeli a TodoItem). Nessun consumer di
produzione ancora — il core continua a ricevere TodoItem."""

import dataclasses
import types

import pytest

from src.models import Priority
from src.planner.models import TaskView, todo_to_task
from tests.conftest import make_todo

EXPECTED_FIELDS = [
    "id",
    "state",
    "due",
    "due_time",
    "priority",
    "project",
    "planned_for",
    "plan_skip",
    "estimate_pomo",
    "actual_pomo",
    "created",
    "completed_at",
    "pomodoros",
    "actual_minutes",
]


def test_t2_lista_campi_esatta():
    """Fail-closed su aggiunte future: ogni campo richiede giustificazione
    nell'algoritmo corrente (piano §5.0)."""
    assert [f.name for f in dataclasses.fields(TaskView)] == EXPECTED_FIELDS


def test_t2_frozen_e_default():
    view = TaskView()
    assert view.id is None
    assert view.state == ""
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.state = "attivo"  # type: ignore[misc]


def test_t2_normalizza_todoitem():
    todo = make_todo(
        "X",
        todo_id=7,
        due="2026-09-10 14:00",
        priority=Priority.HIGH,
        project="MiXed ",
        planned_for="2026-09-10",
        plan_skip="2026-09-09",
        stima_pomo=4,
        actual_pomo=6,
        created="2026-09-01",
        completed_at="",
        pomodoros=2,
        actual_minutes=90,
    )
    assert todo_to_task(todo) == TaskView(
        id=7,
        state="attivo",
        due="2026-09-10",
        due_time="14:00",
        priority="alta",
        project="mixed",
        planned_for="2026-09-10",
        plan_skip="2026-09-09",
        estimate_pomo=4,
        actual_pomo=6,
        created="2026-09-01",
        completed_at="",
        pomodoros=2,
        actual_minutes=90,
    )


def test_t2_stati_e_priorita():
    done = make_todo("D", todo_id=1)
    done.done = True
    assert todo_to_task(done).state == "completato"
    paused = make_todo("P", todo_id=2)
    paused.paused = True
    assert todo_to_task(paused).state == "in_sospeso"
    low = make_todo("L", todo_id=3, priority=Priority.LOW)
    assert todo_to_task(low).priority == "bassa"
    med = make_todo("M", todo_id=4)
    assert todo_to_task(med).priority == "media"


def test_t2_due_time_solo_orari_validi():
    """P3-1: due_time = HH:MM con range reali, altrimenti '' (mai vincoli
    inventati dallo scheduler)."""
    assert todo_to_task(make_todo("A", todo_id=1, due="2026-09-10")).due_time == ""
    assert todo_to_task(make_todo("C", todo_id=3, due="")).due_time == ""
    # TodoItem normalizza "9:30" in forma valida: qui raw via namespace.
    for raw, expected in (
        ("2026-09-10 09:30", "09:30"),
        ("2026-09-10 9:30", ""),
        ("2026-09-10 24:00", ""),
        ("2026-09-10 12:60", ""),
        ("2026-09-10 xx:yy", ""),
        ("2026-09-10 09:30:00", ""),
        ("2026-09-10", ""),
        ("", ""),
    ):
        view = todo_to_task(types.SimpleNamespace(due=raw))
        assert view.due_time == expected, raw


def test_t2_totalita_mai_solleva():
    assert todo_to_task(types.SimpleNamespace()) == TaskView(state="attivo")
    assert todo_to_task(types.SimpleNamespace(done=True)).state == "completato"
    assert todo_to_task(types.SimpleNamespace(paused=True)).state == "in_sospeso"
    garbage = types.SimpleNamespace(
        id="abc",
        state=None,
        due=None,
        priority=None,
        project=None,
        planned_for=None,
        plan_skip=None,
        stima_pomo="xx",
        actual_pomo=-5,
        created=None,
        completed_at=None,
        pomodoros="yy",
        actual_minutes=None,
        done=False,
        paused=False,
    )
    view = todo_to_task(garbage)
    assert view.id is None
    assert view.state == "attivo"
    assert view.due == ""
    assert view.priority == ""
    assert view.estimate_pomo == 0
    assert view.actual_pomo == 0  # clamp come TodoItem, non negativo
    assert view.pomodoros == 0


def test_t2_nessun_campo_applicativo():
    """La projection non trasporta vocabolario storage/UI."""
    names = {f.name for f in dataclasses.fields(TaskView)}
    for leaked in (
        "title",
        "notes",
        "tags",
        "parent_id",
        "recurrence",
        "source",
        "external_id",
        "pomodoro_log",
    ):
        assert leaked not in names
    todo = make_todo("Titolo", todo_id=1, notes="n", tags=["a"], parent_id=9)
    view = todo_to_task(todo)
    assert not hasattr(view, "title")
    assert view == TaskView(id=1, state="attivo", priority="media")
