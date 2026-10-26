# CarpeDiem — Architectural Roadmap

> Spostato da AGENTS.md §9 il 2026-10-26. Fasi 0-10 completate; i principi
> (§9.5) e le regole per il Planner (§9.7) restano vincolanti e sono riassunti in `AGENTS.md`.

## 9. Architectural Roadmap

> Riferimento operativo per le sessioni future. **Evolvere CarpeDiem, non
> riscriverlo. Rendere esplicita l'architettura che il progetto possiede già,
> quindi evolverla per piccoli passi verificabili.**
>
> **NON implementare le fasi future di questa roadmap se non nel corso della
> loro fase.** Ogni fase ha un criterio di completamento esplicito; saltare
> fasi richiede una motivazione tecnica documentata (vedi §9.10).

### 9.1 Visione architetturale

L'obiettivo non è creare un prodotto separato: CarpeDiem deve evolvere
mantenendo il prodotto esistente e rendendo progressivamente più esplicita la
sua architettura.

```text
                    CarpeDiem
                        │
        ┌───────────────┼────────────────┐
        │               │                │
      Tasks           Planner          Execution
        │               │                │
        │               │                ├── Pomodoro
        │               │                ├── Actual time
        │               │                └── Review
        │               │
        │               ├── priorities
        │               ├── deadlines
        │               ├── capacity
        │               ├── constraints
        │               ├── availability
        │               └── scheduling
        │
        └──────────────────────────────────┘
```

Visione a lungo termine: trasformare il Planner da semplice sistema di
ranking delle attività a **motore deterministico di pianificazione temporale
della giornata**.

Sequenza concettuale desiderata:

```text
capture → tasks → estimate → plan → schedule → execute → measure
   → review → calibrate → better planning
```

Il sistema deve restare: **local-first, offline-first, deterministico,
spiegabile, testabile, controllabile dall'utente**. Nessuna AI/LLM come
prerequisito architetturale (zero rete nel planning).

### 9.2 Stato attuale (da non confondere con la roadmap)

Il planning esiste già in `src/carpediem/plan.py` (`plan_day(todos, today, hours,
factor)`, funzione pura, niente I/O/UI). Considera già: deadline, scaduto,
oggi/domani, priorità, progetti fermi (`STALE_DAYS`), task già pianificati
(`planned_for`), capacità giornaliera (`hours` → pomodori da 0.5h), stime
`stima_pomo` (default 1), calibrazione (`factor` da `domain.calibration_factor`,
clamp 0.5–3.0), scartati (`plan_skip`), mandatori (scaduti/oggi mai tagliati),
motivi `(chiave_i18n, params)` per ogni decisione.

Modello attuale (NON è ancora uno scheduler temporale):

```text
tasks → scoring → ordering → capacity → ranked proposal
```

I motivi (`plan_*`) sono già spiegabili e consumati da `PlanProposalScreen`.
`plan_day` è un wrapper compatibile che delega a `Planner.propose()`
(`src/carpediem/planner/service.py` orchestra scoring → constraints → capacity, motivi
da `explain`) e converte il `DayPlan` in formato legacy via `to_legacy()`;
`DailyPlanScreen` e `ReviewScreen` lavorano su
`planned_for` senza passare dal planner. Il flusso di conferma è già
"propone → l'utente rivede → conferma" (additivo, vedi `planp_additive`).

Evoluzione futura (non ancora implementata):

```text
tasks → scoring → constraints → availability → scheduling → time blocks
```

### 9.3 Fasi della roadmap

Le fasi sotto sono progressive. Ognuna ha criterio di completamento e regole
proprie. **Non implementare le fasi future** (vedi §9.10).

#### Phase 0 — Baseline e comprensione

Obiettivo: comprendere e stabilizzare l'architettura esistente prima di
modificarla.

Attività: mappare il flusso task → planning → execution → review; identificare
le responsabilità di `app.py`, `domain.py`, `plan.py`; comprendere
`PlanProposalScreen` e `DailyPlanScreen`; verificare la suite di test;
documentare i comportamenti esistenti (sprint log, §9.2).

Regola: **non refactorizzare solo perché un componente è grande.** Prima
comprendere il contratto esistente.

#### Phase 1 — Explicit Planner boundary

Prima fase operativa. Obiettivo: creare un application/service boundary
`Planner` attorno alla logica già esistente.

```text
PlanProposalScreen → Planner → plan_day()
```

- Il Planner inizialmente **delega** a `plan_day()`.
- Non modificare l'algoritmo. Non modificare il comportamento. Non introdurre
  ancora un nuovo modello di scheduling.

Criterio di completamento:

- esiste un `Planner` chiaramente identificabile;
- il flusso applicativo lo utilizza;
- i risultati sono equivalenti a quelli precedenti;
- i test esistenti continuano a passare;
- esistono test del nuovo boundary.

