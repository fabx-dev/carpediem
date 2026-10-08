"""Replanning deterministico (M4, puro, niente I/O/UI/i18n).

Il replan e' un'operazione esplicita: dato il piano corrente, l'ora
corrente, i task rimanenti, il calendario (busy) e la capacita' residua,
produce una ReplanProposal con le modifiche proposte — MAI modifiche
immediate al piano persistito (il commit e' domain.apply_replan + store).

Riutilizza il motore esistente senza toccarlo: Planner.propose() per la
selezione (i completati escono da soli, i gia'-pianificati restano
privilegiati in capacity.allocate), schedule() con availability clippata
a [now, fine] per rendere gli slot passati indisponibili. Il confronto
col piano corrente produce kept/moved/dropped/added; i motivi vengono da
decide()/primary_reason(), mai inventati.
"""

from dataclasses import dataclass
from datetime import date, datetime

from src.planner.decisions import decide, primary_reason
from src.planner.models import DayPlan, ScheduledDayPlan
from src.planner.scheduler import deadlines_for
from src.planner.service import Planner
from src.planner.time_model import clip_future

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
    """Una modifica proposta (slot 'HH:MM', None se senza slot)."""

    todo_id: int
    kind: str
    old_start: str | None = None
    old_end: str | None = None
    new_start: str | None = None
    new_end: str | None = None
    reasons: tuple = ()
    primary: tuple | None = None


@dataclass(frozen=True)
class ReplanProposal:
    """Proposta di replan: solo dati, nessuna scrittura."""

    day: date
    now: datetime
    moves: tuple = ()
    capacity_pomo: float = 0.0
    planned_pomo: int = 0
    residual_pomo: float = 0.0


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
    new_sched = Planner.schedule(new_plan, future, busy or (), deadlines_for(todos))
    new_slots = {s.item.todo_id: s for s in new_sched.scheduled}
    old_slots = {}
    if current is not None:
        old_slots = {s.item.todo_id: s for s in current.scheduled}

    current_ids = set()
    try:
        for t in todos or ():
            # constraint-site: scan confermati per diff (non decisione)
            if (
                getattr(t, "state", None) == "attivo"
                and getattr(t, "planned_for", "") == today
            ):
                try:
                    current_ids.add(int(t.id))
                except (ValueError, TypeError):
                    pass
    except TypeError:
        pass
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
            kind = KEPT if old_pair == new_pair else MOVED
        elif tid in new_ids:
            kind = ADDED
        else:
            kind = DROPPED
        moves.append(ReplanMove(tid, kind, *old_pair, *new_pair, reasons, primary))
    moves.sort(
        key=lambda m: (
            _KIND_ORDER.get(m.kind, 9),
            m.new_start or "99:99",
            m.todo_id if isinstance(m.todo_id, int) else 0,
        )
    )
    residual = new_plan.capacity_pomo - new_plan.planned_pomo
    return ReplanProposal(
        new_plan.day,
        moment,
        tuple(moves),
        new_plan.capacity_pomo,
        new_plan.planned_pomo,
        residual,
    )
