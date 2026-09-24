"""Boundary di calibrazione del Planner (puro, niente I/O/UI/i18n).

La matematica resta interamente in domain (mediana, min-samples, clamp):
questo modulo espone API coerenti col Planner e deriva observations dagli
ExecutionFeedback, senza duplicare alcun algoritmo e senza cambiare wiring.

Loop: feedback → observations → factor → future estimate. Solo future:
piani/actual/slot passati non vengono mai modificati.
"""

from src.domain import (
    calibration_factor,
    execution_calibration_factor,
    execution_confidence,
    execution_stats,
    last_observation_at,
)
from src.planner.models import ExecutionFeedback


def _as_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError):
        return 0


def observe(feedback: ExecutionFeedback) -> tuple | None:
    """(estimate_pomo, actual_pomo) se il task e' completato con entrambi > 0.

    Fonte actual = dichiarazione utente (actual_pomo), non le sessions:
    la calibrazione storica confronta stima vs dichiarato, come domain.
    """
    estimate, actual = _as_int(feedback.estimate_pomo), _as_int(feedback.actual_pomo)
    if feedback.completed and estimate > 0 and actual > 0:
        return (estimate, actual)
    return None


def observe_all(feedbacks) -> list:
    """Coppie (estimate, actual) osservabili, in ordine di feedback."""
    out = []
    for fb in feedbacks or ():
        if isinstance(fb, ExecutionFeedback):
            obs = observe(fb)
            if obs is not None:
                out.append(obs)
    return out


def factor_for(todos: list) -> float | None:
    """Fattore di calibrazione sui todos (delega a domain, unica fonte)."""
    return calibration_factor(todos)


def calibration_summary(executions) -> dict:
    """Quadro derivato on-demand dalla history (M2): factor, sample_count,
    confidence, last_observation_at. Mai persistito (single source of truth
    = .todo_executions.json); la UI consuma questo, non ricalcola."""
    count = execution_stats(executions)["count"]
    return {
        "factor": execution_calibration_factor(executions),
        "sample_count": count,
        "confidence": execution_confidence(count),
        "last_observation_at": last_observation_at(executions),
    }
