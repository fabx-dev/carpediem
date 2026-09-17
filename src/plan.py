"""Pianificatore giornaliero deterministico (nessuna rete, nessuna AI).

plan_day(todos, today=None, hours=6.0) -> [(id, score, reasons)] dove reasons
e' [(chiave_i18n, params), ...] pronta per T(chiave, **params) nella UI.

Regole (pesi = costanti in testa al modulo, ritoccabili senza refactor):
- solo task "attivo" (state); completati/sospesi esclusi in silenzio; id None scartati.
- scadenze: scaduto OVERDUE / oggi TODAY / domani TOMORROW / altro o senza data 0.
- priorita': alta/medio/bassa da PRIO_SCORES; reason solo per alta.
- progetto fermo: nessun completamento negli ultimi STALE_DAYS (o task attivi
  fermi da piu' di STALE_DAYS se mai completato) -> +STALE_SCORE con n giorni.
- gia' in piano oggi (planned_for == today): +PLANNED_SCORE.
- capacita': ore / POMO_HOURS pomodori; stima mancante = DEFAULT_ESTIMATE.
  Scaduti e di oggi non si tagliano mai (possono sforare); gli altri riempiono
  greedy per score; gli esclusi hanno reason ("plan_cut", {}).
- scartati oggi (plan_skip == today): in fondo con reason ("plan_skipped", {}),
  mai preselezionati, fuori dal consumo di capacita'; domani si ripropongono.
- ordinamento: inclusi per score desc (a pari: due, id), poi tagliati, poi scartati.
"""

from datetime import datetime

from src.domain import CAL_CLAMP_MAX, CAL_CLAMP_MIN
from src.models import Priority, _due_date_part

OVERDUE_SCORE = 100
DUE_TODAY_SCORE = 60
DUE_TOMORROW_SCORE = 30
PRIO_SCORES = {Priority.HIGH: 20, Priority.MEDIUM: 10, Priority.LOW: 0}
STALE_DAYS = 4
STALE_SCORE = 15
PLANNED_SCORE = 5
POMO_HOURS = 0.5
DEFAULT_ESTIMATE = 1


def _parse_day(value: str):
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        return None


def _stale_days(project: str, todos: list, today) -> int | None:
    """Giorni di fermo del progetto, o None se attivo.

    Ultimo completamento se esiste; senno' anzianita' del task attivo piu'
    vecchio (mai completato niente). Le created recenti non mascherano mai
    l'assenza di completamenti.
    """
    if not project:
        return None
    last_done = None
    oldest_open = None
    for t in todos:
        if t.project != project:
            continue
        if t.done and t.completed_at:
            d = _parse_day(t.completed_at)
            if d and (last_done is None or d > last_done):
                last_done = d
        elif t.state == "attivo" and t.created:
            d = _parse_day(t.created)
            if d and (oldest_open is None or d < oldest_open):
                oldest_open = d
    ref = last_done or oldest_open
    if ref is None:
        return None
    age = (today - ref).days
    return age if age >= STALE_DAYS else None


def _estimate(todo, factor: float | None = None) -> int:
    """Stima pomodori: base stima_pomo o DEFAULT; con factor, calibrata.

    Il factor (da domain.calibration_factor) corregge senza riscrivere mai
    la stima originale; clamp [0.5, 3.0] come in domain per coerenza."""
    try:
        base = int(todo.stima_pomo or 0) or DEFAULT_ESTIMATE
    except (ValueError, TypeError):
        base = DEFAULT_ESTIMATE
    if factor is None:
        return base
    try:
        f = max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
    except (ValueError, TypeError):
        return base
    return max(1, round(base * f))


def plan_day(
    todos: list,
    today: str | None = None,
    hours: float = 6.0,
    factor: float | None = None,
) -> list:
    """Ordina i task attivi per la giornata con score, reasons e tagli.

    factor (da domain.calibration_factor): corregge le stime in capacita'
    senza riscriverle; i task stimati mostrano il motivo plan_calibrated."""
    today_d = _parse_day(today or "") or datetime.now().date()
    today_s = today_d.strftime("%Y-%m-%d")
    try:
        calib = (
            max(CAL_CLAMP_MIN, min(CAL_CLAMP_MAX, float(factor)))
            if factor is not None
            else None
        )
    except (ValueError, TypeError):
        calib = None
    try:
        capacity = max(0.0, float(hours)) / POMO_HOURS
    except (ValueError, TypeError):
        capacity = 0.0
    active = [t for t in todos if t.state == "attivo" and t.id is not None]
    stale_cache: dict[str, int | None] = {}
    scored: list[tuple] = []
    for t in active:
        score = 0
        reasons: list[tuple[str, dict]] = []
        due = _due_date_part(t.due)
        due_d = _parse_day(due) if due else None
        mandatory = False
        if due_d and due_d < today_d:
            score += OVERDUE_SCORE
            reasons.append(("plan_overdue", {}))
            mandatory = True
        elif due_d and due_d == today_d:
            score += DUE_TODAY_SCORE
            reasons.append(("plan_due_today", {}))
            mandatory = True
        elif due_d and (due_d - today_d).days == 1:
            score += DUE_TOMORROW_SCORE
            reasons.append(("plan_due_tomorrow", {}))
        score += PRIO_SCORES.get(t.priority, PRIO_SCORES[Priority.MEDIUM])
        if t.priority == Priority.HIGH:
            reasons.append(("plan_prio", {}))
        if t.project not in stale_cache:
            stale_cache[t.project] = _stale_days(t.project, todos, today_d)
        stale_n = stale_cache[t.project]
        if stale_n is not None:
            score += STALE_SCORE
            reasons.append(("plan_stale", {"n": stale_n}))
        planned = t.planned_for == today_s
        if planned:
            score += PLANNED_SCORE
            reasons.append(("plan_planned", {}))
        try:
            has_est = int(t.stima_pomo or 0) > 0
        except (ValueError, TypeError):
            has_est = False
        if calib is not None and has_est:
            reasons.append(("plan_calibrated", {"f": f"x{calib:.1f}"}))
        scored.append((t, score, reasons, mandatory))
    included: list[tuple] = []
    rest: list[tuple] = []
    skipped: list[tuple] = []
    used = 0
    for t, score, reasons, mandatory in scored:
        if getattr(t, "plan_skip", "") == today_s:
            skipped.append((t, score, [*reasons, ("plan_skipped", {})]))
        elif mandatory or t.planned_for == today_s:
            included.append((t, score, reasons))
            used += _estimate(t, calib)
        else:
            rest.append((t, score, reasons))
    rest.sort(key=lambda e: (-e[1], _due_date_part(e[0].due) or "9999", e[0].id))
    for t, score, reasons in rest:
        if used + _estimate(t, calib) <= capacity:
            included.append((t, score, reasons))
            used += _estimate(t, calib)
        else:
            included.append((t, score, [*reasons, ("plan_cut", {})]))
    skipped.sort(key=lambda e: (-e[1], _due_date_part(e[0].due) or "9999", e[0].id))
    included.sort(
        key=lambda e: (
            any(k == "plan_cut" for k, _p in e[2]),
            -e[1],
            _due_date_part(e[0].due) or "9999",
            e[0].id,
        )
    )
    return [(t.id, score, reasons) for t, score, reasons in [*included, *skipped]]