#### Phase 2 — Separare scoring, vincoli e capacità

Obiettivo: evolvere gradualmente il Planner da wrapper a vero application
service.

```text
Planner
 ├── scoring
 ├── constraints
 ├── capacity
 └── explanations
```

- **Scoring**: quanto è importante/opportuno pianificare una task.
- **Hard constraints**: condizioni che non possono essere violate (deadline,
  task già conclusa, eventi fissi, disponibilità, dipendenze quando applicabili).
- **Soft constraints**: preferenze sacrificabili (priorità, equilibrio,
  contesto, preferenze temporali, continuità).
- **Capacity**: quanto lavoro è realisticamente pianificabile nella giornata.
- **Explanation**: perché una task è stata proposta, esclusa o spostata.

Regola fondamentale: **non modificare contemporaneamente scoring, vincoli e
UI.** Ogni estrazione deve avere test propri.

#### Phase 3 — Esplicitare il modello `DayPlan`

Obiettivo: introdurre un modello di dominio/applicazione esplicito per il
risultato del Planner.

```text
DayPlan
 ├── scheduled_blocks
 ├── unscheduled_tasks
 ├── conflicts
 └── warnings
```

Deve distinguere: cosa è pianificato, cosa no, perché no, quali vincoli sono
presenti, quali avvisi mostrare all'utente. Non serve ancora uno scheduler
complesso: prima un modello stabile.

#### Phase 4 — Temporal scheduling

Obiettivo: da lista ordinata a vero piano temporale.

```text
Task A / Task B / Task C            →            09:00–10:30  Task A
                                                 10:30–11:00  Task B
                                                 11:00–12:00  Task C
```

Introdurre progressivamente: `Availability`, `TimeWindow`, `ScheduledBlock`,
`FixedEvent`. Il planner deve considerare: orario di lavoro/disponibilità,
durata stimata, intervalli, eventi fissi, deadline, preferenze temporali.
Lo scheduler deve essere deterministico, riproducibile, spiegabile, testabile:
**a parità di input lo stesso risultato.**

#### Phase 5 — Pomodoro ed execution feedback

L'integrazione Pomodoro esiste già; evoluzione:

```text
estimated time → scheduled time → actual execution → measured time
```

Il Planner potrà usare dati reali di esecuzione. Distinguere sempre e non
confondere: **estimate / scheduled duration / actual duration**. Il Pomodoro
non deve diventare il modello fondamentale del Planner: è uno strumento di
execution/measurement che fornisce dati al sistema di pianificazione.

#### Phase 6 — Calibration e feedback loop

```text
estimate → schedule → execute → actual → calibration → future estimate
```

La calibrazione esiste già (`domain.calibration_factor`, `record_actual`,
`actual_pomo/actual_minutes`, clamp 0.5–3.0, minimo 5 campioni). La futura
evoluzione deve preservarla e renderla più esplicita.

Principio: **il sistema deve imparare dalle misurazioni senza diventare
opaco.** Qualsiasi modifica automatica alle stime deve essere spiegabile
all'utente (già: motivo `plan_calibrated`).

#### Phase 7 — Calendar e fixed events

Integrare nel planning gli impegni non rappresentati come task.

```text
Task / FixedEvent / Availability / Calendar

09:00–10:00 Task A
10:00–11:00 Meeting
11:00–12:30 Task B
```

Il calendario va trattato come **vincolo temporale del Planner**, non come
semplice schermata UI. La logica di scheduling non deve dipendere da Textual.

#### Phase 8 — External task sources

Solo dopo aver stabilizzato il Planner interno valutare integrazioni esterne
(Taskwarrior, Todoist, altri).

```text
External Source → Adapter → CarpeDiem Planner → DayPlan
```

Il Planner non deve conoscere le API dei provider esterni: le integrazioni
sono adapter/infrastructure concerns. **Non introdurre integrazioni esterne
prima che il core Planner sia stabile.**

#### Phase 9 — UI come consumer del Planner

```text
                 Planner
                    ↓
                 DayPlan
                    ↓
       ┌────────────┼────────────┐
       ↓            ↓            ↓
 PlanProposal    Agenda       Calendar
```

La UI deve visualizzare, consentire modifiche, mostrare spiegazioni, chiedere
conferma, avviare execution. **Non deve decidere autonomamente le regole di
scheduling.**

#### Phase 10 — Eventuale estrazione del Planner (opzionale)

```text
carpediem-planner
       ↑
    CarpeDiem (TUI, storage, Pomodoro, calendar)
```

Solo quando il core sarà maturo e riutilizzabile. **Non creare una libreria
separata per motivi estetici o teorici.**

### 9.4 Architettura target (direzione, non requisito immediato)

