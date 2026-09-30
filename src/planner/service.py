"""Application service Planner (Fase 3: produce un DayPlan esplicito).

Pipeline: eleggibilita' (constraints) -> merito (scoring) -> selezione
(constraints + capacity) -> DayPlan con motivi prodotti da explain. Nessun
algoritmo cambiato rispetto a plan_day(): stessi pesi, stessi vincoli,
stessa capacita', stesso ordinamento; cambia solo la forma del risultato.

Factor: None (omesso o esplicito) = auto-calibrazione via
domain.calibration_factor sui todos (la screen non conosce piu' la
calibration); valore esplicito = usato cosi' com'e' (normalizzato in
capacity). Su todos senza dati di calibrazione l'auto vale None.

Tempo (Phase 1, docs/planner-phase1-plan.md §6.0): risoluzione esplicita
prima — `today`, poi `now` (solo parte data) — poi fallback compat
`datetime.now()` (allowlisted qui, rimozione rinviata alla fase
temporale/contrattuale). Tutti i caller di produzione passano valori
espliciti; il fallback copre solo compat (plan_day, test, script ad-hoc).
"""

from datetime import date, datetime

from src.planner import calibration, capacity, constraints, scheduler, scoring
from src.planner.explain import CUT
from src.planner.models import (
    DayPlan,
    PlanItem,
    ScheduledDayPlan,
    TaskView,
    todo_to_task,
)


class Planner:
    """Boundary applicativo e orchestratore della proposta giornaliera."""

    def __init__(
        self,
        todos: list,
        *,
        today: str | date | datetime | None = None,
        hours: float = 6.0,
        factor: float | None = None,
        now: date | datetime | None = None,
    ) -> None:
        # Phase 1: normalizzazione unica al bordo — il core lavora solo su
        # TaskView; TodoItem resta accettato per compat (adapter permanente).
        self.todos = [t if isinstance(t, TaskView) else todo_to_task(t) for t in todos]
        self.today = today
        self.hours = hours
        self.factor = factor
        self.now = now

    def _resolve_day(self):
        """Giorno di pianificazione: today esplicito, poi now, poi fallback
        compat wall-clock (allowlisted Phase 1, docs/planner-phase1-plan.md
        §6.0: produzione sempre esplicita, rimozione in fase successiva)."""
        return (
            scoring.parse_day(self.today)
            or scoring.parse_day(self.now)
            or datetime.now().date()
        )

    def propose(self) -> DayPlan:
        """Proposta giornaliera come DayPlan (planned/cut/skipped + capacita')."""
        today_d = self._resolve_day()
        today_s = today_d.strftime("%Y-%m-%d")
        raw = (
            self.factor
            if self.factor is not None
            else calibration.factor_for(self.todos)
        )
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

    @staticmethod
    def schedule(plan: DayPlan, availability, busy=()) -> ScheduledDayPlan:
        """Collocazione temporale di un DayPlan (thin wrapper a scheduler)."""
        return scheduler.schedule(plan, availability, busy)
