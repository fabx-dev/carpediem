"""Decisioni di pianificazione esplicite (M3, puro, niente I/O/UI/i18n).

PlanningDecision rende esplicito cio' che prima era implicito nelle tre
tuple di DayPlan: NON e' un secondo motore decisionale. Pipeline:

    Task -> Planner -> DayPlan -> Scheduler -> PlanningDecision -> UI

- decide() e' una lettura/proiezione del DayPlan: planned -> SCHEDULED,
  cut -> NOT_SCHEDULED, skipped -> DEFERRED. Non riesegue scoring, non
  tocca pesi, non ricalcola il planner.
- evidence contiene solo dati strutturati (mai testo UI); i motivi
  (chiave_i18n, params) restano quelli di explain, invariati.
- confidence e' opzionale (None di default) e descrive solo la qualita'
  della conoscenza sulla durata: valorizzata con i livelli M2 solo quando
  la decisione usa una stima calibrata (motivo plan_calibrated) e il
  chiamante passa sample_count. Non e' la "certezza" della decisione e
  decisions.py non calcola mai sample_count da solo (separazione:
  UI/service misurano, qui si trasforma).
- refine_with_schedule() distingue decisione da schedulazione: restituisce
  NUOVE decisioni (mai mutazione in-place, frozen) aggiungendo gli slot;
  solo mandatory-senza-slot diventa CONSTRAINED. Mai overlap, mai orari
  inventati, mai vincoli rilassati.
"""

from dataclasses import dataclass, replace

from src.domain import execution_confidence
from src.planner.capacity import POMO_HOURS
from src.planner.explain import CALIBRATED, CUT, SKIPPED
from src.planner.models import DayPlan, ScheduledDayPlan

SCHEDULED = "scheduled"
NOT_SCHEDULED = "not_scheduled"
DEFERRED = "deferred"
CONSTRAINED = "constrained"

DECISIONS = frozenset({SCHEDULED, NOT_SCHEDULED, DEFERRED, CONSTRAINED})

# Motivi che decidono da soli la spiegazione principale (flag di esclusione).
_PRIMARY_FLAGS = frozenset({CUT, SKIPPED})


@dataclass(frozen=True)
class PlanningDecision:
    """Una decisione per task valutato (evidence trattata come immutabile)."""

    todo_id: int
    decision: str
    reasons: tuple = ()
    evidence: dict | None = None
    confidence: str | None = None


def _evidence(item, todo, day_s: str, rank: int, rank_of: int, plan: DayPlan) -> dict:
    try:
        due = str(getattr(todo, "due", "") or "")
    except Exception:
        due = ""
    try:
        priority = str(getattr(getattr(todo, "priority", ""), "value", "") or "")
    except Exception:
        priority = ""
    return {
        "due": due,
        "priority": priority,
        "overdue": bool(due and due[:10] < day_s),
        "score": item.score,
        "rank": rank,
        "rank_of": rank_of,
        "estimate_pomo": item.estimate_pomo,
        "estimate_minutes": int(item.estimate_pomo * POMO_HOURS * 60),
        "mandatory": bool(item.mandatory),
        "capacity_pomo": plan.capacity_pomo,
        "planned_pomo": plan.planned_pomo,
    }


def _confidence(reasons, sample_count) -> str | None:
    if sample_count is None:
        return None
    if not any(k == CALIBRATED for k, _p in reasons):
        return None
    try:
        return execution_confidence(int(sample_count))
    except (ValueError, TypeError):
        return None


def decide(plan: DayPlan, todos, *, sample_count=None) -> tuple:
    """Proietta un DayPlan in decisioni, una per voce valutata, in ordine.

    sample_count e' misurato dal chiamante (es. domain.calibration_samples):
    qui diventa confidence solo con stima calibrata, altrimenti None.
    I non eleggibili non compaiono nel piano e non diventano decisioni.
    """
    try:
        by_id = {t.id: t for t in todos or ()}
    except TypeError:
        by_id = {}
    day_s = plan.day.isoformat()
    items = plan.items
    rank_of = len(items)
    section_of = {}
    for section, decision in (
        (plan.planned, SCHEDULED),
        (plan.cut, NOT_SCHEDULED),
        (plan.skipped, DEFERRED),
    ):
        for item in section:
            section_of[id(item)] = decision
    out = []
    for rank, item in enumerate(items, start=1):
        out.append(
            PlanningDecision(
                item.todo_id,
                section_of.get(id(item), SCHEDULED),
                tuple(item.reasons),
                _evidence(item, by_id.get(item.todo_id), day_s, rank, rank_of, plan),
                _confidence(item.reasons, sample_count),
            )
        )
    return tuple(out)


def refine_with_schedule(decisions, scheduled: ScheduledDayPlan | None) -> tuple:
    """Arricchisce le decisioni con l'esito dello scheduler (puro, no in-place).

    SCHEDULED con slot resta SCHEDULED (+ slot_start/slot_end in evidence);
    mandatory senza slot diventa CONSTRAINED; non-mandatory senza slot resta
    SCHEDULED (la timeline e' una fase distinta dalla decisione). Cut/skipped
    (NOT_SCHEDULED/DEFERRED) passano invariati: lo scheduler non li colloca.
    """
    if scheduled is None:
        return tuple(decisions)
    slots = {s.item.todo_id: s for s in scheduled.scheduled}
    unscheduled_ids = {it.todo_id for it in scheduled.unscheduled}
    out = []
    for d in decisions:
        if d.decision != SCHEDULED:
            out.append(d)
            continue
        if d.todo_id in slots:
            slot = slots[d.todo_id]
            evidence = dict(d.evidence or {})
            evidence["slot_start"] = slot.start.strftime("%Y-%m-%d %H:%M")
            evidence["slot_end"] = slot.end.strftime("%Y-%m-%d %H:%M")
            out.append(replace(d, evidence=evidence))
        elif (d.evidence or {}).get("mandatory") and d.todo_id in unscheduled_ids:
            out.append(replace(d, decision=CONSTRAINED))
        else:
            out.append(d)
    return tuple(out)


def primary_reason(decision: PlanningDecision):
    """Motivo principale: flag di esclusione (CUT/SKIPPED), poi primo motivo.

    None se nessun motivo: il chiamante non deve inventare testo.
    """
    reasons = list(decision.reasons or ())
    for key, params in reasons:
        if key in _PRIMARY_FLAGS:
            return (key, params)
    return reasons[0] if reasons else None