```text
src/
├── domain/
│   ├── task
│   ├── planning
│   └── timing
├── planner/
│   ├── service
│   ├── scoring
│   ├── constraints
│   ├── scheduler
│   └── explain
├── storage/
├── integrations/
│   ├── calendar
│   └── external_tasks
└── screens/
```

**Questo layout è un target, non lo stato attuale né un requisito immediato.**
Preferire evoluzioni incrementali a una migrazione big-bang.

### 9.5 Principi architetturali obbligatori

- **9.5.1 Behavior preservation**: prima preservare il comportamento, poi
  migliorarlo. Ogni cambiamento architetturale accompagnato da test.
- **9.5.2 Small steps**: `small refactor → tests → verify → next refactor`,
  mai `big rewrite → hope tests catch everything`.
- **9.5.3 No premature abstraction**: non creare classi/protocolli/moduli solo
  perché potrebbero servire in futuro; un'astrazione deve risolvere un
  problema reale presente nel codice.
- **9.5.4 Determinism**: a parità di `tasks/today/availability/calendar/
  preferences/configuration` il Planner produce lo stesso risultato. Eccezioni
  deliberate esplicite e testate.
- **9.5.5 Explainability**: ogni decisione significativa spiegabile
  (es. `scheduled because deadline is today`, `deferred because daily
  capacity is exhausted`, `excluded because task is completed`, `moved
  because fixed event occupies this interval`). Niente decisioni opache.
- **9.5.6 User control**: il Planner propone, non impone
  (`Planner proposes → User reviews → User confirms/modifies → Plan becomes
  active`); l'utente deve poter correggere il piano.
- **9.5.7 UI independence**: la logica di planning non dipende da Textual o
  dalle schermate; la UI può consumare il Planner, non il contrario.
- **9.5.8 Domain/application/infrastructure separation**: separazione sempre
  più chiara `Domain → Application services → Infrastructure/UI`. Evitare che:
  storage contenga decisioni di business, UI contenga algoritmi di planning,
  planner conosca Textual, integrazioni esterne penetrino nel dominio.

### 9.6 Regole per `app.py`

`src/carpediem/app.py` è la god-class nota (~2570 righe, 166 funzioni). **Non è
richiesto riscriverlo ora, e non fare una mega-refactor.**

```text
app.py → gradualmente delega → application services
```

Estrarre una responsabilità alla volta, quando esiste un boundary chiaro e
testabile. La regola del §4 vale: prima il contratto, poi l'estrazione.

### 9.7 Regole per il Planner

Ogni futura modifica al Planner deve rispondere a queste domande — se non
riesce a rispondere chiaramente, fermarsi e chiarire il design prima di
implementare:

1. Qual è l'input?
2. Qual è l'output?
3. Quali sono gli hard constraints?
4. Quali sono i soft constraints?
5. Qual è la funzione di scoring?
6. Il risultato è deterministico?
7. È spiegabile?
8. È testabile senza UI?
9. Come interagisce con la capacità disponibile?
10. Come interagisce con actual time e calibration?

### 9.8 Regole sui test

Ogni fase deve aumentare la copertura dei contratti del Planner. Il core deve
essere testabile senza avviare Textual. Distinguere almeno: **unit test,
integration test, UI test** (pattern esistente: `test_plan.py` puro vs
`test_plan_ui.py`/`test_plan_operate.py` pilot).

Verificare soprattutto: determinismo, deadline, priority, capacity, estimates,
calibration, skipped tasks, mandatory tasks, conflicts, availability, fixed
events, scheduling, explanations.

**Non eliminare test esistenti per rendere più semplice un refactoring.**

### 9.9 Definition of Done per ogni fase

Una fase è conclusa solo quando:

- il codice implementato è coerente con l'architettura;
- i test esistenti passano;
- sono stati aggiunti i test necessari;
- non sono state introdotte regressioni note;
- il comportamento è documentato;
- eventuali trade-off sono documentati;
- le fasi successive non sono state implementate prematuramente.

### 9.10 Regola fondamentale per gli agenti futuri

> **Non saltare fasi della roadmap senza una motivazione tecnica esplicita.**

In particolare:

- non trasformare Phase 1 in una riscrittura del Planner;
- non introdurre temporal scheduling prima di aver stabilizzato il boundary;
- non introdurre calendar constraints prima di avere un modello temporale
  adeguato;
- non introdurre integrazioni esterne prima di stabilizzare il core;
- non estrarre una libreria prima che il dominio sia maturo.

Se una fase successiva sembra necessaria per completare quella corrente,
l'agente deve: 1. spiegarne il motivo; 2. minimizzare l'intervento; 3. **non
implementare automaticamente l'intera fase successiva.**

### 9.11 Stato della roadmap

