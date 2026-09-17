"""Test logica di dominio pura (senza app/pilot)."""

import pytest

from src import domain
from src.models import Priority, Recurrence
from tests.conftest import make_todo


def test_apply_state_attivo_e_sospeso():
    t = make_todo("X", done=True, completed_at="2026-09-10 10:00")
    assert domain.apply_state(t, "attivo", "2026-09-12 10:00") is None
    assert (t.done, t.paused, t.completed_at) == (False, False, "")
    assert domain.apply_state(t, "in_sospeso", "2026-09-12 10:00") is None
    assert (t.done, t.paused, t.completed_at) == (False, True, "")


def test_apply_state_completato_senza_ricorrenza():
    t = make_todo("X", todo_id=1, planned_for="2026-09-12")
    assert domain.apply_state(t, "completato", "2026-09-12 10:00") is None
    assert t.done and not t.paused
    assert t.planned_for == "" and t.completed_at == "2026-09-12 10:00"


def test_apply_state_completato_con_ricorrenza():
    t = make_todo(
        "X",
        todo_id=1,
        due="2026-09-12 09:00",
        recurrence=Recurrence.DAILY,
        project="casa",
        tags=["a"],
        notes="n",
        priority=Priority.HIGH,
        parent_id=7,
        stima_pomo=4,
    )
    new = domain.apply_state(t, "completato", "2026-09-12 10:00")
    assert t.done and t.completed_at == "2026-09-12 10:00"
    assert new is not None and new.id is None  # id lo assegna lo store
    assert new.due == "2026-09-13 09:00"  # next daily, orario preservato
    assert (new.title, new.project, new.tags, new.notes) == ("X", "casa", ["a"], "n")
    assert new.priority == Priority.HIGH and new.parent_id == 7
    assert new.recurrence == Recurrence.DAILY
    assert new.stima_pomo == 4  # B1: la ricorrenza eredita la stima


def test_apply_state_scelta_invalida():
    with pytest.raises(ValueError):
        domain.apply_state(make_todo("X"), "boh", "2026-09-12 10:00")


def test_credit_pomodoro():
    t = make_todo("X", todo_id=1)
    domain.credit_pomodoro(t, "2026-09-12 10:25")
    domain.credit_pomodoro(t, "2026-09-12 10:55")
    assert t.pomodoros == 2
    assert t.pomodoro_log == ["2026-09-12 10:25", "2026-09-12 10:55"]


def test_apply_form():
    t = make_todo("Vecchio", todo_id=1)
    domain.apply_form(
        t,
        {
            "title": "Nuovo",
            "priority": Priority.HIGH,
            "due": "2026-09-13",
            "notes": "n",
            "recurrence": Recurrence.WEEKLY,
            "tags": ["x"],
            "project": "casa",
            "stima_pomo": 3,
        },
    )
    assert t.title == "Nuovo" and t.priority == Priority.HIGH
    assert t.due == "2026-09-13" and t.recurrence == Recurrence.WEEKLY
    assert t.tags == ["x"] and t.project == "casa" and t.stima_pomo == 3


def test_review_plan_aggiunge_e_toglie():
    a = make_todo("A", todo_id=1)
    b = make_todo("B", todo_id=2, planned_for="2026-09-13")
    c = make_todo("C", todo_id=3, done=True, completed_at="2026-09-12 10:00")
    n, k = domain.review_plan([a, b, c], {1}, "2026-09-13")
    assert (n, k) == (1, 1)
    assert a.planned_for == "2026-09-13" and b.planned_for == ""
    assert c.planned_for == ""  # completati mai toccati


def test_proposal_plan_additivo():
    a = make_todo("A", todo_id=1)
    b = make_todo("B", todo_id=2, planned_for="2026-09-12")
    c = make_todo("C", todo_id=3, done=True, completed_at="2026-09-12 10:00")
    d = make_todo("D", todo_id=4)
    n, r = domain.proposal_plan([a, b, c, d], {1}, "2026-09-12")
    assert (n, r) == (1, 1)  # a aggiunto, d scartato; b gia' pianificato resta
    assert a.planned_for == "2026-09-12" and a.plan_skip == ""
    assert d.plan_skip == "2026-09-12" and d.planned_for == ""
    assert b.planned_for == "2026-09-12" and b.plan_skip == ""
    assert c.planned_for == ""


