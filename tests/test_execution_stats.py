"""Statistiche, confidence e calibration M2 dalla history.

Statistiche robuste (mediana/p90, mai media semplice); confidence LOW<10,
MEDIUM 10-29, HIGH>=30 (informativa); factor con stessa policy anti-rumore
della calibrazione su todos (min 5, mediana, clamp); predicted mai riscrive
la stima utente.
"""

import src.domain as domain
import src.models as models
from src.planner.calibration import calibration_summary


def _exec(i, actual, estimate=2, planned=60, completed=True):
    return models.TaskExecution(
        i,
        "2026-09-10 09:00",
        f"2026-09-10 {10 + (i % 8):02d}:00",
        planned,
        actual,
        estimate,
        completed,
    )


def test_stats_zero_e_una():
    assert domain.execution_stats([]) == {
        "count": 0,
        "median": None,
        "min": None,
        "max": None,
        "p90": None,
        "variance": None,
    }
    s = domain.execution_stats([_exec(1, 70)])
    assert (s["count"], s["median"], s["min"], s["max"], s["p90"]) == (
        1,
        70.0,
        70,
        70,
        70,
    )
    assert s["variance"] == 0.0


def test_stats_poche_e_outlier():
    execs = [_exec(i, a) for i, a in enumerate([60, 62, 58, 61, 600], start=1)]
    s = domain.execution_stats(execs)
    assert s["count"] == 5
    assert s["median"] == 61.0  # mediana resiste all'outlier 600
    assert (s["min"], s["max"], s["p90"]) == (58, 600, 600)


def test_stats_ignora_non_valide():
    execs = [
        _exec(1, 0),  # senza actual
        _exec(2, 70, estimate=0),  # senza stima
        _exec(3, 80, completed=False),  # non completata
        "xx",
        _exec(4, 70),
    ]
    assert domain.execution_stats(execs)["count"] == 1


def test_confidence_soglie():
    assert [domain.execution_confidence(n) for n in (0, 1, 9)] == ["LOW"] * 3
    assert [domain.execution_confidence(n) for n in (10, 29)] == ["MEDIUM"] * 2
    assert [domain.execution_confidence(n) for n in (30, 100)] == ["HIGH"] * 2
    assert domain.execution_confidence("xx") == "LOW"


def test_calibration_no_dati_e_pochi():
    assert domain.execution_calibration_factor([]) is None
    assert domain.execution_calibration_factor([_exec(1, 70)]) is None
    assert domain.execution_calibration_factor([_exec(i, 70) for i in range(4)]) is None


def test_calibration_coerente_e_clamp():
    execs = [_exec(i, 120, estimate=2) for i in range(1, 6)]  # ratio 2.0
    assert domain.execution_calibration_factor(execs) == 2.0
    huge = [_exec(i, 10000, estimate=1) for i in range(1, 6)]
    assert domain.execution_calibration_factor(huge) == 3.0


def test_predicted_fallback_e_rispetto_stima():
    assert domain.predicted_minutes(60, None) == 60
    assert domain.predicted_minutes(60, 1.5) == 90
    assert domain.predicted_minutes(0, 2.0) == 0
    assert domain.predicted_minutes(60, "xx") == 60


def test_equivalenza_history_vs_todos():
    # stessi dati via executions e via todos -> stesso factor
    from tests.conftest import make_todo

    todos = []
    for i in range(1, 6):
        t = make_todo(f"T{i}", todo_id=i, stima_pomo=2)
        t.done = True
        t.actual_pomo = 4
        todos.append(t)
    execs = [_exec(i, 120, estimate=2) for i in range(1, 6)]
    assert (
        domain.calibration_factor(todos)
        == domain.execution_calibration_factor(execs)
        == 2.0
    )


def test_summary_derivato_on_demand():
    execs = [_exec(i, 90, estimate=2) for i in range(1, 11)]
    s = calibration_summary(execs)
    assert s == {
        "factor": 1.5,
        "sample_count": 10,
        "confidence": "MEDIUM",
        "last_observation_at": "2026-09-10 17:00",
    }
    empty = calibration_summary([])
    assert empty == {
        "factor": None,
        "sample_count": 0,
        "confidence": "LOW",
        "last_observation_at": "",
    }
