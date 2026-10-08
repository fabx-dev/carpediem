"""Replanning stabile deterministico (M4/F4, puro, niente I/O/UI/i18n).

Il replan e' un'operazione esplicita: dato il piano corrente, l'ora
corrente, i task rimanenti, il calendario (busy) e la capacita' residua,
produce una ReplanProposal con le modifiche proposte — MAI modifiche
immediate al piano persistito (il commit e' domain.apply_replan + store).

Riutilizza il motore esistente senza toccarlo: Planner.propose() per la
selezione (i completati escono da soli, i gia'-pianificati restano
privilegiati in capacity.allocate), poi scheduling a due passaggi per
stabilita': prima i confermati (in ordine di merito, sui soli slot futuri
[now, fine]), poi i nuovi candidati sui buchi restanti (slot occupati
come busy). Cosi' un nuovo task non ruba mai lo slot a un confermato:
MOVED solo se costretto da busy/now/completamenti. Gli slot passati sono
indisponibili via time_model (stessa clip del piano giorno: preview e
piano non divergono).

Il confronto col piano corrente produce kept/moved/dropped/added con
definizione precisa di KEPT (stesso task, stesso start/end, slot ancora
futuro e senza conflitti); i motivi vengono da decide()/primary_reason(),
mai inventati. I move senza nuovo slot portano `alt` (PlanAlternative da
diagnose sul merged: blocked_by/detail reali per l'outcome temporale).

Capacita' residua vs tempo residuo (F4, mai confusi):
- remaining_capacity (residual_pomo): pomodori di capacita' meno pianificati.
- remaining_time (remaining_min): minuti liberi futuri dopo now/busy.
"""

from dataclasses import dataclass
from datetime import date, datetime

from src.planner.decisions import decide, primary_reason
from src.planner.diagnostics import diagnose
from src.planner.models import (
    DayPlan,
    PlanAlternative,
    PlanningRequest,
    PlanningResult,
    ScheduledDayPlan,
    TimeWindow,
)
from src.planner.scheduler import deadlines_for
from src.planner.service import Planner
from src.planner.time_model import clip_future, residual

# Vedi scoring._REAL_DATETIME: classi reali per isinstance robusti al
# congelamento dell'orologio nei test (patch del nome `datetime`).
_REAL_DATE = date
_REAL_DATETIME = datetime

KEPT = "kept"
MOVED = "moved"
DROPPED = "dropped"
ADDED = "added"

_KIND_ORDER = {KEPT: 0, MOVED: 1, ADDED: 2, DROPPED: 3}


@dataclass(frozen=True)
class ReplanMove:
    """Una modifica proposta (slot 'HH:MM', None se senza slot).

    `alt` (PlanAlternative da diagnose sul nuovo schedule merged, solo per
    move senza nuovo slot e non DROPPED): porta blocked_by/detail reali
    per l'outcome temporale (non inserito vs non entra oggi); None per i
    move con slot (outcome = schedulato) e per DROPPED (rimozione per
    scelta, il motivo resta `primary`). Mai costruito a mano fuori test.
    """

    todo_id: int
    kind: str
    old_start: str | None = None
    old_end: str | None = None
    new_start: str | None = None
    new_end: str | None = None
    reasons: tuple = ()
    primary: tuple | None = None
    alt: PlanAlternative | None = None


@dataclass(frozen=True)
class ReplanProposal:
    """Proposta di replan: solo dati, nessuna scrittura."""

    day: date
    now: datetime
    moves: tuple = ()
    capacity_pomo: float = 0.0
    planned_pomo: int = 0
    residual_pomo: float = 0.0
    remaining_min: int = 0


def _hhmm(dt) -> str | None:
    try:
        return dt.strftime("%H:%M")
    except Exception:
        return None


def _clip_future(availability, now: datetime) -> list:
    """Availability con gli slot passati indisponibili (busy implicito).

    Thin wrapper sopra time_model.clip_future (F0): stessi risultati,
    solo il futuro di oggi. now di un altro giorno = nessuna availability.
    """
    return clip_future(availability, now)


