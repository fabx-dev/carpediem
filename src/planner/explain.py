"""Reason keys della proposta giornaliera (single source of truth).

Ogni decisione significativa del Planner produce una reason
``(chiave_i18n, params)`` pronta per ``T(chiave, **params)`` nella UI.
I valori sono congelati: catalogo i18n (``src/lang.py``) e screen dipendono
dai letterali, quindi non rinominare senza aggiornare entrambi.

Chi produce cosa:
- scoring: OVERDUE, DUE_TODAY, DUE_TOMORROW, PRIO, STALE, PLANNED, CALIBRATED
- constraints: SKIPPED
- capacity: CUT
"""

OVERDUE = "plan_overdue"
DUE_TODAY = "plan_due_today"
DUE_TOMORROW = "plan_due_tomorrow"
PRIO = "plan_prio"
STALE = "plan_stale"
PLANNED = "plan_planned"
CALIBRATED = "plan_calibrated"
CUT = "plan_cut"
SKIPPED = "plan_skipped"

ALL = frozenset(
    {
        OVERDUE,
        DUE_TODAY,
        DUE_TOMORROW,
        PRIO,
        STALE,
        PLANNED,
        CALIBRATED,
        CUT,
        SKIPPED,
    }
)


def overdue() -> tuple[str, dict]:
    return (OVERDUE, {})


def due_today() -> tuple[str, dict]:
    return (DUE_TODAY, {})


def due_tomorrow() -> tuple[str, dict]:
    return (DUE_TOMORROW, {})


def prio() -> tuple[str, dict]:
    return (PRIO, {})


def stale(n: int) -> tuple[str, dict]:
    return (STALE, {"n": n})


def planned() -> tuple[str, dict]:
    return (PLANNED, {})


def calibrated(factor: float) -> tuple[str, dict]:
    return (CALIBRATED, {"f": f"x{factor:.1f}"})


def cut() -> tuple[str, dict]:
    return (CUT, {})


def skipped() -> tuple[str, dict]:
    return (SKIPPED, {})
