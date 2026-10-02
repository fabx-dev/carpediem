"""Diagnostica del planner (Phase 6, pura, niente I/O/UI/i18n).

diagnose() osserva il risultato esistente e spiega i non-collocati:
NON ridecide, NON rischedula, NON ottimizza. Riusa solo scheduler.schedule
esistente su voci singole (probe deterministiche, economiche).

Semantica vincolante (piano revisionato): `blocked_by` = PRIMO blocco
deterministico osservato nell'ordine duration → tasks → deadline → busy →
window, MAI "unica causa possibile". `tasks` = la voce entrerebbe da sola
ma altri task schedulati occupano il suo slot (gara first-fit persa).
Invariante: una probe non produce mai un esito diverso dallo scheduler
reale (divergenza = difetto qui, non dello scheduler, unica autorita'
decisionale).
"""

from datetime import datetime, timedelta

from src.planner.capacity import pomo_minutes
from src.planner.decisions import CONSTRAINED, DEFERRED, NOT_SCHEDULED, SCHEDULED
from src.planner.models import (
    BLOCKED_BUSY,
    BLOCKED_CAPACITY,
    BLOCKED_DEADLINE,
    BLOCKED_DURATION,
    BLOCKED_TASKS,
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
from src.planner.scheduler import _deadline, deadlines_for, schedule

# Ordine probe documentato (primo-match deterministico, mai causa unica):
# oltre la giornata, gara persa con altri task, scadenza, impegni, finestra.
_PROBE_ORDER = (
    BLOCKED_DURATION,
    BLOCKED_TASKS,
    BLOCKED_DEADLINE,
    BLOCKED_BUSY,
    BLOCKED_WINDOW,
)


def _solo(item, day) -> DayPlan:
    """DayPlan da una voce sola per le probe (capacita' irrilevante qui)."""
    return DayPlan(day=day, planned=(item,))


def _full_day(day) -> tuple:
    start = datetime(day.year, day.month, day.day)
    return (TimeWindow(start, start + timedelta(days=1)),)


def _first_fit(item, day, avail, busy, deadlines):
    """Primo slot libero per la voce sola, o None (osservazione pura)."""
    sched = schedule(_solo(item, day), avail, busy, deadlines)
    return sched.scheduled[0] if sched.scheduled else None


def _fits(item, day, avail, busy, deadlines) -> bool:
    """La voce entrerebbe da sola in queste condizioni (osservazione)."""
    return _first_fit(item, day, avail, busy, deadlines) is not None


def _blocking_titles(events, slot) -> tuple:
    """Titoli degli eventi che intersecano lo slot (nomi per il Blocco)."""
    names = []
    for e in events or ():
        try:
            start, end = e.start, e.end
            title = str(e.title or "").strip()
        except AttributeError:
            continue
        if title and start < slot.end and slot.start < end:
            names.append(title)
    return tuple(names)


def _overlapping_ids(scheduled, slot, exclude) -> tuple:
    """Id schedulati che intersecano lo slot, in ordine di collocazione."""
    out = []
    for s in scheduled or ():
        try:
            tid = s.item.todo_id
        except AttributeError:
            continue
        if tid != exclude and s.start < slot.end and slot.start < s.end:
            out.append(tid)
    return tuple(out)


def _probe_unscheduled(
    item, day, avail, busy, deadlines, events=(), scheduled=()
) -> PlanAlternative:
    """Primo blocco osservato per una voce unscheduled (ordine documentato).

    Coerenza garantita per costruzione: ogni probe riusa schedule() reale,
    quindi nessun esito inventato. decision rispecchia refine_with_schedule
    (mandatory senza slot -> CONSTRAINED). Se la voce entrerebbe da sola ma
    altri task schedulati occupano il suo slot, il blocco sono LORO
    (competizione first-fit persa), non la finestra.
    """
    decision = CONSTRAINED if item.mandatory else SCHEDULED
    needed = pomo_minutes(item.estimate_pomo)
    if not _fits(item, day, _full_day(day), (), None):
        return PlanAlternative(
            item.todo_id, decision, BLOCKED_DURATION, {"needed_min": needed}
        )
    own = (deadlines or {}).get(item.todo_id, ("", ""))
    own_map = {item.todo_id: own} if own != ("", "") else None
    alone = _first_fit(item, day, avail, busy, own_map)
    if alone is not None:
        rivals = _overlapping_ids(scheduled, alone, item.todo_id)
        # Solo con rivali veri: senza nomi la causa tasks sarebbe vacua
        # (si prosegue con l'analisi assoluta: deadline/busy/window).
        if rivals:
            return PlanAlternative(
                item.todo_id, decision, BLOCKED_TASKS, {"task_ids": rivals}
            )
    # Stessa applicabilita' dello scheduler (due-date == day + orario valido):
    # mai due definizioni di "scadenza" (bug: date-only passava il check tupla
    # e produceva "scadenza alle ." vuota). HH:MM sempre presente da limit.
    limit = _deadline(deadlines, item.todo_id, day)
    if limit is not None and _fits(item, day, avail, busy, None):
        return PlanAlternative(
            item.todo_id,
            decision,
            BLOCKED_DEADLINE,
            {"needed_min": needed, "deadline": limit.strftime("%H:%M")},
        )
    # Solo se esiste busy da togliere: a busy vuoto la probe sarebbe vacua.
    # I nomi degli eventi che bloccano davvero lo slot ritrovato (di che
    # impegni si parla, mai generico quando si sa).
    freed = _first_fit(item, day, avail, (), own_map) if (busy or ()) else None
    if freed is not None:
        detail: dict = {"needed_min": needed}
        names = _blocking_titles(events, freed)
        if names:
            detail["busy_titles"] = names
        return PlanAlternative(item.todo_id, decision, BLOCKED_BUSY, detail)
    return PlanAlternative(
        item.todo_id, decision, BLOCKED_WINDOW, {"needed_min": needed}
    )


def diagnose(result, events=()) -> tuple[tuple, tuple]:
    """(alternatives, diagnostics) da un PlanningResult (puro, totale).

    Cut -> capacity, skipped -> user_skip, unscheduled -> probe; scheduled ->
    niente. Diagnostica di piano solo se vera (overflow, mandatory senza
    slot, availability vuota con planned). `events` (FixedEvent, opzionale)
    nomina gli impegni che bloccano davvero; senza, causa busy generica.
    Mai eccezioni verso il chiamante.
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
        placed = sched.scheduled if sched is not None else ()
        for item in unscheduled:
            alternatives.append(
                _probe_unscheduled(
                    item, plan.day, avail, busy, deadlines, events, placed
                )
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
