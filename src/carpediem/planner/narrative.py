"""Spiegazioni naturali deterministiche delle decisioni (M3 UX, puro).

Pipeline: Planner -> DayPlan -> PlanningDecision -> explain_decision() ->
chiave i18n. Nessuna AI, rete, scoring: solo selezione di un template
in base a decisione + reasons + evidence gia' prodotte dal planner.

Priorita' di selezione (documentata, deterministica): la decisione viene
per prima; dentro SCHEDULED contano i flag in ordine overdue, due-today
(con slack misurato -> variante tight F5), priorita' alta, domani, stale,
pianificato, poi fallback. La prio resta davanti ai segnali temporali
deboli: solo i task oggi in fallback cambiano frase. NOT_SCHEDULED
distingue overflow (obbligatori oltre capacita') dal taglio in
graduatoria; DEFERRED/CONSTRAINED hanno un template ciascuna.

Ritorna PhraseRef per T(ref.key, **ref.params) nella view, o None
con reasons vuote (il chiamante non deve inventare testo). Mai importare
src.lang/src.screens/src.app (guardrail purezza): solo chiavi, mai testo.
"""

from carpediem.planner import decisions as _dec
from carpediem.planner.explain import (
    CUT,
    DUE_TODAY,
    DUE_TOMORROW,
    OVERDUE,
    PRIO,
    SKIPPED,
    STALE,
)
from carpediem.planner.phrases import PhraseRef

STORY_SCHED_OVERDUE = "why_story_sched_overdue"
STORY_SCHED_DUE_TODAY = "why_story_sched_due_today"
STORY_SCHED_TIGHT = "why_story_sched_tight"
STORY_SCHED_PRIO = "why_story_sched_prio"
STORY_SCHED_TOMORROW = "why_story_sched_tomorrow"
STORY_SCHED_STALE = "why_story_sched_stale"
STORY_SCHED = "why_story_sched"
STORY_PROP_OVERDUE = "why_story_prop_overdue"
STORY_PROP_DUE_TODAY = "why_story_prop_due_today"
STORY_PROP_TIGHT = "why_story_prop_tight"
STORY_PROP_PRIO = "why_story_prop_prio"
STORY_PROP_TOMORROW = "why_story_prop_tomorrow"
STORY_PROP_STALE = "why_story_prop_stale"
STORY_PROP = "why_story_prop_fallback"
STORY_CUT = "why_story_cut"
STORY_CUT_OVERFLOW = "why_story_cut_overflow"
STORY_DEFERRED = "why_story_deferred"
STORY_CONSTRAINED = "why_story_constrained"

_ALL_KEYS = frozenset(
    {
        STORY_SCHED_OVERDUE,
        STORY_SCHED_DUE_TODAY,
        STORY_SCHED_TIGHT,
        STORY_SCHED_PRIO,
        STORY_SCHED_TOMORROW,
        STORY_SCHED_STALE,
        STORY_SCHED,
        STORY_PROP_OVERDUE,
        STORY_PROP_DUE_TODAY,
        STORY_PROP_TIGHT,
        STORY_PROP_PRIO,
        STORY_PROP_TOMORROW,
        STORY_PROP_STALE,
        STORY_PROP,
        STORY_CUT,
        STORY_CUT_OVERFLOW,
        STORY_DEFERRED,
        STORY_CONSTRAINED,
    }
)


def story_keys() -> frozenset:
    """Chiavi i18n dei template narrativi (per test di parita' it/en)."""
    return _ALL_KEYS


def _sched_variant(
    reasons: list,
    ev: dict,
    overdue: str,
    due_today: str,
    tight: str,
    prio: str,
    tomorrow: str,
    stale: str,
    fallback: str,
) -> PhraseRef:
    """Variante SCHEDULED condivisa da pianificato e proposto (pura).

    Niente ramo planned: l'appartenenza al piano la dicono gia' etichetta
    ("Nel piano di oggi" / noslot "Confermato...") e motivo principale
    ("gia' in piano") — una story dedicata triplicherebbe il messaggio.
    Tight (F5): scadenza odierna con slack misurato (evidence slack_min da
    decide con now) — piu' informativa della generica due-today perche'
    dice che l'urgenza temporale ha guidato anche l'ordine di scheduling.
    """
    keys = {k for k, _p in reasons}
    if OVERDUE in keys or bool(ev.get("overdue")):
        return PhraseRef(overdue, {}, "story")
    if DUE_TODAY in keys:
        if ev.get("slack_min") is not None:
            return PhraseRef(tight, {}, "story")
        return PhraseRef(due_today, {}, "story")
    if PRIO in keys or str(ev.get("priority") or "") == "alta":
        return PhraseRef(prio, {}, "story")
    if DUE_TOMORROW in keys:
        return PhraseRef(tomorrow, {}, "story")
    if STALE in keys:
        try:
            params = dict(reasons).get(STALE, {}) or {}
            n = int(params.get("n", 0))
        except (ValueError, TypeError, AttributeError):
            n = 0
        return PhraseRef(stale, {"n": n}, "story")
    return PhraseRef(fallback, {}, "story")


def explain_decision(decision: _dec.PlanningDecision) -> PhraseRef | None:
    """Seleziona il template narrativo per una decisione (puro, totale).

    Solo lettura di decision/reasons/evidence: non ricalcola merito,
    capacita' o scheduling. A parita' di input, stesso output.
    """
    reasons = list(decision.reasons or ())
    if not reasons:
        return None
    ev = decision.evidence or {}
    kind = decision.decision
    if kind == _dec.SCHEDULED:
        return _sched_variant(
            reasons,
            ev,
            STORY_SCHED_OVERDUE,
            STORY_SCHED_DUE_TODAY,
            STORY_SCHED_TIGHT,
            STORY_SCHED_PRIO,
            STORY_SCHED_TOMORROW,
            STORY_SCHED_STALE,
            STORY_SCHED,
        )
    if kind == _dec.NOT_SCHEDULED:
        try:
            overflow = float(ev.get("planned_pomo", 0)) > float(
                ev.get("capacity_pomo", 0)
            )
        except (ValueError, TypeError):
            overflow = False
        return PhraseRef(STORY_CUT_OVERFLOW if overflow else STORY_CUT, {}, "story")
    if kind == _dec.DEFERRED:
        return PhraseRef(STORY_DEFERRED, {}, "story")
    if kind == _dec.CONSTRAINED:
        return PhraseRef(STORY_CONSTRAINED, {}, "story")
    # Decisione ignota: CUT/SKIPPED decidono da soli come in primary_reason.
    keys = {k for k, _p in reasons}
    if CUT in keys:
        return PhraseRef(STORY_CUT, {}, "story")
    if SKIPPED in keys:
        return PhraseRef(STORY_DEFERRED, {}, "story")
    return None


def explain_proposed(decision: _dec.PlanningDecision) -> PhraseRef | None:
    """Story per SCHEDULED non confermato in piano (pura, totale).

    Stessa selezione di explain_decision ma con wording "proposto", mai
    "pianificato". Solo per decisioni SCHEDULED con motivi; altrimenti None
    (il chiamante usa explain_decision o niente).
    """
    reasons = list(decision.reasons or ())
    if not reasons or decision.decision != _dec.SCHEDULED:
        return None
    return _sched_variant(
        reasons,
        decision.evidence or {},
        STORY_PROP_OVERDUE,
        STORY_PROP_DUE_TODAY,
        STORY_PROP_TIGHT,
        STORY_PROP_PRIO,
        STORY_PROP_TOMORROW,
        STORY_PROP_STALE,
        STORY_PROP,
    )
