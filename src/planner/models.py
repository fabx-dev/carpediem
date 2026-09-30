"""Modello esplicito del piano giornaliero (puro, niente I/O/UI/i18n).

DayPlan e' il contratto tra Planner e consumer: cosa e' pianificato, cosa e'
tagliato per capacita', cosa e' scartato, con quanta capacita' e quale factor.
ScheduledDayPlan aggiunge la collocazione temporale (Fase 4): quali voci
hanno uno slot e quali no — mai orari inventati, mai scheduling del Planner.

Unita': i pomodori (stima_pomo, capacita' ore/0.5). planned_pomo puo'
superare capacity_pomo: mandatory e gia'-pianificati non si tagliano mai
(semantica storica) — nessun invariante forzato, il modello rappresenta
la realta' dell'algoritmo. Gli hard-excluded (non attivi, id None) non
compaiono, come nella proposta storica.

Tempi: datetime naive wall-time (convenzione del repo, mai aware).

TaskView (Phase 1): proiezione planner-owned del task in ingresso, non il
modello di dominio futuro — vedi docstring di TaskView/todo_to_task.
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class TaskView:
    """Proiezione planner-owned di un task (Phase 1, anti-corruption edge).

    Solo i campi scalari letti DAVVERO dagli algoritmi del planner
    (stato, scadenze, priorita', progetto, piano, stime, actual): niente
    titolo/note/tag/parenti/ricorrenze/sorgenti/log — quelli restano
    vocabolario applicativo di TodoItem e non entrano mai nel core.

    Status architetturale (vincolante, docs/planner-phase1-plan.md §5.0):
    TaskView e' una forma di input normalizzata minima e un boundary di
    compatibilita', INTENZIONALMENTE non il futuro modello di dominio
    canonico `Task` (decisione aperta di Phase 2+) e non il futuro `Task`
    pubblico. Regola: non aggiungere semantica di dominio a TaskView solo
    perche' potrebbe servire in futuro — ogni campo richiede una
    giustificazione nell'algoritmo corrente (test T2 fallisce chiuso su
    aggiunte: lista campi esatta).
    """

    id: int | None = None
    state: str = ""
    due: str = ""
    priority: str = ""
    project: str = ""
    planned_for: str = ""
    plan_skip: str = ""
    estimate_pomo: int = 0
    actual_pomo: int = 0
    created: str = ""
    completed_at: str = ""
    pomodoros: int = 0
    actual_minutes: int = 0


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def _as_nonneg_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError):
        return 0


def _as_id(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _date_part(value) -> str:
    """Solo YYYY-MM-DD di un due con eventuale HH:MM (stessa semantica di
    models._due_date_part, copiata per non importare il modello storage)."""
    s = str(value or "")
    return s.strip().split()[0] if s.strip() else ""


def todo_to_task(todo) -> TaskView:
    """TodoItem (o duck-typed equivalente) -> TaskView (totale, puro).

    Non solleva mai: campi mancanti/malformati diventano default sicuri con
    le stesse regole di TodoItem (clamp ≥0 su stime/actual, priorita' da
    enum .value o stringa raw, due ridotto alla parte data, progetto
    normalizzato come in TodoItem). Unico punto che conosce TodoItem.
    """
    state = str(getattr(todo, "state", "") or "")
    if not state:
        # Ripiego per oggetti senza proprieta' state: stessa regola di
        # TodoItem.state (done > paused > attivo).
        if getattr(todo, "done", False):
            state = "completato"
        elif getattr(todo, "paused", False):
            state = "in_sospeso"
        else:
            state = "attivo"
    raw_prio = getattr(todo, "priority", "")
    priority = str(getattr(raw_prio, "value", raw_prio) or "").strip().lower()
    return TaskView(
        id=_as_id(getattr(todo, "id", None)),
        state=state,
        due=_date_part(getattr(todo, "due", "")),
        priority=priority,
        project=str(getattr(todo, "project", "") or "").strip().lower(),
        planned_for=str(getattr(todo, "planned_for", "") or ""),
        plan_skip=str(getattr(todo, "plan_skip", "") or ""),
        estimate_pomo=_as_nonneg_int(getattr(todo, "stima_pomo", 0)),
        actual_pomo=_as_nonneg_int(getattr(todo, "actual_pomo", 0)),
        created=str(getattr(todo, "created", "") or ""),
        completed_at=str(getattr(todo, "completed_at", "") or ""),
        pomodoros=_as_int(getattr(todo, "pomodoros", 0)),
        actual_minutes=_as_nonneg_int(getattr(todo, "actual_minutes", 0)),
    )


@dataclass(frozen=True)
class PlanItem:
    """Una voce del piano: id + dati di pianificazione, mai il Todo intero."""

    todo_id: int
    score: int
    reasons: tuple = ()
    estimate_pomo: int = 1
    mandatory: bool = False


@dataclass(frozen=True)
class DayPlan:
    """Risultato/proposta del Planner per un giorno (immutabile, non CRUD)."""

    day: date
    planned: tuple = ()
    cut: tuple = ()
    skipped: tuple = ()
    capacity_pomo: float = 0.0
    planned_pomo: int = 0
    factor: float | None = None

    @property
    def items(self) -> tuple:
        """Tutte le voci in ordine legacy: pianificati, tagliati, scartati."""
        return (*self.planned, *self.cut, *self.skipped)

    def to_legacy(self) -> list:
        """Rappresentazione compatibile [(id, score, reasons)] come plan_day()."""
        return [(it.todo_id, it.score, list(it.reasons)) for it in self.items]


@dataclass(frozen=True)
class TimeWindow:
    """Intervallo [start, end): disponibilita' o busy (ruolo dal contesto)."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class FixedEvent:
    """Evento fisso esterno al Planner: vincolo temporale, mai un Task.

    Solo titolo + intervallo; niente score/priorita'/ricorrenze/persistenza.
    Non passa da scoring/capacity/calibration: diventa busy per lo scheduler
    tramite proiezione pura (events_to_busy), che resta fuori dal modello.
    """

    title: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ScheduledItem:
    """Voce del DayPlan collocata: riusa il PlanItem, aggiunge lo slot."""

    item: PlanItem
    start: datetime
    end: datetime


