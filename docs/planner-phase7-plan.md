# Phase 7 — Public Planner API: implementation plan

*(Stesura in build mode, ma SOLO piano: nessuna modifica a codice/test in
questa sessione. Verificato contro il repo post-phrases (`4b4eee3`, suite
873 verdi). Riferimenti: `docs/planner-engine.md` §16 Phase 7 + §13
(public API vision), `docs/planner-phase6-plan.md`,
`docs/adr-001-planner-boundary.md` (invariato), `AGENTS.md` §9.)*

---

## 1. Executive summary

Phases 1–6 hanno chiuso il core (dominio, temporale, vincoli, stima,
spiegabilità) + il contratto phrases. Phase 7 fa il passo previsto da
`planner-engine.md` §16:

> **Stabilize `PlanningRequest`, `PlanningResult`, `Planner`; define
> compatibility and versioning (§13).**

Stato onesto (`CURRENT`): `plan(request) → PlanningResult` esiste e gira
in produzione via adapter app-side; `PlanningRequest`/`PlanningResult`
portano ancora il marchio **INSTABILE** (`models.py:273-275`,
`service.py:179`); nessuna versione di contratto, nessuna policy di
compatibilità scritta, nessun test che congeli la superficie pubblica.
Phase 7 dichiara stabile il contratto v1 **senza cambiare algoritmi né
diagnostica**: congela campi/firme, aggiunge versione, scrive la policy,
estende i guardrail. Niente package separato (resta Phase 8, ADR-001
invariato), niente REST/MCP, niente nuovi stadi.

## 2. Punto di partenza (verificato)

- `plan(request: PlanningRequest) -> PlanningResult` (`service.py:168`):
  compone `_build_day_plan` + `schedule` + `decide` + `diagnose()`; usata
  in produzione? — verificare call-site (adapter in `app.py`?
  `build_planning_request`?). Legacy `Planner.propose()` resta per il path
  Buongiorno; `replan()` resta entry separata.
- `PlanningRequest`: `day/tasks/capacity_pomo/factor/availability/busy/now/
  sample_count` con normalizzazione in `__post_init__` (fail-fast su day
  invalido — proprietà da preservare).
- `PlanningResult`: `request/plan/scheduled/decisions/alternatives/
  diagnostics` (tutti tuple/frozen, JSON-amichevoli tranne `request` eco).
- Superficie pubblica: `src/planner/__init__.py` `__all__` (~50 nomi,
  include interni come `todo_to_task`, `story_keys`, `deadlines_for`).
- Guardrail esistenti: `tests/test_arch.py` (niente second planner in UI,
  purezza), `test_planner_contract.py`, `test_planner_fixtures.py`
  (equivalenza), `test_planner_perf.py` (baseline).

## 3. Decisioni (trade-off espliciti)

### X-Scope: solo il percorso `plan()`, non tutto `__all__`

Raccomandazione: la promessa di stabilità copre ESATTAMENTE
`PlanningRequest`, `PlanningResult`, `plan()`, più i tipi che li
compongono (`TaskView`, `DayPlan`, `ScheduledDayPlan`, `PlanningDecision`,
`PlanAlternative`, `PlanDiagnostic`, `TimeWindow`, `FixedEvent`,
vocabolari `BLOCKED_*/DIAG_*/DETAIL_KEYS`). Tutto il resto di `__all__`
(`Planner.propose`, `replan`, `feedback`, `observe_*`, `explain.*`,
`todo_to_task`, scoring/capacity/scheduler interni) resta **interno non
versionato**: usabile in-repo, mai promesso. Motivo: promettere 50 nomi
congelerebbe anche gli stadi interni, contro §17 (niente astrazioni
premature). `replan()` entra in v1 solo come firma, non come semantica
congelata? — **No**: fuori scope, resta interno (ha path CLI suo).

### X-Version: costante indipendente, non versione package

Raccomandazione: `PLANNER_CONTRACT_VERSION = 1` in `models.py`
(costante, testata), indipendente da `pyproject` `0.18.4`. Motivo: il
contratto evolve a ritmo diverso dall'app; legarlo al package lo
renderebbe bugiardo a ogni release UX. Bump solo su cambio breaking
deliberato (mai silenzioso).

### X-Compat: additivo, frozen, kwargs

Policy v1 (da scrivere in `docs/planner-api.md`, nuovo file breve):

- campi dataclass solo **aggiunti in coda con default** (costruzione
  posizionale esistente mai rotta); mai rimossi/rinominati senza bump
  major del contratto;
- classi restano `frozen=True`; `tuple`, mai `list`, nei campi pubblici;
- costruzione sempre possibile da kwargs con soli campi obbligatori
  (`day` per Request; `request`+`plan` per Result);
- nuovi `kind` nei vocabolari chiusi = compatibile (consumer devono
  gestire ignoti con fallback, come fa già la UI);
- `plan()` pura e deterministica a parità di request (stessa regola §3);
- `__post_init__` fail-fast su `day` invalido = comportamento congelato.

### X-What: quattro step, zero algoritmi

- **P7-1 — Versione + policy scritta**: `PLANNER_CONTRACT_VERSION = 1`,
  `docs/planner-api.md` (superficie promessa, policy, esempi minimi),
  docstring INSTABILE → STABILE v1. Solo scrittura, zero logica.
- **P7-2 — Freeze test**: `tests/test_planner_api.py` (nuovo): `__all__`
  promesso ⊆ `__all__` reale; firme `plan()`/`PlanningRequest`/
  `PlanningResult` (campi, default, ordine); costruzione kwargs minima;
  `frozen` su tutte le classi promesse; `KeyError`-free su kind noti?
  (no — quello vive già in phrases). Niente fixture di equivalenza nuove
  (la matrice esiste).
- **P7-3 — Adapter unico**: verificare che TUTTI i consumer in-repo
  passino per `plan()` o dichiarino perché no (legacy `propose()` in
  Buongiorno: migrare o documentare come debito con issue). Se la
  migrazione tocca algoritmi → fermarsi e ridiscutere (fuori scope).
- **P7-4 — Chiusura**: `planner-engine.md` §16 Phase 7 → `CURRENT`
  (solo la riga, come da regola §16), `CHANGELOG` voce, bump minor?
  (contratto stabile = feature architetturale → sì, `0.19.0` via release
  commit separato secondo convenzione).

## 4. Non-obiettivi (vincolanti)

Niente serializzazione JSON ufficiale (i tipi sono semplici ma nessun
formato è promesso in v1); niente `planner.replan(request)` unificato;
niente package/versione PyPI separata; niente deprecazione del legacy
`Planner.propose()` (solo censimento); niente timezone/DST (Phase 3 ha
chiuso la policy: naive-in-zona ai bordi).

## 5. Definition of Done

- `PLANNER_CONTRACT_VERSION` esiste ed è testata;
- `docs/planner-api.md` descrive superficie + policy + esempi;
- `tests/test_planner_api.py` congela campi/firme/frozen/kwargs;
- suite completa + ruff + mypy verdi; zero divergenze equivalenza;
- `planner-engine.md` aggiornato (una riga), CHANGELOG voce;
- nessun algoritmo toccato (diff solo modelli/doc/test/adapter
  dichiarato).
