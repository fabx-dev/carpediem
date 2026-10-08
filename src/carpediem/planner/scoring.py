"""Merito delle task: punteggio, motivi e flag mandatory (puri, niente I/O).

Pesi e regole identici allo storico plan_day(); catalogo soft Phase 4
(S1-S5, influenza senza veto — mai vincoli): S1 priorita', S2 progetto
fermo, S3 domani, S4 bonus gia'-pianificato, S5 annotazione calibrata
(solo motivo, mai punteggio). Il flag mandatory (scaduto/oggi) e' un vincolo
duro consumato da capacity (mai tagliati, H4); tutto il resto e' preferenza.

Phase 5 (S-NoScore): pesi rivalutati esplicitamente — nessuna evidenza di
merito sbagliato (fixture 40+ verdi, nessuno scenario che li smentisca) —
invariati. La procedura differenziale legacy-vs-nuovo resta armata per
quando servira'.

Phase 1: opera su TaskView (proiezione normalizzata, mai TodoItem diretto).
PRIO_SCORES e' a chiavi stringa ("alta"/"media"/"bassa", stessi pesi storici;
parita' coperta dalle fixture). Niente import dal modello storage.
"""

from datetime import date, datetime

from carpediem.planner import explain
from carpediem.planner.estimation import POMO_MINUTES
from carpediem.planner.models import TaskView
from carpediem.planner.time_model import deadline_at
from carpediem.planner.time_model import slack as canonical_slack

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
        # constraint-site: lettura stato per fermo progetto (non decisione)
        if t.state == "completato" and t.completed_at:
            d = parse_day(t.completed_at)
            if d and (last_done is None or d > last_done):
                last_done = d
        elif t.state == "attivo" and t.created:  # constraint-site: vedi sopra
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


def rank_key(entry, *, now=None, deadlines=None) -> tuple:
    """Ordinamento per merito: score desc, poi urgenza, poi scadenza, poi id.

    Pesi primari congelati (F3: 100/60/30/20/10/15/5 intoccati). A parita'
    di score, secondario deterministico: slack crescente (deadline odierna
    con ora valida + now esplicito, definizione canonica time_model),
    poi durata crescente (i task brevi riempiono meglio i buchi: proxy di
    fit senza contesto temporale — il waste vero vive nel best-fit F2 dove
    i gap esistono, capacity resta timeline-free per disegno), poi scadenza
    e id. Senza now/deadlines la chiave e' quella legacy, byte-identica.
    """
    todo, score, _reasons = entry[0], entry[1], entry[2]
    due = _date_part(todo.due) or "9999"
    moment = _as_moment(now)
    if moment is None or not deadlines:
        return (-score, due, todo.id)
    return (
        -score,
        _slack_key(todo, moment, deadlines),
        _need_min(todo),
        due,
        todo.id,
    )


_SLACK_NONE = 10**9


def _need_min(todo) -> int:
    """Durata in minuti dalla stima raw (fallback 1, mai calibrazione).

    La calibrazione scala tutti i task dello stesso factor: ininfluente per
    l'ordine relativo. POMO_MINUTES in lock-step con capacity.POMO_HOURS.
    """
    try:
        base = int(todo.estimate_pomo or 0) or 1
    except (ValueError, TypeError):
        base = 1
    return max(0, POMO_MINUTES * base)


def _as_moment(now):
    if isinstance(now, _REAL_DATETIME):
        return now
    if isinstance(now, _REAL_DATE):
        return datetime(now.year, now.month, now.day)
    return None


def _slack_key(todo, moment, deadlines) -> int:
    """Slack canonico del task, o +inf se non calcolabile (in coda).

    moment gia' normalizzato dal chiamante (rank_key); deadlines la mappa
    {todo_id: (due_s, due_t)} dello scheduler.
    """
    if moment is None or not deadlines:
        return _SLACK_NONE
    try:
        day = parse_day(_date_part(todo.due))
    except Exception:
        return _SLACK_NONE
    if day is None:
        return _SLACK_NONE
    limit = deadline_at(deadlines, todo.id, day)
    if limit is None:
        return _SLACK_NONE
    value = canonical_slack(limit, moment, _need_min(todo))
    return value if value is not None else _SLACK_NONE
