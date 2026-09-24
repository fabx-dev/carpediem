"""Logica di dominio: transizioni di stato, pomodori, pianificazione.

Contratto:
- niente I/O (mai store/storage), niente UI (mai T()/notify), niente orologi
  impliciti (i timestamp arrivano come parametri espliciti);
- le funzioni mutano SOLO gli oggetti TodoItem passati e ritornano riepiloghi
  (conteggi, nuovi item); deterministiche e testabili senza app/pilot;
- l'app e le screen chiamano queste e persistono via store.commit().
"""

from datetime import datetime, timedelta

from src.models import Recurrence, TaskExecution, TodoItem, _due_date_part

STATES = ("attivo", "in_sospeso", "completato")

# Calibrazione locale stime ("piano che impara"): policy anti-rumore.
# Minimo campioni per fidarsi, clamp del fattore, mediana (non media) per
# resistere agli outlier. Mai riscrive stima_pomo: solo display in plan_day.
CAL_MIN_SAMPLES = 5
CAL_CLAMP_MIN = 0.5
CAL_CLAMP_MAX = 3.0

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


def apply_replan(todos: list[TodoItem], proposal, today: str) -> tuple[int, int]:
    """Applica una ReplanProposal confermata (puro sui todos passati).

    ADDED -> planned_for=today (plan_skip azzerato, come la conferma smart);
    DROPPED -> planned_for azzerato + plan_skip=today (scarto esplicito di
    oggi, non riproposto); KEPT/MOVED invariati (gli slot non si persistono).
    Solo attivi. Ritorna (aggiunti, rimandati). Il commit resta al chiamante.
    """
    try:
        moves = list(getattr(proposal, "moves", None) or ())
    except TypeError:
        return (0, 0)
    by_id = {}
    try:
        for t in todos or ():
            by_id[getattr(t, "id", None)] = t
    except TypeError:
        return (0, 0)
    added = dropped = 0
    for m in moves:
        todo = by_id.get(getattr(m, "todo_id", None))
        if todo is None or todo.state != "attivo":
            continue
        kind = getattr(m, "kind", "")
        if kind == "added":
            todo.planned_for = today
            todo.plan_skip = ""
            added += 1
        elif kind == "dropped":
            todo.planned_for = ""
            todo.plan_skip = today
            dropped += 1
    return (added, dropped)


def plan_suspend(todo: TodoItem) -> None:
    """Sospende un item pianificato (piano giorno)."""
    todo.paused = True


def matches_smart(todo: TodoItem, spec: dict) -> bool:
    """AND di {state, tag, project, search}; campo vuoto/None = wildcard.

    Case-insensitive su tag/project/search; search su titolo+note+progetto+tag.
    Spec malformata mai solleva: wildcard."""
    try:
        state = spec.get("state")
    except AttributeError:
        return True
    if state is not None:
        # Vocabolario filtri ("completati" plurale) -> stato modello (singolare),
        # come app._matches_state: accetta entrambi, mai fallimenti silenziosi.
        target = {"completati": "completato"}.get(state, state)
        if todo.state != target:
            return False
    tag = spec.get("tag")
    if tag and str(tag).strip().lower() not in [t.lower() for t in todo.tags]:
        return False
    project = spec.get("project")
    if project and todo.project.lower() != str(project).strip().lower():
        return False
    search = spec.get("search")
    if search:
        q = str(search).strip().lower()
        hay = " ".join([todo.title, todo.notes, todo.project, *todo.tags]).lower()
        if q not in hay:
            return False
    return True


def record_actual(todo: TodoItem, actual_pomo: int, actual_minutes: int = 0) -> None:
    """Registra il tempo effettivo a completamento (clamp >= 0, int)."""
    try:
        todo.actual_pomo = max(0, int(actual_pomo or 0))
    except (ValueError, TypeError):
        todo.actual_pomo = 0
    try:
        todo.actual_minutes = max(0, int(actual_minutes or 0))
    except (ValueError, TypeError):
        todo.actual_minutes = 0


