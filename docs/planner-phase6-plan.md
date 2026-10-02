# Phase 6 — Explainability: implementation plan

*(Stesura in build mode, ma SOLO piano: nessuna modifica a codice/test in
questa sessione. Verificato contro il repo post-Phase 5 (P5-4, CI verde).
Riferimenti: `docs/planner-engine.md` §16 Phase 6 + §12 (explainability),
`docs/planner-phase5-plan.md`, `docs/adr-001-planner-boundary.md`
(invariato), `AGENTS.md` §9.)*

---

## 1. Executive summary

Phase 5 ha chiuso sofisticazione e proprietà del core. Phase 6 fa il passo
previsto da `planner-engine.md` §16:

> **Decisions observable as decision / reason / constraint / alternative /
> diagnostic (§12).**

Stato onesto (`CURRENT`): decisione, motivo, evidence e story esistono e
sono renderizzati nella Why-card; **manca l'osservabile "perché no"**:
alternative scartate e diagnostica di piano vivono solo come assenza
(task non in lista, slot vuoti). Phase 6 li rende dati strutturati nel
core (`PlanningResult`), con UN rendering minimo in Why-card. Niente
motore diagnostico generico, niente seconde opinioni sullo scoring.

## 2. Punto di partenza (verificato)

- `PlanningDecision`: decisione/motivi/evidence/confidence; `decide()` +
  `refine_with_schedule()` + `primary_reason()`; narrative a chiavi i18n.
- `PlanningResult`: `request/plan/scheduled/decisions` (campi U1).
- Why-card (`views.py::_why_lines`): etichetta decisione + story + sezione
  Dettagli (due/priorità/score/stima/capacità) + motivo + confidence +
  `why_alt_deferred` per DEFERRED. Invariante strutturale: fra etichetta e
  `why_sec_details` esattamente una riga (la story) — il blocker va in
  CODA, mai in mezzo.
- Parità chiavi it/en imposta da `test_parita_chiavi`: ogni chiave nuova
  in entrambe le lingue.
- `plan_decisions()` in views.py: 3 caller precalcolano + fallback Detail.

## 3. Decisioni (trade-off espliciti)

### X-What: alternative per i non-collocati, diagnostica per il piano

Raccomandazione: due frozen dataclass in `models.py`:

```python
@dataclass(frozen=True)
class PlanAlternative:
    todo_id: int
    decision: str      # NOT_SCHEDULED | DEFERRED | CONSTRAINED | SCHEDULED
    blocked_by: str    # user_skip | capacity | deadline | busy | window | duration
    detail: dict       # solo fatti a vocabolario chiuso DETAIL_KEYS

@dataclass(frozen=True)
class PlanDiagnostic:
    kind: str          # overflow | constrained_mandatory | empty_availability
    detail: dict       # conteggi/id, mai testo, mai interpretazioni
```

Semantica vincolante (revisione): `PlanAlternative` è informazione
diagnostica su un candidato escluso/non collocato — NON un piano
alternativo, NON un'alternativa completa, NON un modello da estendere
senza decisione architetturale esplicita. `blocked_by` = PRIMO blocco
deterministico osservato (vedi X-Probe), MAI "unica causa possibile".

- Chi le riceve: cut → (NOT_SCHEDULED, capacity); skipped →
  (DEFERRED, user_skip); unscheduled (mandatory e no) → probe §4
  (decision resta SCHEDULED/CONSTRAINED come oggi — l'alternativa spiega
  il blocco osservato, non ridecide); scheduled → nessuna (niente scarto).
- Senza tentativo di scheduling (`scheduled=None`) le planned NON
  generano alternative (nessun blocco osservabile: l'assenza di scheduling
  è una fase, non un difetto — correzione P6-2).
- Diagnostica solo se vera: overflow (`planned_pomo > capacity_pomo`),
  mandatory-constrained (count+ids), scheduling tentato con availability
  vuota. Tuple vuote altrimenti. Niente soglie inventate, niente severity.

### X-Probe: il blocco si dimostra per esclusione, deterministicamente

Raccomandazione: per voce unscheduled, probe single-item via
`scheduler.schedule` esistente (nessun algoritmo nuovo), primo-match in
ordine documentato:

1. `duration`: non entra nemmeno in [giorno intero, no busy, no deadline]
   → oltre la giornata.
2. `deadline`: entra togliendo solo la deadline → la scadenza.
3. `busy`: entra togliendo solo i busy → gli impegni.
4. `window`: entra da solo in ideale ma non in gara → finestra residua
   insufficiente (competizione first-fit persa).

