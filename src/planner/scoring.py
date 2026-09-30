"""Merito delle task: punteggio, motivi e flag mandatory (puri, niente I/O).

Pesi e regole identici allo storico plan_day(): scadenze (scaduto/oggi/domani),
priorita', progetto fermo, gia' pianificato oggi, annotazione calibrata
(solo motivo, mai punteggio). Il flag mandatory (scaduto/oggi) e' un vincolo
duro consumato da capacity (mai tagliati); tutto il resto e' preferenza.

Phase 1: opera su TaskView (proiezione normalizzata, mai TodoItem diretto).
PRIO_SCORES e' a chiavi stringa ("alta"/"media"/"bassa", stessi pesi storici;
parita' coperta dalle fixture). Niente import dal modello storage.
"""

from datetime import date, datetime

from src.planner import explain
from src.planner.models import TaskView

# Classi stdlib reali: i test congelano l'orologio patchando il nome
# `datetime` del modulo con una sottoclasse (unico modo per freezare
# datetime.now); gli isinstance qui devono restare veri anche patchati.
_REAL_DATE = date
_REAL_DATETIME = datetime

OVERDUE_SCORE = 100
DUE_TODAY_SCORE = 60
DUE_TOMORROW_SCORE = 30
PRIO_SCORES = {"alta": 20, "media": 10, "bassa": 0}
_PRIO_MEDIUM = 10
STALE_DAYS = 4
STALE_SCORE = 15
PLANNED_SCORE = 5


def parse_day(value):
    """YYYY-MM-DD (o date/datetime) -> date, o None se non interpretabile.

    Totale: accetta str, date, datetime; garbage (None, "", "xx") -> None
    e il chiamante applica la catena esplicito -> fallback compat.
    """
    if isinstance(value, _REAL_DATETIME):
        return value.date()
    if isinstance(value, _REAL_DATE):
        return value
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        return None


def _date_part(due: str) -> str:
    """Solo YYYY-MM-DD (TaskView.due e' gia' normalizzato: identita';
    tollera comunque stringhe con orario). Copia locale per non importare
    il modello storage."""
    s = str(due or "")
    return s.strip().split()[0] if s.strip() else ""


def stale_days(project: str, todos: list, today) -> int | None:
    """Giorni di fermo del progetto, o None se attivo.

    Ultimo completamento se esiste; senno' anzianita' del task attivo piu'
    vecchio (mai completato niente). Le created recenti non mascherano mai
    l'assenza di completamenti. Itera su TUTTI i todos (i completati servono
    per l'ultimo completamento), non solo sugli eleggibili.
    Accetta TaskView o TodoItem (stato letto via .state in entrambi).
    """
    if not project:
        return None
    last_done = None
    oldest_open = None
    for t in todos:
        if t.project != project:
            continue
        if t.state == "completato" and t.completed_at:
            d = parse_day(t.completed_at)
            if d and (last_done is None or d > last_done):
                last_done = d
        elif t.state == "attivo" and t.created:
            d = parse_day(t.created)
            if d and (oldest_open is None or d < oldest_open):
                oldest_open = d
    ref = last_done or oldest_open
    if ref is None:
        return None
    age = (today - ref).days
    return age if age >= STALE_DAYS else None


def score(
    todo: TaskView,
    *,
    today,
    today_s: str,
    stale_n: int | None,
    calib: float | None,
) -> tuple[int, list, bool]:
    """(punteggio, reasons, mandatory) di un singolo task eleggibile."""
    result = 0
    reasons: list[tuple[str, dict]] = []
    due = _date_part(todo.due)
    due_d = parse_day(due) if due else None
    mandatory = False
    if due_d and due_d < today:
        result += OVERDUE_SCORE
        reasons.append(explain.overdue())
        mandatory = True
    elif due_d and due_d == today:
        result += DUE_TODAY_SCORE
        reasons.append(explain.due_today())
        mandatory = True
    elif due_d and (due_d - today).days == 1:
        result += DUE_TOMORROW_SCORE
        reasons.append(explain.due_tomorrow())
    result += PRIO_SCORES.get(todo.priority, _PRIO_MEDIUM)
    if todo.priority == "alta":
        reasons.append(explain.prio())
    if stale_n is not None:
        result += STALE_SCORE
        reasons.append(explain.stale(stale_n))
    if todo.planned_for == today_s:
        result += PLANNED_SCORE
        reasons.append(explain.planned())
    try:
        has_est = int(todo.estimate_pomo or 0) > 0
    except (ValueError, TypeError):
        has_est = False
    if calib is not None and has_est:
        reasons.append(explain.calibrated(calib))
    return result, reasons, mandatory


def score_all(
    eligible: list[TaskView],
    all_todos: list[TaskView],
    today,
    today_s: str,
    calib: float | None,
) -> list:
    """Valuta gli eleggibili: [(todo, score, reasons, mandatory)]."""
    stale_cache: dict[str, int | None] = {}
    scored = []
    for t in eligible:
        if t.project not in stale_cache:
            stale_cache[t.project] = stale_days(t.project, all_todos, today)
        result, reasons, mandatory = score(
            t,
            today=today,
            today_s=today_s,
            stale_n=stale_cache[t.project],
            calib=calib,
        )
        scored.append((t, result, reasons, mandatory))
    return scored


def rank_key(entry) -> tuple:
    """Ordinamento per merito: score desc, poi scadenza, poi id."""
    todo, score, _reasons = entry[0], entry[1], entry[2]
    return (-score, _date_part(todo.due) or "9999", todo.id)