def validate_smart_name(name: str, lists: list[dict], max_n: int) -> tuple:
    """Valida il nome di una smart list: (ok, chiave_i18n, params).

    Pura: l'app la usa prima di toccare config/DOM. Ordine: vuoto, duplicato
    (case-insensitive), limite."""
    clean = (name or "").strip()
    if not clean:
        return (False, "n_smart_empty_name", {})
    try:
        current = list(lists) if isinstance(lists, list) else []
    except TypeError:
        current = []
    if any(
        isinstance(e, dict) and str(e.get("name", "")).lower() == clean.lower()
        for e in current
    ):
        return (False, "n_smart_dup", {"n": clean})
    try:
        limit = int(max_n)
    except (ValueError, TypeError):
        limit = 10
    if len(current) >= limit:
        return (False, "n_smart_full", {})
    return (True, "", {"n": clean})


def _calibration_ratios(todos: list[TodoItem]) -> list[float]:
    """Rapporti actual/stima sui completati con entrambi > 0 (anti-rumore)."""
    ratios: list[float] = []
    for t in todos:
        try:
            est = int(t.stima_pomo or 0)
            act = int(t.actual_pomo or 0)
        except (ValueError, TypeError):
            continue
        if t.state == "completato" and est > 0 and act > 0:
            ratios.append(act / est)
    return ratios


def calibration_samples(todos: list[TodoItem]) -> int:
    """Quanti completati alimentano la calibrazione."""
    try:
        return len(_calibration_ratios(list(todos)))
    except TypeError:
        return 0


def calibration_factor(todos: list[TodoItem]) -> float | None:
    """Fattore mediano actual/stima sui completati con entrambi > 0.

    None se campioni < CAL_MIN_SAMPLES; clamp [MIN, MAX] per non fidarsi
    mai ciecamente di pochi dati o outlier estremi."""
    ratios = _calibration_ratios(todos)
    if len(ratios) < CAL_MIN_SAMPLES:
        return None
    ratios.sort()
    mid = len(ratios) // 2
    median = ratios[mid] if len(ratios) % 2 else (ratios[mid - 1] + ratios[mid]) / 2
    return max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, median))


def calibrated_estimate(todo: TodoItem, factor: float | None) -> tuple[int, bool]:
    """(stima_corretta, usata_calibrazione). Base = stima o 1 se assente.

    L'1 per stima assente e' un fallback di pianificazione (il piano ha
    bisogno di una durata), non una stima dichiarata dall'utente."""
    try:
        base = int(todo.stima_pomo or 0) or 1
    except (ValueError, TypeError):
        base = 1
    if factor is None:
        return base, False
    try:
        f = max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
    except (ValueError, TypeError):
        return base, False
    return max(1, round(base * f)), True


# M2 Task Reality Model: minuti wall-time come unita' canonica della history.
# 1 pomodoro = 30 minuti, in lock-step con planner.capacity.POMO_HOURS (0.5):
# l'import diretto e' vietato qui (capacity importa domain, sarebbe un ciclo).
# Se POMO_HOURS cambia, aggiornare anche POMO_MINUTES.
POMO_MINUTES = 30

# Soglie confidence (informativa in M2, mai decisionale): LOW < 10,
# MEDIUM 10-29, HIGH >= 30 osservazioni.
CONFIDENCE_LEVELS = ("LOW", "MEDIUM", "HIGH")


def make_execution(
    task_id,
    started_at="",
    ended_at=None,
    planned_minutes=0,
    actual_minutes=0,
    estimate_pomo=0,
    completed=False,
) -> TaskExecution:
    """Costruttore puro di TaskExecution (mai I/O; la persistenza e' del chiamante)."""
    return TaskExecution(
        task_id,
        started_at,
        ended_at,
        planned_minutes,
        actual_minutes,
        estimate_pomo,
        completed,
    )


def execution_variance(exec: TaskExecution) -> int | None:
    """actual - planned in minuti; None senza actual (non inventare durate)."""
    if exec.actual_minutes <= 0:
        return None
    return exec.actual_minutes - exec.planned_minutes