def _is_kept(old, new, moment: datetime) -> bool:
    """KEPT preciso (F4, puro): stesso slot ancora valido, niente churn.

    Solo se entrambi noti, stessi start/end, inizio non trascorso
    (uno slot parzialmente trascorso non puo' essere KEPT: i task sono
    atomici) — la validita' busy/availability dello slot la garantisce
    il fresh schedule che ha prodotto `new`. (None, None) non arriva qui:
    il chiamante lo tratta come mantenuto-senza-orario.
    """
    try:
        if old is None or new is None:
            return False
        if old.start != new.start or old.end != new.end:
            return False
        return old.start >= moment
    except (AttributeError, TypeError):
        return False


def _confirmed_ids(todos, today: str) -> set:
    """Id confermati oggi (stato attivo + planned_for == today, puro)."""
    found = set()
    try:
        for t in todos or ():
            # constraint-site: scan confermati per diff (non decisione)
            if (
                getattr(t, "state", None) == "attivo"
                and getattr(t, "planned_for", "") == today
            ):
                try:
                    found.add(int(t.id))
                except (ValueError, TypeError):
                    pass
    except TypeError:
        pass
    return found


def _stable_schedule(new_plan: DayPlan, current_ids, future, busy, deadlines, moment):
    """Ricollocazione a due passaggi (F4): confermati prima, poi aggiunti.

    I confermati scelgono per primi sui slot futuri (ordine di merito del
    DayPlan); i nuovi candidati riempiono i buchi restanti (slot occupati
    passati come busy). Riusa Planner.schedule senza toccarlo: niente
    secondo scoring, niente ricalcolo stime. Ritorna (slots, first, second)
    dove slots = {todo_id: ScheduledItem} merged e first/second sono gli
    ScheduledDayPlan dei due passaggi (per la diagnose sugli outcome).
    """
    confirmed = [it for it in new_plan.planned if it.todo_id in current_ids]
    added = [it for it in new_plan.planned if it.todo_id not in current_ids]
    first = Planner.schedule(
        DayPlan(
            day=new_plan.day,
            planned=tuple(confirmed),
            capacity_pomo=new_plan.capacity_pomo,
            planned_pomo=sum(i.estimate_pomo for i in confirmed),
            factor=new_plan.factor,
        ),
        future,
        busy or (),
        deadlines,
        now=moment,
    )
    occupied = list(busy or ()) + [TimeWindow(s.start, s.end) for s in first.scheduled]
    second = Planner.schedule(
        DayPlan(
            day=new_plan.day,
            planned=tuple(added),
            capacity_pomo=new_plan.capacity_pomo,
            planned_pomo=sum(i.estimate_pomo for i in added),
            factor=new_plan.factor,
        ),
        future,
        occupied,
        deadlines,
        now=moment,
    )
    slots = {s.item.todo_id: s for s in (*first.scheduled, *second.scheduled)}
    return slots, first, second


def _merged_diagnose(new_plan, slots, first, busy, todos, moment, sample_count):
    """Alternative sul nuovo schedule merged (solo lettura, per gli outcome).

    Ricompone uno ScheduledDayPlan unico dai due passaggi (stessa
    availability/busy normalizzata del primo: i buchi occupati dai
    confermati restano visibili come scheduled per le probe di gara) e
    riusa diagnose() esistente: nessuna logica duplicata, nessuna
    divergenza probe-vs-reale. Ritorna {todo_id: PlanAlternative}.
    """
    scheduled = tuple(slots[tid] for tid in slots)
    unscheduled = tuple(it for it in new_plan.planned if it.todo_id not in slots)
    merged = ScheduledDayPlan(
        plan=new_plan,
        scheduled=scheduled,
        unscheduled=unscheduled,
        availability=first.availability,
        busy=first.busy,
    )
    try:
        req = PlanningRequest(
            day=new_plan.day,
            tasks=tuple(todos or ()),
            capacity_pomo=new_plan.capacity_pomo,
            factor=new_plan.factor,
            availability=first.availability,
            busy=first.busy,
            now=moment,
            sample_count=sample_count,
        )
        alts, _diags = diagnose(
            PlanningResult(request=req, plan=new_plan, scheduled=merged)
        )
    except Exception:
        return {}
    return {a.todo_id: a for a in alts}


