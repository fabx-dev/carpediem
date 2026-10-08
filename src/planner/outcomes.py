"""Outcome di scheduling a tre stati (puro, niente I/O/UI/i18n).

Un task del piano di oggi puo' non avere uno slot per due ragioni diverse,
e la UI deve distinguerle invece di mostrare un unico "senza orario":

- OUT_SCHEDULED: ha uno slot concreto (membership in sched.scheduled).
- OUT_ELIGIBLE (non inserito): entrerebbe da solo ma ha perso la gara per
  gli slot (blocked_by == tasks, prova costruttiva via rivals in diagnose).
- OUT_OUTSIDE (non entra oggi): nessun intervallo futuro compatibile con
  la durata atomica (duration/deadline/busy/window), dopo clip/fuse/busy.

capacity/user_skip non arrivano mai qui: sono cut/skipped decisi prima
dello scheduler. classify() e' totale sui kind temporali e non solleva
mai: kind ignoto -> OUT_OUTSIDE onesto (meglio che sparire; la causa resta
quella di phrase_for/fallback). La UI non deduce mai il perche': legge
blocked_by/detail da PlanAlternative e raggruppa per questo outcome.
"""

from src.planner.models import (
    BLOCKED_BUSY,
    BLOCKED_CAPACITY,
    BLOCKED_DEADLINE,
    BLOCKED_DURATION,
    BLOCKED_TASKS,
    BLOCKED_USER_SKIP,
    BLOCKED_WINDOW,
)

OUT_SCHEDULED = "scheduled"
OUT_ELIGIBLE = "unsched_eligible"
OUT_OUTSIDE = "outside_availability"

OUTCOMES = frozenset({OUT_SCHEDULED, OUT_ELIGIBLE, OUT_OUTSIDE})

# Competizione osservata (unico kind competitivo di diagnose).
_ELIGIBLE_KINDS = frozenset({BLOCKED_TASKS})

# Impossibilita' strutturale nella disponibilita' residua.
_OUTSIDE_KINDS = frozenset(
    {BLOCKED_DURATION, BLOCKED_DEADLINE, BLOCKED_BUSY, BLOCKED_WINDOW}
)

# Fuori-scope scheduler (mai schedulati per merito/scelta, non per tempo).
_NOSCHED_KINDS = frozenset({BLOCKED_CAPACITY, BLOCKED_USER_SKIP})


def classify(blocked_by) -> str:
    """blocked_by -> OUT_ELIGIBLE | OUT_OUTSIDE (puro, totale).

    tasks (gara persa, slot esistente rubato) -> ELIGIBLE; duration/
    deadline/busy/window (nessun gap compatibile) -> OUTSIDE; capacity/
    user_skip o kind ignoto/vuoto -> OUTSIDE (visibile con motivo, mai
    perso; la causa testuale resta quella di phrase_for).
    """
    try:
        kind = str(blocked_by or "")
    except Exception:
        return OUT_OUTSIDE
    if kind in _ELIGIBLE_KINDS:
        return OUT_ELIGIBLE
    if kind in _OUTSIDE_KINDS or kind in _NOSCHED_KINDS:
        return OUT_OUTSIDE
    return OUT_OUTSIDE


def outcome_of(*, scheduled: bool, blocked_by=None) -> str:
    """Outcome completo di una voce: slot vince su tutto (puro, totale)."""
    if scheduled:
        return OUT_SCHEDULED
    return classify(blocked_by)