Stato al 2026-09-18, basato sul codice reale (non su aspirazioni). Phase 0 è
completata di fatto (architettura mappata e documentata in §2/§7/§9.2). Phase 1
completata: esiste `Planner` (`src/carpediem/planner/service.py`), usato da
`PlanProposalScreen`. Phase 2 completata: `Planner` orchestra
`scoring`/`constraints`/`capacity`/`explain`, `plan.py` e' wrapper compatibile,
`factor=None` auto-calibra; contratto in `tests/test_planner*.py`. Phase 3
completata: `Planner.propose()` restituisce `DayPlan`
(`src/carpediem/planner/models.py`, niente scheduling temporale), `plan_day()` e'
`propose().to_legacy()`; contratto in `tests/test_planner*.py` +
`test_planner_dayplan.py`. Phase 4 completata: `schedule()` deterministico
su `DayPlan` + `availability` esplicita (`src/carpediem/planner/scheduler.py`,
`ScheduledDayPlan` in `models.py`); `Planner.schedule()` wrapper;
`propose()`/`plan_day()`/UI intoccati; `tests/test_scheduler.py`. Phase 5
completata: `feedback()` deriva `ExecutionFeedback` da scheduled+todos
(solo osservazione, niente auto-calibrazione); `tests/test_feedback.py`.
Phase 6 completata: `calibration.py` boundary sottile (observe/factor_for,
matematica in `domain`); `capacity.estimate` riusa `domain`;
`tests/test_calibration.py`.

| Phase | Obiettivo                        | Stato       |
| ----- | -------------------------------- | ----------- |
| 0     | Baseline e comprensione          | Done        |
| 1     | Explicit Planner boundary        | Done        |
| 2     | Scoring / constraints / capacity | Done        |
| 3     | DayPlan model                    | Done        |
| 4     | Temporal scheduling              | Done        |
| 5     | Pomodoro / execution feedback    | Done        |
| 6     | Calibration / feedback loop      | Done        |
| 7     | Calendar / fixed events          | Done        |
| 8     | External task sources            | Done        |
| 9     | UI as Planner consumer           | Done        |
| 10    | Optional Planner extraction      | Done (audit: non estrarre) |

> Nota: **non** spostare una fase su "In progress"/"Done" finché l'implementazione
> non esiste davvero nel codice e i test non passano. La tabella va aggiornata
> nella stessa commit che realizza la fase.
> Direzione evolutiva del Planner Engine (TARGET/FUTURE, niente codice): `docs/planner-engine.md`
> (Phase 1 futura = Domain Consolidation, non estrazione; ADR-001 resta valido fino alla Phase 8).

### 9.12 Stato delle milestone M (audit 2026-09-25)

Le issue GitHub (#1–#53) erano un piano di lavoro, non segnalazioni utente:
erano state create dallo sviluppatore per guidare le milestone M1–M6. Il
triage del 2026-09-25 le ha verificate una a una contro il codice reale e ha
chiuso 51 su 53. **Da quel momento GitHub Issues contiene solo segnalazioni
degli utenti** (vedi `CONTRIBUTING.md`); le milestone si tracciano qui e in
`CHANGELOG.md`.

| Milestone | Stato | Dove vive |
| --- | --- | --- |
| M1 Planning Foundation | Done | `tests/test_planner_contract.py`, `_fixtures.py`, `_perf.py`; guardrail in `test_arch.py` |
| M2 Task Reality | Done | `src/carpediem/domain.py` (`TaskExecution`, `execution_summary`), `src/carpediem/storage.py` (`EXECUTIONS_FILE`) |
| M3 Explainable Planner | Done | `src/carpediem/planner/decisions.py` + `narrative.py`; card Why in `DetailScreen` |
| M4 Replanning | Done | `src/carpediem/planner/replan.py`, `domain.apply_replan`, `ReplanPreviewScreen` (`G`), CLI `carpediem replan` |
| M5 Calendar & Intelligence | Done | `FixedEvent`/`events_to_busy` in `src/carpediem/planner/`, `day_window` in config, `WeekReviewScreen` (`W`) |
| M6 Personal Time Model | **Parziale** | calibrazione e storico fatti; il *temporal fit* manca → #43 resta aperta |
| M6 Decomposition | Not planned | #44 chiusa: modello di stima non pronto, in conflitto con la direzione del progetto |
| M6 AI Layer | Not planned | #45 chiusa per scelta architetturale (§9.1: nessun AI/LLM nel percorso di pianificazione) |

La epic #6 resta aperta come umbrella M6 finché #43 non è chiusa (o abbandonata
con decisione documentata). Nota le tre famiglie duplicate che avevano le
issue #7–#20, #21–#30, #31–#40: erano la stessa roadmap ripetuta tre volte,
ora tutte chiuse.
