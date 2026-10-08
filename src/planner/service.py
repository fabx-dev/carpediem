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
wall-clock (allowlisted in _resolve_day, rimozione rinviata alla fase
temporale/contrattuale). Tutti i caller di produzione passano valori
espliciti; il fallback copre solo compat (plan_day, test, script ad-hoc).
"""

from dataclasses import dataclass, replace
from datetime import date, datetime

from src.planner import calibration, capacity, constraints, scheduler, scoring
from src.planner.decisions import decide
from src.planner.diagnostics import diagnose
from src.planner.explain import CUT
from src.planner.models import (
    DayPlan,
    PlanItem,
    PlanningRequest,
    PlanningResult,
    ScheduledDayPlan,
    TaskView,
    todo_to_task,
)


@dataclass(frozen=True)
class _PlannerInput:
    """Forma di input normalizzata interna (Phase 1, privata, non esportata).

    Dimostra l'idea "un solo input in entrata" senza congelare il futuro
    contratto pubblico PlanningRequest (Phase 2+/7): giorno risolto,
    viste normalizzate, capacita' e factor. Costruita solo da TaskView,
    mai direttamente da TodoItem.
    """

    day: date
    today_s: str
    capacity_pomo: float
    factor: float | None
    views: tuple


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
            or datetime.now().date()  # allowlist Phase 1 (§6.0): fallback compat
        )

    def _normalize(self) -> _PlannerInput:
        """Risoluzione unica dell'input: giorno, viste, capacita', factor."""
        day = self._resolve_day()
        raw = (
            self.factor
            if self.factor is not None
            else calibration.factor_for(self.todos)
        )
        return _PlannerInput(
            day=day,
            today_s=day.strftime("%Y-%m-%d"),
            capacity_pomo=capacity.total(self.hours),
            factor=capacity.normalize_factor(raw),
            views=tuple(self.todos),
        )

    def propose(self) -> DayPlan:
        """Proposta giornaliera come DayPlan (planned/cut/skipped + capacita')."""
        inp = self._normalize()
        return _build_day_plan(
            list(inp.views), inp.day, inp.today_s, inp.factor, inp.capacity_pomo
        )

    @staticmethod
    def schedule(
        plan: DayPlan, availability, busy=(), deadlines=None
    ) -> ScheduledDayPlan:
        """Collocazione temporale di un DayPlan (thin wrapper a scheduler)."""
        return scheduler.schedule(plan, availability, busy, deadlines)


def _build_day_plan(views, day, today_s: str, calib, total) -> DayPlan:
    """Eleggibilita' → merito → selezione → DayPlan (coda condivisa).

    Unica implementazione usata da Planner.propose() e plan(): stessi pesi,
    stessi vincoli, stessa capacita', stesso ordinamento. Niente algoritmi
    qui, solo composizione degli stadi.
    """
    eligible = [t for t in views if constraints.is_eligible(t)]
    scored = scoring.score_all(eligible, list(views), day, today_s, calib)
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
        day=day,
        planned=planned_t,
        cut=tuple(cut),
        skipped=tuple(skipped_items),
        capacity_pomo=total,
        planned_pomo=sum(i.estimate_pomo for i in planned_t),
        factor=calib,
    )


def plan(request: PlanningRequest) -> PlanningResult:
    """Proposta + schedulazione + decisioni da un PlanningRequest (Phase 2).

    Via regia del domain core: compone gli stadi esistenti senza nuovi
    algoritmi (stessa coda di Planner.propose via _build_day_plan).
    - factor: esplicito dal request (None = non calibrato, mai auto qui).
    - scheduled: None senza availability (decisione ≠ schedulazione).
    - now (F0, contratto v2): vincolante — l'availability e' clippata al
      futuro [max(start, now), end] via time_model prima dello scheduling;
      a parita' di request stesso risultato, ma request con now diverso
      danno slot diversi (mai slot nel passato).
    - decisions: via decide() con request.sample_count (confidence anche
      None — regola invariata).
    - alternatives/diagnostics (Phase 6): osservabili additivi via
      diagnose(), mai decisionali.
    Contratto stabile v2 (docs/planner-api.md): pura e deterministica
    a parita' di request.
    """
    views = list(request.tasks)
    calib = capacity.normalize_factor(request.factor)
    dayplan = _build_day_plan(
        views,
        request.day,
        request.day.strftime("%Y-%m-%d"),
        calib,
        request.capacity_pomo,
    )
    avail = request.availability
    if request.now is not None:
        from src.planner.time_model import clip_future

        avail = tuple(clip_future(request.availability, request.now))
    scheduled = (
        scheduler.schedule(
            dayplan,
            avail,
            request.busy,
            scheduler.deadlines_for(views),
        )
        if request.availability
        else None
    )
    base = PlanningResult(
        request=request,
        plan=dayplan,
        scheduled=scheduled,
        decisions=decide(dayplan, views, sample_count=request.sample_count),
    )
    alternatives, diagnostics = diagnose(base)
    return replace(base, alternatives=alternatives, diagnostics=diagnostics)