def replan(
    todos,
    today: str,
    hours: float,
    availability,
    busy=(),
    now: datetime | date | None = None,
    *,
    current: ScheduledDayPlan | None = None,
    sample_count=None,
    factor: float | None = None,
) -> ReplanProposal:
    """Ricalcola la giornata e confronta col piano corrente (puro).

    availability/busy sono finestre gia' parsate (il parsing day_window
    resta al chiamante); now=None = fallback compat wall-clock (allowlisted
    Phase 1, docs/planner-phase1-plan.md §6.0: produzione sempre esplicita,
    rimozione in fase successiva); date = mezzanotte. factor=None = auto-
    calibrazione come Planner (compat, default invariato); valore esplicito
    = iniettato nel propose interno (seam Phase 1 §10.1, opt-in: nessun
    caller di produzione lo passa). I test passano now esplicito.
    current = ScheduledDayPlan corrente per gli slot vecchi (None = slot
    vecchi ignoti: kept solo se anche i nuovi mancano). Non muta i todos,
    non scrive.
    """
    if isinstance(now, _REAL_DATETIME):
        moment = now
    elif isinstance(now, _REAL_DATE):
        moment = datetime(now.year, now.month, now.day)
    else:
        moment = datetime.now()  # allowlist Phase 1 (§6.0): fallback compat
    new_plan: DayPlan = Planner(
        todos, today=today, hours=hours, factor=factor
    ).propose()
    decisions = {
        d.todo_id: d for d in decide(new_plan, todos, sample_count=sample_count)
    }
    future = _clip_future(availability, moment)
    deadlines = deadlines_for(todos)
    current_ids = _confirmed_ids(todos, today)
    new_slots, first_sched, _second_sched = _stable_schedule(
        new_plan,
        current_ids,
        future,
        busy,
        deadlines,
        moment,
    )
    new_alts = _merged_diagnose(
        new_plan, new_slots, first_sched, busy, todos, moment, sample_count
    )
    old_slots = {}
    if current is not None:
        old_slots = {s.item.todo_id: s for s in current.scheduled}
    new_ids = {it.todo_id for it in new_plan.planned}

    moves = []
    for tid in sorted(current_ids | new_ids):
        dec = decisions.get(tid)
        reasons = tuple(dec.reasons) if dec is not None else ()
        primary = primary_reason(dec) if dec is not None else None
        old = old_slots.get(tid)
        new = new_slots.get(tid)
        old_pair = (
            (_hhmm(old.start), _hhmm(old.end)) if old is not None else (None, None)
        )
        new_pair = (
            (_hhmm(new.start), _hhmm(new.end)) if new is not None else (None, None)
        )
        if tid in current_ids and tid in new_ids:
            if old is None and new is None:
                kind = KEPT  # mantenuto senza orario (nessuno slot prima né dopo)
            else:
                kind = KEPT if _is_kept(old, new, moment) else MOVED
        elif tid in new_ids:
            kind = ADDED
        else:
            kind = DROPPED
        alt = new_alts.get(tid) if (new is None and kind != DROPPED) else None
        moves.append(ReplanMove(tid, kind, *old_pair, *new_pair, reasons, primary, alt))
    moves.sort(
        key=lambda m: (
            _KIND_ORDER.get(m.kind, 9),
            m.new_start or "99:99",
            m.todo_id if isinstance(m.todo_id, int) else 0,
        )
    )
    residual_pomo = new_plan.capacity_pomo - new_plan.planned_pomo
    return ReplanProposal(
        new_plan.day,
        moment,
        tuple(moves),
        new_plan.capacity_pomo,
        new_plan.planned_pomo,
        residual_pomo,
        residual(future, busy, moment),
    )
