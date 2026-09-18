"""Application service Planner (Fase 3: produce un DayPlan esplicito).

Pipeline: eleggibilita' (constraints) -> merito (scoring) -> selezione
(constraints + capacity) -> DayPlan con motivi prodotti da explain. Nessun
algoritmo cambiato rispetto a plan_day(): stessi pesi, stessi vincoli,
stessa capacita', stesso ordinamento; cambia solo la forma del risultato.

Factor: None (omesso o esplicito) = auto-calibrazione via
domain.calibration_factor sui todos (la screen non conosce piu' la
calibration); valore esplicito = usato cosi' com'e' (normalizzato in
capacity). Su todos senza dati di calibrazione l'auto vale None.
"""

from datetime import datetime

from src.domain import calibration_factor
from src.models import TodoItem
from src.planner import capacity, constraints, scoring
from src.planner.explain import CUT
from src.planner.models import DayPlan, PlanItem


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

    def propose(self) -> DayPlan:
        """Proposta giornaliera come DayPlan (planned/cut/skipped + capacita')."""
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
        planned: list[PlanItem] = []
        cut: list[PlanItem] = []
        for t, result, reasons, mandatory in included:
            assert t.id is not None  # garantito da is_eligible
            item = PlanItem(
                t.id,
                result,
                tuple(reasons),
                capacity.estimate(t, calib),
                mandatory,
            )
            if any(k == CUT for k, _p in reasons):
                cut.append(item)
            else:
                planned.append(item)
        skipped_items = []
        for t, result, reasons, mandatory in skipped:
            assert t.id is not None  # garantito da is_eligible
            skipped_items.append(
                PlanItem(
                    t.id,
                    result,
                    tuple(reasons),
                    capacity.estimate(t, calib),
                    mandatory,
                )
            )
        planned_t = tuple(planned)
        return DayPlan(
            day=today_d,
            planned=planned_t,
            cut=tuple(cut),
            skipped=tuple(skipped_items),
            capacity_pomo=total,
            planned_pomo=sum(i.estimate_pomo for i in planned_t),
            factor=calib,
        )
