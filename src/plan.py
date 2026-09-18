"""Pianificatore giornaliero deterministico (nessuna rete, nessuna AI).

Compatibilita': plan_day() delega al Planner (implementazione in
src/planner/: scoring, constraints, capacity, explain, models) e converte
il DayPlan in [(id, score, reasons)] via to_legacy(). Stesse regole,
stessi pesi, stesso formato [(id, score, reasons)] dove reasons e'
[(chiave_i18n, params), ...] pronta per T(chiave, **params) nella UI:

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
- factor None = auto-calibrazione via domain.calibration_factor (come il Planner).
"""

from src.planner.capacity import DEFAULT_ESTIMATE, POMO_HOURS
from src.planner.capacity import (
    estimate as _estimate,  # noqa: F401 (compat: usato da tests/test_plan.py)
)
from src.planner.scoring import (
    DUE_TODAY_SCORE,
    DUE_TOMORROW_SCORE,
    OVERDUE_SCORE,
    PLANNED_SCORE,
    PRIO_SCORES,
    STALE_DAYS,
    STALE_SCORE,
)
from src.planner.service import Planner

__all__ = [
    "DEFAULT_ESTIMATE",
    "DUE_TODAY_SCORE",
    "DUE_TOMORROW_SCORE",
    "OVERDUE_SCORE",
    "PLANNED_SCORE",
    "POMO_HOURS",
    "PRIO_SCORES",
    "STALE_DAYS",
    "STALE_SCORE",
    "Planner",
    "plan_day",
]


def plan_day(
    todos: list,
    today: str | None = None,
    hours: float = 6.0,
    factor: float | None = None,
) -> list:
    """Ordina i task attivi per la giornata con score, reasons e tagli.

    Wrapper compatibile: Planner.propose() -> DayPlan -> to_legacy()
    (factor None = auto-calibrazione).
    """
    return Planner(todos, today=today, hours=hours, factor=factor).propose().to_legacy()
