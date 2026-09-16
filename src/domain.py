"""Logica di dominio: transizioni di stato, pomodori, pianificazione.

Contratto:
- niente I/O (mai store/storage), niente UI (mai T()/notify), niente orologi
  impliciti (i timestamp arrivano come parametri espliciti);
- le funzioni mutano SOLO gli oggetti TodoItem passati e ritornano riepiloghi
  (conteggi, nuovi item); deterministiche e testabili senza app/pilot;
- l'app e le screen chiamano queste e persistono via store.commit().
"""

from datetime import datetime, timedelta

from src.models import Recurrence, TodoItem, _due_date_part

STATES = ("attivo", "in_sospeso", "completato")

RADAR_CAP = 14
RADAR_PRIO_Y = {"alta": 3.0, "media": 2.0, "bassa": 1.0}
RADAR_HIT_DX = 1.0
RADAR_HIT_DY = 0.45
RADAR_MAX_CANDIDATES = 8


def _radar_jitter(todo_id: int | None) -> float:
    """Scostamento verticale deterministico in [-0.25, +0.25)."""
    return (((todo_id or 0) * 2654435761) % 1000) / 1000 * 0.5 - 0.25


def kanban_plot_data(todos: list[TodoItem], today_str: str) -> dict:
    """Dati per il radar scadenze in home (strip-scatter priorita' x orizzonte).

    Pura e deterministica: solo item non-sottotask; i completati contano in
    `closed7` (ultimi 7 giorni da completed_at), gli aperti con `due` valida
    diventano punti (orizzonte in giorni cappato a +-RADAR_CAP, serie
    late/open dallo scarto non cappato), gli aperti senza/invalida scadenza
    finiscono in `nodate`. `worst` = i 2 peggiori ritardi (id, giorni).
    `phash` = firma per saltare i rebuild invariati (solo sessione).
    Note: item senza id e completati senza `completed_at` sono esclusi
    (i primi non apribili, dei secondi si ignora la data); `today_str`
    invalida solleva ValueError."""
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    week_ago = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    points: list[tuple] = []
    late = open_ok = closed7 = nodate = 0
    late_rows: list[tuple] = []
    sig: list[tuple] = []
    for t in todos:
        if t.parent_id is not None or t.id is None:
            continue
        state = t.state
        sig.append((t.id, state, t.due, t.priority.value, (t.completed_at or "")[:10]))
        if state == "completato":
            day = (t.completed_at or "")[:10]
            if week_ago <= day <= today_str:
                closed7 += 1
            continue
        if state not in ("attivo", "in_sospeso"):
            continue
        due_part = _due_date_part(t.due)
        if not due_part:
            nodate += 1
            continue
        try:
            due_d = datetime.strptime(due_part, "%Y-%m-%d").date()
        except ValueError:
            nodate += 1
            continue
        horizon = (due_d - today).days
        serie = "late" if horizon < 0 else "open"
        if serie == "late":
            late += 1
            late_rows.append((horizon, t.id))
        else:
            open_ok += 1
        y = RADAR_PRIO_Y.get(t.priority.value, 2.0) + _radar_jitter(t.id)
        points.append((t.id, max(-RADAR_CAP, min(RADAR_CAP, horizon)), y, serie))
    late_rows.sort()
    return {
        "points": points,
        "late": late,
        "open_ok": open_ok,
        "closed7": closed7,
        "nodate": nodate,
        "worst": [(tid, h) for h, tid in late_rows[:2]],
        "phash": hash((today_str, tuple(sorted(sig)))),
    }


def radar_hit(points: list[tuple], day: float, y_est: float) -> list[int]:
    """Hit-test sui punti del radar: id entro soglia, vicini prima, max 8."""
    out = []
    for tid, h, y, _serie in points:
        dh, dy = abs(h - day), abs(y - y_est)
        if dh <= RADAR_HIT_DX and dy <= RADAR_HIT_DY:
            out.append((dh + dy, tid))
    return [tid for _, tid in sorted(out)[:RADAR_MAX_CANDIDATES]]


def apply_state(todo: TodoItem, choice: str, now_str: str) -> TodoItem | None:
    """Transizione di stato. Ritorna l'eventuale nuovo item da ricorrenza
    (senza id: il chiamante lo aggiunge via store.add che lo assegna)."""
    if choice not in STATES:
        raise ValueError(f"stato non valido: {choice!r}")
    if choice == "attivo":
        todo.done = False
        todo.paused = False
        todo.completed_at = ""
    elif choice == "in_sospeso":
        todo.done = False
        todo.paused = True
        todo.completed_at = ""
    else:  # completato
        todo.paused = False
        todo.done = True
        todo.planned_for = ""
        todo.completed_at = now_str
        if todo.recurrence != Recurrence.NONE and todo.due:
            return TodoItem(
                title=todo.title,
                priority=todo.priority,
                due=todo.recurrence.next_date(todo.due),
                notes=todo.notes,
                parent_id=todo.parent_id,
                recurrence=todo.recurrence,
                tags=list(todo.tags),
                project=todo.project,
                stima_pomo=todo.stima_pomo,
            )
    return None


def credit_pomodoro(todo: TodoItem, stamp_str: str) -> None:
    """Accredita un pomodoro (contatore + log)."""
    todo.pomodoros += 1
    todo.pomodoro_log.append(stamp_str)


def apply_form(todo: TodoItem, result: dict) -> None:
    """Applica il dict risultato del TodoFormScreen (8 campi)."""
    todo.title = result["title"]
    todo.priority = result["priority"]
    todo.due = result["due"]
    todo.notes = result["notes"]
    todo.recurrence = result["recurrence"]
    todo.tags = result["tags"]
    todo.project = result.get("project", "")
    todo.stima_pomo = result.get("stima_pomo", 0)


def review_plan(
    todos: list[TodoItem], selected_ids: set, tomorrow: str
) -> tuple[int, int]:
    """Piano di domani (Review): aggiunge i selezionati, toglie i deselezionati.
    Solo item attivi. Ritorna (aggiunti, rimossi)."""
    n = k = 0
    for t in todos:
        if t.state != "attivo":
            continue
        if t.id in selected_ids:
            t.planned_for = tomorrow
            n += 1
        elif t.planned_for == tomorrow:
            t.planned_for = ""
            k += 1
    return n, k


def proposal_plan(
    todos: list[TodoItem], selected_ids: set, today: str
) -> tuple[int, int]:
    """Piano smart additivo (Buongiorno): aggiunge i selezionati, marca gli
    scartati in plan_skip. Solo item attivi. Ritorna (aggiunti, rimandati)."""
    n = r = 0
    for t in todos:
        if t.state != "attivo":
            continue
        if t.id in selected_ids:
            t.planned_for = today
            t.plan_skip = ""
            n += 1
        elif t.planned_for != today:
            if t.plan_skip != today:
                r += 1
            t.plan_skip = today
    return n, r


def plan_add(todo: TodoItem, today: str) -> None:
    """Pianifica un item per oggi (piano giorno)."""
    todo.planned_for = today


def plan_remove(todo: TodoItem) -> None:
    """Toglie un item dal piano di oggi (piano giorno)."""
    todo.planned_for = ""


def plan_suspend(todo: TodoItem) -> None:
    """Sospende un item pianificato (piano giorno)."""
    todo.paused = True
