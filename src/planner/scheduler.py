"""Scheduler temporale deterministico (puro, niente I/O/UI/i18n).

Catalogo hard Phase 4 (H5-H8; H9 vive in replan._clip_future via
time_model; H1-H4 in constraints/capacity): H5 solo dentro availability
(fuse con time_model: sovrapposte/contenute/contigue unite), H6 mai
overlap busy, H7 scadenza oggi+orario (sotto), H8 clip finestre al giorno.

Collocazione best-fit atomica (F2): i task restano indivisibili e si
collocano nell'ordine del Planner con urgenza temporale (slack crescente
per le scadenze odierne con ora valida, stable sort — mai secondo
scoring sul merito); tra i gap che contengono il task vince il minimo
waste (gap - need), tie-break (waste, start). Gerarchia esplicita:
merito -> urgenza/deadline -> capienza del gap -> fit -> tie-break.
Il waste sceglie solo il gap, mai l'ordine dei task.

Deadline (Phase 3): una voce con scadenza OGGI con orario si colloca solo
in slot che finiscono ENTRO la scadenza (bordo inclusivo); altrimenti resta
unscheduled strutturale. Vale solo due-date == plan.day + orario valido:
scaduti (merito, non vincolo), futuri e senza-ora schedulano come prima.
Le scadenze arrivano nella mappa esplicita `deadlines` (None = spente =
comportamento legacy identico).

Cut e skipped non si schedulano (gia' decisi dal Planner); i planned senza
slot restano unscheduled (strutturale, motivo via diagnose()/blocked_by).
Mandatory senza slot = unscheduled: mai overlap, mai ore inventate, mai
durate modificate, mai split del task.

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
from src.planner.time_model import fuse
from src.planner.time_model import slack as canonical_slack


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
    """Finestre valide, clippate al giorno, fuse e ordinate per inizio.

    La fusione (time_model.fuse) unisce sovrapposte/contenute/contigue:
    niente double-booking apparente da availability multiple.
    """
    out = []
    for w in windows or ():
        if isinstance(w, TimeWindow):
            c = _clip(w, lo, hi)
            if c is not None:
                out.append(c)
    return fuse(out)


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


_DAY_MINUTES = 24 * 60


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

    Delega a time_model.deadline_at (F3, definizione unica): solo due-date
    == plan.day + orario valido, il resto schedula come prima.
    """
    from src.planner.time_model import deadline_at

    return deadline_at(deadlines, todo_id, day)


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


def _slack_order_key(item, deadlines, day, now):
    """Chiave di urgenza temporale (F2): slack crescente, mai merito.

    Solo scadenze odierne con ora valida + now esplicito: (0, slack_min).
    Tutto il resto (senza scadenza odierna, o now assente) resta in coda
    con chiave costante — stable sort preserva l'ordine di merito del
    DayPlan. Slack canonico da time_model (deadline - now - duration).
    """
    if now is None:
        return (1, 0)
    limit = _deadline(deadlines, item.todo_id, day)
    if limit is None:
        return (1, 0)
    value = canonical_slack(limit, now, pomo_minutes(item.estimate_pomo))
    if value is None:
        return (1, 0)
    return (0, value)


def _best_gap(free: list, need, limit):
    """Indice del gap col minimo waste tra quelli collocabili, o None.

    Candidato = inizio + need <= min(fine, scadenza); waste = (fine
    effettiva - inizio) - need. Tie-break (waste, start): il loop segue
    `free` (ordinato per inizio), primo minimo vince; perfect-fit esce
    subito. Puro, deterministico.
    """
    best = None
    best_waste = None
    for i, slot in enumerate(free):
        end = slot.end if limit is None else min(slot.end, limit)
        if slot.start + need > end:
            continue
        waste = (end - slot.start) - need
        if best is None or waste < best_waste:
            best, best_waste = i, waste
            if waste <= timedelta(0):
                break
    return best


def schedule(plan, availability, busy=(), deadlines=None, now=None) -> ScheduledDayPlan:
    """Colloca plan.planned in availability evitando busy (best-fit atomico).

    deadlines = {todo_id: (due_date_s, due_time_s)} da deadlines_for():
    con scadenza oggi+orario lo slot deve finire entro la scadenza, senno'
    la voce resta unscheduled. None = vincoli spenti (legacy identico).
    now = datetime vincolante per l'ordine di urgenza (slack crescente);
    None = ordine legacy (scadenza odierna prima, resto per merito).
    I task restano atomici: mai split su piu' gap.
    """
    lo, hi = _day_bounds(plan.day)
    avail = _normalize(availability, lo, hi)
    busy_n = _merge(_normalize(busy, lo, hi))
    free = _subtract(avail, busy_n)
    moment = now if isinstance(now, datetime) else None
    # Urgenza temporale (F2): le voci con scadenza odierna si ordinano per
    # slack crescente — una deadline stretta non resta stranded dietro una
    # voce capiente. Stable sort: l'ordine di merito del DayPlan resta
    # l'unico criterio oltre il vincolo. Senza now/scadenze la chiave e'
    # costante e la sequenza e' identica a prima (legacy).
    if moment is not None:
        ordered = sorted(
            plan.planned,
            key=lambda it: _slack_order_key(it, deadlines, plan.day, moment),
        )
    else:
        ordered = sorted(
            plan.planned,
            key=lambda it: _deadline(deadlines, it.todo_id, plan.day) is None,
        )
    scheduled: list = []
    unscheduled: list = []
    for item in ordered:
        # Infeasible per costruzione (B6): lo scheduler e' giornaliero,
        # oltre le 24h nessuna finestra puo' bastare. Confronto sui minuti
        # (int, mai overflow) PRIMA di costruire il timedelta; il fit esatto
        # 24h resta schedulabile.
        if pomo_minutes(item.estimate_pomo) > _DAY_MINUTES:
            unscheduled.append(item)
            continue
        need = _duration(item)
        limit = _deadline(deadlines, item.todo_id, plan.day)
        at = _best_gap(free, need, limit)
        if at is None:
            unscheduled.append(item)
            continue
        slot = free[at]
        placed = ScheduledItem(item, slot.start, slot.start + need)
        if slot.start + need < slot.end:
            free[at] = TimeWindow(slot.start + need, slot.end)
        else:
            del free[at]
        scheduled.append(placed)
    return ScheduledDayPlan(
        plan=plan,
        scheduled=tuple(scheduled),
        unscheduled=tuple(unscheduled),
        availability=tuple(avail),
        busy=tuple(busy_n),
    )