Totale, puro, deterministico, economico (≤3 schedule single-item a voce;
N piccolo). Ordine documentato nel docstring (doppio blocco = primo in
lista, mai euristica nascosta). Regola controfattuale: un blocco si
dichiara solo se presente E se toglierlo da solo abilita il fit
(deadline senza orario o busy vuoto non scattano mai — probe vacue
vietate). Invariante: una probe non produce mai un esito diverso dallo
scheduler reale (divergenza = difetto diagnostico; lo scheduler resta
l'unica autorità decisionale).

### X-Where: `diagnose(result)`, popolato da `plan()`

Raccomandazione: nuovo `src/planner/diagnostics.py` (~120 righe,
giustificato: capacità nuova con consumer reale, non helper da 30 righe)
con `diagnose(result) -> (alternatives, diagnostics)`; `plan()` lo
chiama e riempie i nuovi campi `PlanningResult.alternatives/diagnostics`
(default `()`). `replan()` invariato (ha già motivi/primary; alternative
nel proposal = non-goal). `decide()`/`refine` invariati.

### X-UI: una riga in coda alla Why-card, niente di più

Raccomandazione: `DetailScreen(alternatives=None)` opzionale (default =
rendering odierno, zero rotture); `plan_context()` nuovo in views.py
(single `plan()` → `(decisions, {todo_id: alternative})`) adottato dai 3
caller precalcolanti; `plan_decisions` resta (compat + fallback senza
blocker — degrado documentato). Rendering: riga `why_blocked_*` DOPO
confidence/alt (invariante story intatta); 6 chiavi it/en
(capacity/deadline/busy/window/duration/user_skip); per DEFERRED nessuna
riga (coperta da `why_alt_deferred` esistente). Narrative invariata
(la story resta naturale, il blocker è etichetta fattuale).

## 4. Casistica (da fissare in test)

| voce | esito atteso |
|---|---|
| cut per capacità | (NOT_SCHEDULED, capacity, {estimate_pomo}) |
| skipped oggi | (DEFERRED, user_skip, {}) |
| unscheduled oltre-giornata (50🍅 in 8h) | (…, duration, {needed_min}) |
| unscheduled per scadenza (P3-2 golden) | (…, deadline, {deadline, needed_min}) |
| unscheduled per busy (buco dopo mai) | (…, busy, {needed_min}) |
| unscheduled per gara persa (entra da solo, rivali sullo slot) | (SCHEDULED, tasks, {task_ids}) — nomi risolti in UI |
| unscheduled per finestra corta assoluta (neanche da solo) | (SCHEDULED, window, {needed_min}) |
| overflow (mandatory sforano) | diagnostic overflow {planned, capacity, over} |
| mandatory senza slot | diagnostic constrained_mandatory {count, ids} |
| scheduling tentato con availability vuota | diagnostic empty_availability (+ window a testa, + constrained se mandatory) |
| tutto collocato | alternatives == () e diagnostics == () |

## 5. Sequenza (un commit per step)

1. **P6-1 — Tipi**: `PlanAlternative`/`PlanDiagnostic` in models.py +
   campi `PlanningResult` (+ U-test forma/frozen/liste esatte).
2. **P6-2 — Probe**: `diagnostics.py` `diagnose()` + golden §4 (solo test
   nuovi + modulo nuovo; nessun consumer ancora).
3. **P6-3 — Facade**: `plan()` popola i campi (E1 rieseguita: campi vecchi
   identici) + T9 export (`diagnose`, tipi).
4. **P6-4 — UI minima**: `plan_context`, `DetailScreen(alternatives)`,
   6 chiavi it/en, riga in coda + pilot + parità; `plan_decisions` intatta.
5. **P6-5 — Guard + docs**: G5 — `diagnose` unica costruttrice di
   alternative/diagnostics (grep: nessun altro modulo li costruisce);
   docstring pipeline aggiornata.
6. **P6-6 — Gate + reviewer**: full + ruff + format + mypy + `@reviewer`,
   nessuna release (osservabilità interna + 1 riga UI di nicchia).

## 6. Non-goals (Phase 6 NON implementa)

- niente framework diagnostico (severity, codici v2, aggregazioni oltre §4);
- niente narrative per i blocker (factual label, non story);
- niente alternative nel `ReplanProposal` (motivi esistenti bastano);
- niente rescoring/reranking nelle probe (solo schedule esistente);
- niente chiavi oltre le 6 blocker; niente altre screen oltre Detail;
- niente stabilizzazione API (Phase 7), bump/release di default.

## 7. Definition of Done (rivista per le garanzie semantiche)

1. Diagnostica additiva: selezione, ordine, capacità, scheduling, motivi,
   replan identici (E1 + suite verdi).
2. Decisioni esistenti invariate.
3. Determinismo: stesso input → stesso output (incl. ordine tuple).
4. Le probe riusano lo scheduler esistente; coerenza probe≡scheduler
   verificata per riga golden; "blocker" = primo blocco osservato, mai
   causa unica (D4 multi-blocco esplicito).
5. Le probe non sono autorità alternativa (invariante §X-Probe).
6. UI minima e sicura: riga in coda, invariante story intatta, fallback
   intatto (`plan_decisions` invariata).
7. Fallback senza contesto diagnostico come prima.
8. Nessuna architettura Phase 7/8 (niente API stabili, versioning,
   package, REST/MCP, constraint engine indipendente).
9. Guard G5 + full gate + `@reviewer` OK; ADR-001 intatto; zero dipendenze;
   AGENTS.md/CHANGELOG solo se convenzione; nessuna release di default.

## 8. Rischi

| Rischio | Mitigazione |
|---|---|
| Probe costose su piani grandi | ≤3 schedule single-item solo per unscheduled (pochi per costruzione); perf-test invariato |
| Doppio blocco ambiguo | ordine probe documentato e pinnato; primo-match deterministico |
| Detail senza contesto (fallback) | degrado documentato: niente riga senza alternatives |
| Tentazione severity/taxonomy | vietato in review (6 kind chiusi, nuovi solo con consumer) |
| Blocker duplicato per DEFERRED | regola esplicita: deferred usa `why_alt_deferred`, mai riga blocker |

## Appendice — evidenze

- `decisions.py` riletto (182 righe: decide/refine/primary invariati in P6).
- Why-card riletta (`views.py:1315-1386`): invariante story documentata.
- Chiavi `why_*` censite (it + en, parità automatica).
- `plan_decisions`: 3 caller + fallback (migrazione a `plan_context` meccanica).
- `PlanningResult` da estendere (campi U1); E1 confronta per-campi (sicuro).
