# ADR-001 — Planner come boundary esplicito, non libreria

- Stato: accettato (audit Fase 10, 2026-09-18).
- Contesto: il planning viveva in `src/plan.py` + logica sparsa in UI.
- Decisione: `src/planner/` è il boundary applicativo (scoring,
  constraints, capacity, scheduler, explain, decisions, replan); la UI
  consuma `DayPlan`/`ScheduledDayPlan`, mai gli stadi interni (guardrail
  `tests/test_arch.py`). `plan.py` resta wrapper compatibile.
- Non estrarre in pacchetto separato: nessun consumer esterno lo
  giustifica (costi di versioning/CI > benefici).
