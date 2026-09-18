"""Application service Planner (Fase 2: orchestratore esplicito).

Pipeline: eleggibilita' (constraints) -> merito (scoring) -> selezione
(constraints + capacity) -> proposta [(id, score, reasons)] con motivi
prodotti da explain. Nessun algoritmo cambiato rispetto a plan_day():
stessi pesi, stessi vincoli, stessa capacita', stesso ordinamento.

Factor: None (omesso o esplicito) = auto-calibrazione via
domain.calibration_factor sui todos (la screen non conosce piu' la
calibration); valore esplicito = usato cosi' com'e' (normalizzato in
capacity). Su todos senza dati di calibrazione l'auto vale None.
"""

from datetime import datetime

from src.domain import calibration_factor
from src.models import TodoItem
from src.planner import capacity, constraints, scoring


class Planner:
    """Boundary applicativo e orchestratore della proposta giornaliera."""

    def __init__(
        self,
        todos: list[TodoItem],
        *,
        today: str | None = None,
        hours: float = 6.0,
        factor: float | None = None,
    ) -> None:
        self.todos = todos
        self.today = today
        self.hours = hours
        self.factor = factor

    def propose(self) -> list:
        """Proposta giornaliera: [(id, score, reasons)] come plan_day()."""
        today_d = scoring.parse_day(self.today or "") or datetime.now().date()
        today_s = today_d.strftime("%Y-%m-%d")
        raw = self.factor if self.factor is not None else calibration_factor(self.todos)
        calib = capacity.normalize_factor(raw)
        total = capacity.total(self.hours)
        eligible = [t for t in self.todos if constraints.is_eligible(t)]
        scored = scoring.score_all(eligible, self.todos, today_d, today_s, calib)
        candidates, skipped = constraints.partition(scored, today_s)
        included = capacity.allocate(
            candidates, today_s=today_s, capacity=total, calib=calib
        )
        return [(t.id, result, reasons) for t, result, reasons in [*included, *skipped]]
