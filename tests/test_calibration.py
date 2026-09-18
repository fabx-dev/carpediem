"""Test boundary di calibrazione (Fase 6: adapter sottile, senza Textual)."""

from src.domain import calibrated_estimate, calibration_factor
from src.planner import calibration, capacity
from src.planner.models import ExecutionFeedback
from tests.conftest import make_todo


def _fb(tid, est, act, completed=True, sessions=0):
    return ExecutionFeedback(
        tid, est, est * 30, None, None, sessions, act, 0, completed
    )


def test_estimate_delega_a_domain():
    bases = [0, 1, 2, 3, 7, "x", None, -2]
    factors = [None, 0.1, 0.5, 1.0, 2.0, 3.0, 99.0, "xx", -1]
    for b in bases:
        t = make_todo("T", todo_id=1, stima_pomo=b)
        for f in factors:
            assert capacity.estimate(t, f) == calibrated_estimate(t, f)[0]


def test_observe_coppie_solo_completati_con_dati():
    assert calibration.observe(_fb(1, 2, 4)) == (2, 4)
    assert calibration.observe(_fb(1, 2, 4, completed=False)) is None
    assert calibration.observe(_fb(1, 0, 4)) is None
    assert calibration.observe(_fb(1, 2, 0)) is None
    # Le sessions non alimentano la calibrazione: conta il dichiarato.
    assert calibration.observe(_fb(1, 2, 0, sessions=5)) is None


def test_observe_all_ordine_e_filtro():
    fbs = [_fb(1, 2, 4), _fb(2, 1, 1), _fb(3, 2, 0), "xx", None]
    assert calibration.observe_all(fbs) == [(2, 4), (1, 1)]
    assert calibration.observe_all(None) == []


def test_factor_for_delega_a_domain():
    todos = [make_todo(f"T{i}", todo_id=i) for i in range(3)]
    assert calibration.factor_for(todos) == calibration_factor(todos) is None
    assert calibration.factor_for([]) is None


def test_equivalenza_feedback_todos():
    # Stessi dati storici, due vie: observations dai feedback vs todos diretti.
    pairs = [(2, 4), (2, 4), (1, 2), (3, 6), (1, 3)]
    fbs = [_fb(i + 1, e, a) for i, (e, a) in enumerate(pairs)]
    assert calibration.observe_all(fbs) == pairs
    via_feedback = calibration.factor_for(
        [
            make_todo(f"O{i}", todo_id=100 + i, stima_pomo=e)
            for i, (e, a) in enumerate(pairs)
        ]
    )
    assert via_feedback is None  # non completati: nessun campione
    done = []
    for i, (e, a) in enumerate(pairs):
        t = make_todo(f"D{i}", todo_id=i, stima_pomo=e, actual_pomo=a)
        t.done = True
        t.completed_at = "2026-09-09 10:00"
        done.append(t)
    assert calibration.factor_for(done) == calibration_factor(done) == 2.0


def test_edge_pochi_dati_outlier_determinismo():
    one = [make_todo("A", todo_id=1, stima_pomo=2, actual_pomo=4)]
    one[0].done = True
    assert calibration.factor_for(one) is None  # un solo dato: neutro
    wild = []
    for i in range(5):
        t = make_todo(f"W{i}", todo_id=i, stima_pomo=1, actual_pomo=100)
        t.done = True
        wild.append(t)
    assert calibration.factor_for(wild) == 3.0  # outlier clampato
    assert calibration.factor_for(wild) == calibration.factor_for(list(wild))
