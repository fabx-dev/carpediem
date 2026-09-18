"""Scheduler temporale deterministico (puro, niente I/O/UI/i18n).

Colloca le voci planned di un DayPlan in slot [start, end) dentro la
disponibilita' esplicita, evitando i busy (hard constraint). Greedy
first-fit nell'ordine del Planner: niente ottimizzazione, niente secondo
scoring, niente ricalcolo delle stime (usa PlanItem.estimate_pomo).

Cut e skipped non si schedulano (gia' decisi dal Planner); i planned senza
slot restano unscheduled (strutturale, senza reason nuova). Mandatory senza
slot = unscheduled: mai overlap, mai ore inventate, mai durate modificate.
"""

from datetime import datetime, timedelta

from src.planner.capacity import POMO_HOURS
from src.planner.models import PlanItem, ScheduledDayPlan, ScheduledItem, TimeWindow


def _day_bounds(day) -> tuple:
    start = datetime(day.year, day.month, day.day)
    return start, start + timedelta(days=1)


def _clip(window: TimeWindow, lo: datetime, hi: datetime):
    """Finestra valida clippata al giorno, o None se vuota/fuori/invalida."""
    try:
        start, end = window.start, window.end
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return None
        start, end = max(start, lo), min(end, hi)
    except TypeError:
        return None
    return TimeWindow(start, end) if start < end else None


def _normalize(windows, lo: datetime, hi: datetime) -> list:
    """Finestre valide, clippate al giorno, ordinate per inizio."""
    out = []
    for w in windows or ():
        if isinstance(w, TimeWindow):
            c = _clip(w, lo, hi)
            if c is not None:
                out.append(c)
    out.sort(key=lambda w: (w.start, w.end))
    return out


def _merge(windows: list) -> list:
    """Fonde finestre sovrapposte o adiacenti (busy normalizzati)."""
    merged: list = []
    for w in windows:
        if merged and w.start <= merged[-1].end:
            merged[-1] = TimeWindow(merged[-1].start, max(merged[-1].end, w.end))
        else:
            merged.append(w)
    return merged


def _subtract(free: list, busy: list) -> list:
    """Disponibilita' meno busy: intervalli liberi, ordinati, non vuoti."""
    out = []
    for f in free:
        cur = f.start
        for b in busy:
            if b.end <= cur or b.start >= f.end:
                continue
            if b.start > cur:
                out.append(TimeWindow(cur, min(b.start, f.end)))
            cur = max(cur, b.end)
            if cur >= f.end:
                break
        if cur < f.end:
            out.append(TimeWindow(cur, f.end))
    return out


def _duration(item: PlanItem) -> timedelta:
    return timedelta(hours=POMO_HOURS * max(0, item.estimate_pomo))


def schedule(plan, availability, busy=()) -> ScheduledDayPlan:
    """Colloca plan.planned in availability evitando busy (first-fit)."""
    lo, hi = _day_bounds(plan.day)
    avail = _normalize(availability, lo, hi)
    busy_n = _merge(_normalize(busy, lo, hi))
    free = _subtract(avail, busy_n)
    scheduled: list = []
    unscheduled: list = []
    for item in plan.planned:
        need = _duration(item)
        placed = None
        for i, slot in enumerate(free):
            if slot.start + need <= slot.end:
                placed = ScheduledItem(item, slot.start, slot.start + need)
                if slot.start + need < slot.end:
                    free[i] = TimeWindow(slot.start + need, slot.end)
                else:
                    del free[i]
                break
        if placed is not None:
            scheduled.append(placed)
        else:
            unscheduled.append(item)
    return ScheduledDayPlan(
        plan=plan,
        scheduled=tuple(scheduled),
        unscheduled=tuple(unscheduled),
        availability=tuple(avail),
        busy=tuple(busy_n),
    )
