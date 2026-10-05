"""Boundary di calibrazione del Planner (puro, niente I/O/UI/i18n).

La matematica vive in planner.estimation (fonte unica, Phase 5):
questo modulo espone API coerenti col Planner e deriva observations dagli
ExecutionFeedback, senza duplicare alcun algoritmo e senza cambiare wiring.

Loop: feedback → observations → factor → future estimate. Solo future:
piani/actual/slot passati non vengono mai modificati.

Status (Phase 2, D3): observe/observe_all/factor_for sono il boundary verso
il core; calibration_summary e' traslocato in domain (stesso comportamento,
stesso nome) — era pura aggregazione history, mai appartenuto al core.
"""

from src.planner.estimation import calibration_factor
from src.planner.models import ExecutionFeedback


def _as_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError):
        return 0


def observe(feedback: ExecutionFeedback) -> tuple | None:
    """(raw_estimate_pomo, actual_pomo) se il task e' completato con entrambi > 0.

    Fonte actual = dichiarazione utente (actual_pomo), non le sessions:
    la calibrazione storica confronta stima vs dichiarato, come domain.
    Baseline = SEMPRE la raw dichiarata (B1): estimate_pomo puo' essere
    gia' calibrata dal Planner (Planner(factor)->feedback); usarla come
    baseline cancellerebbe il segnale (convergenza a 1.0). Feedback senza
    raw (costruiti a mano/storici) usano estimate_pomo come prima.
    """
    raw = _as_int(getattr(feedback, "raw_estimate_pomo", 0))
    estimate = raw if raw > 0 else _as_int(feedback.estimate_pomo)
    actual = _as_int(feedback.actual_pomo)
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
