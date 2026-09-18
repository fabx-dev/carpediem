"""Merito delle task: punteggio, motivi e flag mandatory (puri, niente I/O).

Pesi e regole identici allo storico plan_day(): scadenze (scaduto/oggi/domani),
priorita', progetto fermo, gia' pianificato oggi, annotazione calibrata
(solo motivo, mai punteggio). Il flag mandatory (scaduto/oggi) e' un vincolo
duro consumato da capacity (mai tagliati); tutto il resto e' preferenza.
"""

from datetime import datetime

from src.models import Priority, TodoItem, _due_date_part
from src.planner import explain

OVERDUE_SCORE = 100
DUE_TODAY_SCORE = 60
DUE_TOMORROW_SCORE = 30
PRIO_SCORES = {Priority.HIGH: 20, Priority.MEDIUM: 10, Priority.LOW: 0}
STALE_DAYS = 4
STALE_SCORE = 15
PLANNED_SCORE = 5


def parse_day(value: str):
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        return None


def stale_days(project: str, todos: list, today) -> int | None:
    """Giorni di fermo del progetto, o None se attivo.

    Ultimo completamento se esiste; senno' anzianita' del task attivo piu'
    vecchio (mai completato niente). Le created recenti non mascherano mai
    l'assenza di completamenti. Itera su TUTTI i todos (i completati servono
    per l'ultimo completamento), non solo sugli eleggibili.
    """
    if not project:
        return None
    last_done = None
    oldest_open = None
    for t in todos:
        if t.project != project:
            continue
        if t.done and t.completed_at:
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
    todo: TodoItem,
    *,
    today,
    today_s: str,
    stale_n: int | None,
    calib: float | None,
) -> tuple[int, list, bool]:
    """(punteggio, reasons, mandatory) di un singolo task eleggibile."""
    result = 0
    reasons: list[tuple[str, dict]] = []
    due = _due_date_part(todo.due)
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
    result += PRIO_SCORES.get(todo.priority, PRIO_SCORES[Priority.MEDIUM])
    if todo.priority == Priority.HIGH:
        reasons.append(explain.prio())
    if stale_n is not None:
        result += STALE_SCORE
        reasons.append(explain.stale(stale_n))
    if todo.planned_for == today_s:
        result += PLANNED_SCORE
        reasons.append(explain.planned())
    try:
        has_est = int(todo.stima_pomo or 0) > 0
    except (ValueError, TypeError):
        has_est = False
    if calib is not None and has_est:
        reasons.append(explain.calibrated(calib))
    return result, reasons, mandatory


def score_all(
    eligible: list[TodoItem],
    all_todos: list[TodoItem],
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
    return (-score, _due_date_part(todo.due) or "9999", todo.id)