def resolve_actual_minutes(todo: TodoItem) -> int:
    """Priorita' actual alla chiusura: actual_minutes esplicito, poi
    actual_pomo x POMO_MINUTES, altrimenti 0 = senza actual."""
    try:
        explicit = int(todo.actual_minutes or 0)
    except (ValueError, TypeError):
        explicit = 0
    if explicit > 0:
        return explicit
    try:
        pomo = int(todo.actual_pomo or 0)
    except (ValueError, TypeError):
        pomo = 0
    return max(0, pomo) * POMO_MINUTES if pomo > 0 else 0


def resolve_planned_minutes(slot_minutes, estimate_pomo) -> int:
    """Priorita' planned: durata dello slot schedulato, altrimenti
    estimate_pomo x POMO_MINUTES (fallback or-1 come il planner)."""
    try:
        slot = int(slot_minutes or 0)
    except (ValueError, TypeError):
        slot = 0
    if slot > 0:
        return slot
    try:
        est = int(estimate_pomo or 0) or 1
    except (ValueError, TypeError):
        est = 1
    return max(1, est) * POMO_MINUTES


def _valid_observations(executions) -> list[TaskExecution]:
    """Completate con actual e stima snapshot > 0: le uniche che insegnano."""
    try:
        items = list(executions)
    except TypeError:
        return []
    return [
        e
        for e in items
        if isinstance(e, TaskExecution)
        and e.completed
        and e.actual_minutes > 0
        and e.estimate_pomo > 0
    ]


def _median(sorted_vals: list) -> float | None:
    if not sorted_vals:
        return None
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def execution_stats(executions) -> dict:
    """Statistiche robuste sugli actual (minuti) delle osservazioni valide.

    count=0 -> statistiche None (mai divisione per zero, mai eccezioni).
    Mediana + p90 (nearest-rank) resistono agli outlier meglio della media."""
    actuals = sorted(e.actual_minutes for e in _valid_observations(executions))
    n = len(actuals)
    if n == 0:
        return {
            "count": 0,
            "median": None,
            "min": None,
            "max": None,
            "p90": None,
            "variance": None,
        }
    mean = sum(actuals) / n
    rank = min(n, max(1, -(-90 * n // 100)))
    return {
        "count": n,
        "median": _median(actuals),
        "min": actuals[0],
        "max": actuals[-1],
        "p90": actuals[rank - 1],
        "variance": sum((a - mean) ** 2 for a in actuals) / n,
    }


def execution_confidence(count) -> str:
    """LOW < 10, MEDIUM 10-29, HIGH >= 30. Informativa, mai decisionale."""
    try:
        n = int(count)
    except (ValueError, TypeError):
        n = 0
    if n >= 30:
        return "HIGH"
    if n >= 10:
        return "MEDIUM"
    return "LOW"


def last_observation_at(executions) -> str:
    """Max ended_at tra le osservazioni valide, '' senza storia."""
    ends = [e.ended_at for e in _valid_observations(executions) if e.ended_at]
    try:
        return max(ends) if ends else ""
    except TypeError:
        return ""


def execution_calibration_factor(executions) -> float | None:
    """Fattore mediano actual/stima dalla history (stessa policy anti-rumore
    di calibration_factor: minimo campioni, clamp). Le due fonti coincidono
    quando l'actual deriva dai pomodori (actual_pomo x 30 / stima x 30)."""
    ratios = []
    for e in _valid_observations(executions):
        estimated = e.estimate_pomo * POMO_MINUTES
        if estimated > 0:
            ratios.append(e.actual_minutes / estimated)
    if len(ratios) < CAL_MIN_SAMPLES:
        return None
    ratios.sort()
    return max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, _median(ratios) or 0))


def predicted_minutes(estimate_minutes, factor) -> int:
    """predicted = estimate x factor; senza factor (o stima nulla) = estimate."""
    try:
        est = int(estimate_minutes or 0)
    except (ValueError, TypeError):
        est = 0
    if est <= 0:
        return 0
    if factor is None:
        return est
    try:
        f = max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
    except (ValueError, TypeError):
        return est
    return max(1, round(est * f))
