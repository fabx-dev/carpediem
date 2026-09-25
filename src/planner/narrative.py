"""Spiegazioni naturali deterministiche delle decisioni (M3 UX, puro).

Pipeline: Planner -> DayPlan -> PlanningDecision -> explain_decision() ->
chiave i18n. Nessuna AI, rete, scoring: solo selezione di un template
in base a decisione + reasons + evidence gia' prodotte dal planner.

Priorita' di selezione (documentata, deterministica): la decisione viene
per prima; dentro SCHEDULED contano i flag in ordine overdue, due-today,
priorita' alta, poi fallback. NOT_SCHEDULED/DEFERRED/CONSTRAINED hanno un
template ciascuna: la decisione e' gia' distintiva.

Ritorna (chiave_i18n, params) per T(chiave, **params) nella view, o None
con reasons vuote (il chiamante non deve inventare testo). Mai importare
src.lang/src.screens/src.app (guardrail purezza): solo chiavi, mai testo.
"""

from src.planner import decisions as _dec
from src.planner.explain import (
    CUT,
    DUE_TODAY,
    OVERDUE,
    PRIO,
    SKIPPED,
)

STORY_SCHED_OVERDUE = "why_story_sched_overdue"
STORY_SCHED_DUE_TODAY = "why_story_sched_due_today"
STORY_SCHED_PRIO = "why_story_sched_prio"
STORY_SCHED = "why_story_sched"
STORY_CUT = "why_story_cut"
STORY_DEFERRED = "why_story_deferred"
STORY_CONSTRAINED = "why_story_constrained"

_ALL_KEYS = frozenset(
    {
        STORY_SCHED_OVERDUE,
        STORY_SCHED_DUE_TODAY,
        STORY_SCHED_PRIO,
        STORY_SCHED,
        STORY_CUT,
        STORY_DEFERRED,
        STORY_CONSTRAINED,
    }
)


def story_keys() -> frozenset:
    """Chiavi i18n dei template narrativi (per test di parita' it/en)."""
    return _ALL_KEYS


def explain_decision(decision: _dec.PlanningDecision) -> tuple[str, dict] | None:
    """Seleziona il template narrativo per una decisione (puro, totale).

    Solo lettura di decision/reasons/evidence: non ricalcola merito,
    capacita' o scheduling. A parita' di input, stesso output.
    """
    reasons = list(decision.reasons or ())
    if not reasons:
        return None
    keys = {k for k, _p in reasons}
    ev = decision.evidence or {}
    kind = decision.decision
    if kind == _dec.SCHEDULED:
        if OVERDUE in keys or bool(ev.get("overdue")):
            return (STORY_SCHED_OVERDUE, {})
        if DUE_TODAY in keys:
            return (STORY_SCHED_DUE_TODAY, {})
        if PRIO in keys or str(ev.get("priority") or "") == "alta":
            return (STORY_SCHED_PRIO, {})
        return (STORY_SCHED, {})
    if kind == _dec.NOT_SCHEDULED:
        return (STORY_CUT, {})
    if kind == _dec.DEFERRED:
        return (STORY_DEFERRED, {})
    if kind == _dec.CONSTRAINED:
        return (STORY_CONSTRAINED, {})
    # Decisione ignota: CUT/SKIPPED decidono da soli come in primary_reason.
    if CUT in keys:
        return (STORY_CUT, {})
    if SKIPPED in keys:
        return (STORY_DEFERRED, {})
    return None