def test_plan_add_remove_suspend():
    t = make_todo("X", todo_id=1)
    domain.plan_add(t, "2026-09-12")
    assert t.planned_for == "2026-09-12"
    domain.plan_remove(t)
    assert t.planned_for == ""
    domain.plan_add(t, "2026-09-12")
    domain.plan_suspend(t)
    assert t.paused and t.planned_for == "2026-09-12"


def test_matches_smart_and_e_wildcard():
    t = make_todo("Bollette luce", todo_id=1, tags=["casa"], project="casa")
    assert domain.matches_smart(t, {})
    assert domain.matches_smart(t, {"state": "attivo"})
    assert not domain.matches_smart(t, {"state": "completato"})
    assert domain.matches_smart(t, {"tag": "CASA"})  # case-insensitive
    assert not domain.matches_smart(t, {"tag": "lavoro"})
    assert domain.matches_smart(t, {"project": "casa", "search": "bollette"})
    assert not domain.matches_smart(t, {"project": "casa", "search": "gas"})
    assert domain.matches_smart(t, "malformata")  # mai solleva
    # Vocabolario filtri: "completati" (plurale) matcha lo stato "completato"
    c = make_todo("Fatto", todo_id=2, done=True, completed_at="2026-09-12 10:00")
    assert domain.matches_smart(c, {"state": "completati"})
    assert domain.matches_smart(c, {"state": "completato"})
    assert not domain.matches_smart(t, {"state": "completati"})


def test_record_actual_clamp():
    t = make_todo("X", todo_id=1)
    domain.record_actual(t, 3, 75)
    assert (t.actual_pomo, t.actual_minutes) == (3, 75)
    domain.record_actual(t, -2, "xx")
    assert (t.actual_pomo, t.actual_minutes) == (0, 0)


def _done_with(actual: int, est: int, tid: int):
    t = make_todo("X", todo_id=tid, stima_pomo=est)
    t.done = True
    t.completed_at = "2026-09-12 10:00"
    t.actual_pomo = actual
    return t


def test_calibration_factor_min_campioni_e_mediana():
    assert domain.calibration_factor([]) is None
    pochi = [_done_with(4, 2, i) for i in range(1, 5)]
    assert domain.calibration_factor(pochi) is None  # < 5 campioni
    # 5 campioni x2.0 + 1 outlier x10 -> mediana x2.0, non media
    tanti = [_done_with(4, 2, i) for i in range(1, 6)] + [_done_with(20, 2, 9)]
    assert domain.calibration_factor(tanti) == pytest.approx(2.0)
    # clamp: tutti x10 -> 3.0
    alti = [_done_with(20, 2, i) for i in range(1, 7)]
    assert domain.calibration_factor(alti) == pytest.approx(3.0)
    # stime/actual a 0 ignorati
    misti = [_done_with(0, 0, i) for i in range(1, 7)]
    assert domain.calibration_factor(misti) is None


def test_calibrated_estimate_mai_sotto_uno():
    t = make_todo("X", todo_id=1, stima_pomo=2)
    assert domain.calibrated_estimate(t, None) == (2, False)
    assert domain.calibrated_estimate(t, 1.5) == (3, True)
    assert domain.calibrated_estimate(t, 99.0) == (6, True)  # clamp 3.0
    assert domain.calibrated_estimate(t, "xx") == (2, False)
    t0 = make_todo("Y", todo_id=2)  # senza stima -> base 1
    assert domain.calibrated_estimate(t0, 2.0) == (2, True)


def test_arch_purezza_no_import_app_ui():
    """Guardrail god-class: domain/plan/models mai verso app/screens/T()."""
    import pathlib

    for mod in ("domain", "plan", "models"):
        src = pathlib.Path(f"src/{mod}.py").read_text(encoding="utf-8")
        assert "from src.app" not in src and "import src.app" not in src
        assert "from src.screens" not in src and "import src.screens" not in src
        assert "from src.lang import" not in src or mod == "models"