@dataclass(frozen=True)
class ScheduledDayPlan:
    """DayPlan + collocazione temporale (immutabile, non CRUD).

    scheduled/unscheduled coprono esattamente plan.planned: cut e skipped
    restano fuori dallo scheduling (gia' decisi dal Planner). Un mandatory
    senza slot resta unscheduled — mai overlap, mai ore inventate.
    """

    plan: DayPlan
    scheduled: tuple = ()
    unscheduled: tuple = ()
    availability: tuple = ()
    busy: tuple = ()


@dataclass(frozen=True)
class ExecutionFeedback:
    """Cosa e' successo davvero a una voce pianificata (Fase 5, derivato).

    Solo lettura dei dati esistenti, mai scritture: estimate dal PlanItem,
    scheduled dallo ScheduledDayPlan, actual dallo stato del Todo.
    - estimate_pomo: unita' astratta di stima (mai minuti).
    - estimate_minutes: stima in minuti via POMO_HOURS (unica conversione).
    - scheduled_start/end: slot assegnato, None se mai schedulato.
    - actual_pomo: pomodori dichiarati dall'utente (input calibrazione).
    - actual_minutes: minuti dichiarati dall'utente (puo' essere 0).
    - sessions: sessioni Pomodoro completate (evidence automatica).
    - completed: stato, indipendente dall'actual (sessione != task).
    """

    todo_id: int
    estimate_pomo: int
    estimate_minutes: int
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    sessions: int
    actual_pomo: int
    actual_minutes: int
    completed: bool
