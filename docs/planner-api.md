# Planner API v2 — superficie promessa e policy di compatibilità

> Stato: contratto stabile v2 da F0 time-aware (`PLANNER_CONTRACT_VERSION = 2`,
> vedi `docs/planner-phase7-plan.md` per v1). Questa pagina è vincolante: ogni
> cambio al contratto deve rispettarla o aggiornarla con bump deliberato.

## 1. Superficie promessa

Solo questi nomi sono stabili. Tutto il resto di `src/planner/` è
interno non versionato (usabile in-repo, mai promesso):

```text
plan(request) -> PlanningResult
PlanningRequest / PlanningResult
TaskView, DayPlan, PlanItem, ScheduledDayPlan, ScheduledItem,
TimeWindow, FixedEvent, PlanningDecision, PlanAlternative,
PlanDiagnostic, ExecutionFeedback
BLOCKED_* / BLOCKED_KINDS, DIAG_* / DIAG_KINDS, DETAIL_KEYS,
SCHEDULED / NOT_SCHEDULED / DEFERRED / CONSTRAINED,
PLANNER_CONTRACT_VERSION
```

Esplicitamente fuori: `Planner.propose()` (legacy), `replan()`,
`feedback()`, `observe_*`, `explain.*`, `todo_to_task`, scoring /
capacity / scheduler interni. `replan()` resta entry supportata ma con
semantica non congelata.

## 2. Uso minimo

```python
from datetime import date
from src.planner import PlanningRequest, plan

req = PlanningRequest(day=date(2026, 10, 2), tasks=todos, capacity_pomo=12.0)
res = plan(req)
res.plan.planned        # tuple[PlanItem, ...]
res.scheduled           # ScheduledDayPlan | None (None senza availability)
res.decisions           # tuple[PlanningDecision, ...]
res.alternatives        # tuple[PlanAlternative, ...] (solo blocchi osservati)
res.diagnostics         # tuple[PlanDiagnostic, ...] (solo fatti veri)
```

Regole d'uso: `day` invalido = `ValueError` subito (mai piano spostato
silenziosamente); `plan()` è pura e deterministica a parità di request;
`scheduled` è `None` senza `availability` (decisione ≠ schedulazione);
`request.now` è vincolante (v2): con `now` l'availability è clippata al
futuro `[max(start, now), end]` prima dello scheduling — a parità di giorno
ma con `now` diverso gli slot cambiano (mai slot nel passato).

## 3. Consumer in-repo dichiarati (P7-3)

- Via `plan()`: `PlanProposalScreen` (Buongiorno), `scheduled_for_today()`,
  Why-card (`plan_decisions()` in `views.py`).
- Usi interni dichiarati (non promessi, corretti): `Planner.schedule()`
  statico per ri-schedulare DayPlan esistenti a rendering
  (`screens/plan.py`, la selezione confermata non va ri-proposta);
  `diagnose()` per arricchire sub-DayPlan a rendering; `replan()` per
  `ReplanPreviewScreen` + CLI (semantica non congelata, vedi §1);
  `feedback()` per il briefing sera (osservazione).
- `Planner.propose()` resta solo dentro `replan.py` + wrapper legacy
  `src/plan.py` (zero consumer produzione, solo test): nessuna migrazione
  richiesta, nessuna deprecazione in v1.

## 4. Policy di compatibilità

- Campi dataclass solo **aggiunti in coda con default**; mai rimossi o
  rinominati senza bump del contratto.
- Classi restano `frozen=True`; campi pubblici `tuple`, mai `list`.
- Costruzione sempre possibile da kwargs con soli obbligatori
  (`day` per Request; `request` + `plan` per Result).
- Nuovi `kind` nei vocabolari chiusi = compatibile; i consumer devono
  gestire gli ignoti con fallback (come fa la UI via `phrase_for`).
- Bump di `PLANNER_CONTRACT_VERSION` solo su cambio breaking deliberato,
  mai silenzioso; indipendente dalla versione package.
