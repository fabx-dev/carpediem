"""Feedback di esecuzione (puro, niente I/O/UI/i18n/persistenza).

Deriva cosa e' successo davvero alle voci pianificate, riusando i dati
esistenti senza crearne di nuovi:
- estimate: dal PlanItem (unita' astratta + minuti via POMO_HOURS);
- scheduled: dallo ScheduledDayPlan (slot o None);
- actual: dal Todo (sessions = pomodoros, actual_* = dichiarazione utente);
- completed: dallo stato (sessione completata != task completato).

Niente scritture, niente calibration, niente rescheduling: la Fase 5
osserva, la Fase 6 interpretera'.
"""

from src.planner.capacity import POMO_HOURS
from src.planner.models import ExecutionFeedback


def _as_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError):
        return 0


def feedback(scheduled_plan, todos: list) -> tuple:
    """Un ExecutionFeedback per ogni voce planned, nello stesso ordine."""
    by_id = {t.id: t for t in todos if t.id is not None}
    slots = {s.item.todo_id: s for s in scheduled_plan.scheduled}
    out = []
    for plan_item in scheduled_plan.plan.planned:
        todo = by_id.get(plan_item.todo_id)
        slot = slots.get(plan_item.todo_id)
        out.append(
            ExecutionFeedback(
                todo_id=plan_item.todo_id,
                estimate_pomo=plan_item.estimate_pomo,
                estimate_minutes=int(POMO_HOURS * 60 * plan_item.estimate_pomo),
                scheduled_start=slot.start if slot else None,
                scheduled_end=slot.end if slot else None,
                sessions=_as_int(getattr(todo, "pomodoros", 0)),
                actual_pomo=_as_int(getattr(todo, "actual_pomo", 0)),
                actual_minutes=_as_int(getattr(todo, "actual_minutes", 0)),
                completed=bool(todo is not None and todo.state == "completato"),
            )
        )
    return tuple(out)
