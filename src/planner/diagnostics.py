"""Diagnostica del planner (Phase 6, pura, niente I/O/UI/i18n).

diagnose() osserva il risultato esistente e spiega i non-collocati:
NON ridecide, NON rischedula, NON ottimizza. Riusa solo scheduler.schedule
esistente su voci singole (probe deterministiche, economiche).

Semantica vincolante (piano revisionato): `blocked_by` = PRIMO blocco
deterministico osservato nell'ordine duration → deadline → busy → window,
MAI "unica causa possibile". Invariante: una probe non produce mai un esito
diverso dallo scheduler reale (divergenza = difetto qui, non dello
scheduler, unica autorita' decisionale).
"""

from datetime import datetime, timedelta

from src.planner.capacity import pomo_minutes
from src.planner.decisions import CONSTRAINED, DEFERRED, NOT_SCHEDULED, SCHEDULED
from src.planner.models import (
    BLOCKED_BUSY,
    BLOCKED_CAPACITY,
    BLOCKED_DEADLINE,
    BLOCKED_DURATION,
    BLOCKED_USER_SKIP,
    BLOCKED_WINDOW,
    DIAG_CONSTRAINED,
    DIAG_NO_AVAIL,
    DIAG_OVERFLOW,
    DayPlan,
    PlanAlternative,
    PlanDiagnostic,
    TimeWindow,
)
from src.planner.scheduler import deadlines_for, schedule

# Ordine probe documentato (primo-match deterministico, mai causa unica).
_PROBE_ORDER = (BLOCKED_DURATION, BLOCKED_DEADLINE, BLOCKED_BUSY, BLOCKED_WINDOW)


def _solo(item, day) -> DayPlan:
    """DayPlan da una voce sola per le probe (capacita' irrilevante qui)."""
    return DayPlan(day=day, planned=(item,))


def _full_day(day) -> tuple:
    start = datetime(day.year, day.month, day.day)
    return (TimeWindow(start, start + timedelta(days=1)),)


def _fits(item, day, avail, busy, deadlines) -> bool:
    """La voce entrerebbe da sola in queste condizioni (osservazione)."""
    return bool(schedule(_solo(item, day), avail, busy, deadlines).scheduled)


def _probe_unscheduled(item, day, avail, busy, deadlines) -> PlanAlternative:
    """Primo blocco osservato per una voce unscheduled (ordine documentato).

    Coerenza garantita per costruzione: ogni probe riusa schedule() reale,
    quindi nessun esito inventato. decision rispecchia refine_with_schedule
    (mandatory senza slot -> CONSTRAINED).
    """
    decision = CONSTRAINED if item.mandatory else SCHEDULED
    needed = pomo_minutes(item.estimate_pomo)
    if not _fits(item, day, _full_day(day), (), None):
        return PlanAlternative(
            item.todo_id, decision, BLOCKED_DURATION, {"needed_min": needed}
        )
    own = (deadlines or {}).get(item.todo_id, ("", ""))
    if own != ("", "") and _fits(item, day, avail, busy, None):
        return PlanAlternative(
            item.todo_id,
            decision,
            BLOCKED_DEADLINE,
            {"needed_min": needed, "deadline": own[1]},
        )
    # Solo se esiste busy da togliere: a busy vuoto la probe sarebbe vacua.
    if (busy or ()) and _fits(
        item, day, avail, (), {item.todo_id: own} if own != ("", "") else None
    ):
        return PlanAlternative(
            item.todo_id, decision, BLOCKED_BUSY, {"needed_min": needed}
        )
    return PlanAlternative(
        item.todo_id, decision, BLOCKED_WINDOW, {"needed_min": needed}
    )


def diagnose(result) -> tuple[tuple, tuple]:
    """(alternatives, diagnostics) da un PlanningResult (puro, totale).

    Cut -> capacity, skipped -> user_skip, unscheduled -> probe; scheduled ->
    niente. Diagnostica di piano solo se vera (overflow, mandatory senza
    slot, availability vuota con planned). Mai eccezioni verso il chiamante.
    """
    try:
        plan = result.plan
        sched = result.scheduled
    except AttributeError:
        return (), ()
    try:
        tasks = result.request.tasks
    except AttributeError:
        tasks = ()
    try:
        deadlines = deadlines_for(tasks)
    except Exception:
        deadlines = {}
    alternatives: list = []
    try:
        for item in plan.cut:
            alternatives.append(
                PlanAlternative(
                    item.todo_id,
                    NOT_SCHEDULED,
                    BLOCKED_CAPACITY,
                    {"estimate_pomo": item.estimate_pomo},
                )
            )
        for item in plan.skipped:
            alternatives.append(
                PlanAlternative(item.todo_id, DEFERRED, BLOCKED_USER_SKIP, {})
            )
        # Senza tentativo di scheduling (scheduled None) non c'e' blocco
        # osservato: le planned non generano alternative (correzione P6-2:
        # l'assenza di scheduling e' una fase, non un difetto).
        if sched is None:
            unscheduled: list = []
            avail: tuple = ()
            busy: tuple = ()
        else:
            unscheduled = [it for it in sched.unscheduled]
            avail, busy = sched.availability, sched.busy
        for item in unscheduled:
            alternatives.append(
                _probe_unscheduled(item, plan.day, avail, busy, deadlines)
            )
    except Exception:
        return tuple(alternatives), ()
    diagnostics: list = []
    try:
        if plan.planned_pomo > plan.capacity_pomo:
            diagnostics.append(
                PlanDiagnostic(
                    DIAG_OVERFLOW,
                    {
                        "planned_pomo": plan.planned_pomo,
                        "capacity_pomo": plan.capacity_pomo,
                        "over_pomo": plan.planned_pomo - plan.capacity_pomo,
                    },
                )
            )
        constrained_ids = tuple(it.todo_id for it in unscheduled if it.mandatory)
        if constrained_ids:
            diagnostics.append(
                PlanDiagnostic(
                    DIAG_CONSTRAINED,
                    {"count": len(constrained_ids), "todo_ids": constrained_ids},
                )
            )
        if sched is not None and not sched.availability and [it for it in plan.planned]:
            diagnostics.append(
                PlanDiagnostic(DIAG_NO_AVAIL, {"planned_count": len(plan.planned)})
            )
    except Exception:
        pass
    return tuple(alternatives), tuple(diagnostics)
