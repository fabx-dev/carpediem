"""Scheduler temporale deterministico (puro, niente I/O/UI/i18n).

Colloca le voci planned di un DayPlan in slot [start, end) dentro la
disponibilita' esplicita, evitando i busy (hard constraint). Greedy
first-fit nell'ordine del Planner: niente ottimizzazione, niente secondo
scoring, niente ricalcolo delle stime (usa PlanItem.estimate_pomo).

Deadline (Phase 3): una voce con scadenza OGGI con orario si colloca solo
in slot che finiscono ENTRO la scadenza (bordo inclusivo); altrimenti resta
unscheduled strutturale. Vale solo due-date == plan.day + orario valido:
scaduti (merito, non vincolo), futuri e senza-ora schedulano come prima.
Le scadenze arrivano nella mappa esplicita `deadlines` (None = spente =
comportamento legacy identico).

Cut e skipped non si schedulano (gia' decisi dal Planner); i planned senza
slot restano unscheduled (strutturale, senza reason nuova). Mandatory senza
slot = unscheduled: mai overlap, mai ore inventate, mai durate modificate.

Policy temporale (Phase 3, canonica per il core):
- wall-time naive ovunque (convenzione repo: oggetti con fuso romperebbero
  i dati); mai conversioni di zona qui dentro (guard G2).
- conversioni di fuso SOLO ai bordi di integrazione (Outlook: naive-in-zona
  o aware-con-offset -> naive nella tz mailbox, DST gestito li —
  test_timezone_dst.py). Mailbox tz da config validata (default
  Europe/Rome), usata sia per l'header Graph `Prefer` sia come target
  del parse (wiring auditato, test_outlook_auth.py).
- limite noto e dichiarato: l'aritmetica naive ignora le transizioni DST
  (slot a cavallo dell'ora mancante misura 1h reale; ambiguità fold non
  rappresentabile). Fixarlo richiederebbe aware nel core = rottura
  storage: rinviato per disegno, non per dimenticanza.
"""

from datetime import datetime, timedelta

from src.planner.capacity import pomo_minutes
from src.planner.models import (
    FixedEvent,
    PlanItem,
    ScheduledDayPlan,
    ScheduledItem,
    TimeWindow,
)


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
    return timedelta(minutes=pomo_minutes(item.estimate_pomo))


def deadlines_for(todos) -> dict:
    """{todo_id: (due_date_s, due_time_s)} dai task (TodoItem o TaskView).

    Totale, mai solleva: id None saltati, date/ore malformate passate cosi'
    come sono (`_deadline` le scarta). Unico punto che estrae scadenze per
    lo scheduler — i caller con i todos la costruiscono e la passano.
    """
    from src.planner.models import todo_to_task

    out = {}
    for t in todos or ():
        try:
            v = t if hasattr(t, "due_time") else todo_to_task(t)
        except Exception:
            continue
        if v.id is None:
            continue
        out[v.id] = (v.due, v.due_time)
    return out


def _deadline(deadlines, todo_id, day):
    """Limite superiore di fine-slot, o None se non applicabile (totale).

    Solo due-date == plan.day + orario HH:MM valido: il resto (scaduti,
    futuri, senza ora, garbage, mappa assente) schedula come prima.
    """
    try:
        due_s, due_t = (deadlines or {}).get(todo_id, ("", ""))
    except (AttributeError, TypeError, ValueError):
        return None
    if not due_t or str(due_s or "")[:10] != day.isoformat():
        return None
    try:
        h, m = int(str(due_t)[:2]), int(str(due_t)[3:5])
        if not (0 <= h <= 23 and 0 <= m <= 59 and str(due_t)[2:3] == ":"):
            return None
    except (ValueError, TypeError, IndexError):
        return None
    try:
        return datetime(day.year, day.month, day.day, h, m)
    except ValueError:
        return None


def events_to_busy(events) -> tuple:
    """Proiezione pura FixedEvent -> TimeWindow per il parametro busy.

    Solo (start, end) con end > start; niente merge/clip (restano dentro
    schedule, unica sede della logica temporale)."""
    out = []
    for e in events or ():
        if (
            isinstance(e, FixedEvent)
            and isinstance(e.start, datetime)
            and isinstance(e.end, datetime)
            and e.start < e.end
        ):
            out.append(TimeWindow(e.start, e.end))
    return tuple(out)


def _placeable(slot: TimeWindow, need, limit) -> bool:
    """Congiunzione di collocazione (Phase 4): fit nel libero + entro la
    scadenza quando c'e'. Un futuro bound temporale aggiunge qui un
    congiunto + mappa esplicita (precedente deadlines), mai chirurgia del
    loop. Terzo congiunto senza consumer reale vietato in review."""

    end = slot.end if limit is None else min(slot.end, limit)
    return slot.start + need <= end


def schedule(plan, availability, busy=(), deadlines=None) -> ScheduledDayPlan:
    """Colloca plan.planned in availability evitando busy (first-fit).

    deadlines = {todo_id: (due_date_s, due_time_s)} da deadlines_for():
    con scadenza oggi+orario lo slot deve finire entro la scadenza, senno'
    la voce resta unscheduled. None = vincoli spenti (legacy identico).
    """
    lo, hi = _day_bounds(plan.day)
    avail = _normalize(availability, lo, hi)
    busy_n = _merge(_normalize(busy, lo, hi))
    free = _subtract(avail, busy_n)
    scheduled: list = []
    unscheduled: list = []
    for item in plan.planned:
        need = _duration(item)
        limit = _deadline(deadlines, item.todo_id, plan.day)
        placed = None
        for i, slot in enumerate(free):
            if _placeable(slot, need, limit):
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
