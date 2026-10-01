# Phase 2 — Domain Core: implementation plan

*(Stesura in build mode, ma SOLO piano: nessuna modifica a codice/test in
questa sessione. Verificato contro il repo post-Phase 1 (`2da6996`, CI
verde). Riferimenti: `docs/planner-engine.md` §16 Phase 2 + §§4–6, 12–13,
`docs/planner-phase1-plan.md` (base di partenza), `docs/adr-001-planner-boundary.md`
(invariato), `AGENTS.md` §9.)*

---

## 1. Executive summary

Phase 1 ha consolidato il boundary (`TaskView` + `todo_to_task()`, tempo
esplicito-first con fallback allowlisted, seam factor/confidence,
`_PlannerInput` privata, guardrail T8). Phase 2 fa il passo previsto da
`planner-engine.md` §16:

> **Consolidate domain models, `PlanningRequest`, `PlanningResult`, the
> `Planner` facade, and dependency boundaries. Goal: the planner stands
> alone as a domain core.**

In concreto, alla fine della Phase 2:

```python
result = plan(request)   # senza app, UI, storage, integrazioni
```

funziona con input espliciti e interamente planner-owned, e CarpeDiem
(screens + CLI) consuma questa superficie come primo client. I percorsi
legacy (`Planner(todos, ...)`, `plan_day()`, `replan(...)` posizionale)
restano intatti per compat: Phase 2 aggiunge la via regia, non rimuove
quella vecchia (le rimozioni sono Phase 7+).

Distinzione vincolante rispetto alla Phase 7 (Public Planner API):

- **Phase 2 = introdurre e usare** `PlanningRequest` / `PlanningResult` /
  `plan()` come superficie di lavoro interna-al-repo, marcata **instabile**
  (niente promessa di stabilita', niente versioning).
- **Phase 7 = stabilizzare e versionare**. Niente in Phase 2 deve
  precludere o anticipare quella stabilizzazione (niente numero di
  versione, niente garanzia retrocompatibile oltre il repo).

## 2. Punto di partenza (post-Phase 1, verificato)

```text
CURRENT (verificato su 2da6996)

  callers (tutti con today/now espliciti — audit T4)
  ├── screens/plan.py   Planner.propose (Buongiorno, scheduled_for_today),
  │                     replan + apply_replan (ReplanPreviewScreen G),
  │                     feedback (briefing sera)
  ├── screens/views.py  plan_decisions() = Planner.propose + decide
  │                     (+ domain.calibration_samples)
  ├── cli.py            replan + apply_replan (lazy import day_window_parts
  │                     + scheduled_for_today: debito noto)
  └── app.py            orchestra via screens (mai planner diretto)
            ↓  (input: list[TodoItem] + today str + hours + factor auto)
  src/planner/  (puro, T8 verde)
  ├── service.Planner(todos, today, hours, factor, now) → DayPlan
  │   ├── _resolve_day (explicit-first, fallback allowlisted)
  │   └── _normalize → _PlannerInput (PRIVATA)
  ├── scoring/constraints/capacity (su TaskView) + explain (chiavi)
  ├── scheduler.schedule / events_to_busy (su PlanItem/TimeWindow)
  ├── decisions.decide(+confidence seam) / narrative (chiavi i18n)
  ├── replan(todos, today, hours, avail, busy, now, current, factor)
  ├── feedback(scheduled, todos) → ExecutionFeedback
  └── calibration.factor_for/observe* (+ calibration_summary non-core)
            ↓  (seam documentati D1/D2/D3/D4)
  src/domain  calibrated_estimate+clamp (D1, unica fonte),
              calibration_factor (D2, auto path),
              execution_confidence (D4, default resolver),
              + execution_* history (fuori dal core)
  src/models  TodoItem (app-owned; il core non lo importa piu')
```

Fatti verificati per il disegno (grep 2026-10-01):

- `calibration_summary` (planner) ha **zero consumer di produzione**
  (solo `tests/test_execution_stats.py`): il trasloco D3 e' triviale.
- `factor_for`/`observe`/`observe_all` non sono chiamati da
  screens/app/cli (solo `service._normalize` + test): il seam D2 e'
  esercitato solo dal path auto legacy.
- Le screen importano dal boundary solo `Planner`, `decide`,
  `primary_reason`, costanti decisioni, `narrative`, `feedback`,
  `models.*`, `replan` (+costanti), `events_to_busy`, `explain`
  (solo `screens/plan.py`): **nessuna importa gli stadi interni**
  (`scoring`/`constraints`/`capacity`) — il guardrail che lo vieta
  sara' gratis.
- `replan()` e' gia' request-like (tutto esplicito) e gia'
  view-compatibile (normalizza via `Planner` + scan `getattr`):
  **non richiede modifiche in Phase 2**.

## 3. Decisioni architetturali (trade-off espliciti)

### D-Task: TaskView resta, nessun secondo modello

Raccomandazione: **tenere `TaskView` (nome + 13 campi) come modello task
del core; non introdurre alcun `Task` canonico parallelo.**

- Pro: zero churn (T2 fail-closed, adapter, test e chiamate restano
  validi); il nome onesto ("View") registra la provenienza come
  proiezione dei dati applicativi; la questione "modello canonico" si
  risolve DA SOLA — il core ne ha gia' uno e funziona.
- Contro: in un futuro package pubblico `TaskView` suona da adapter,
  non da dominio.
- Respinte: (a) rinomina `TaskView → Task` ora — churn su ~15 file per
  zero comportamento, e congela il nome pubblico prima della Phase 7
  (che e' la sede giusta per decidere i nomi stabili); (b) nuovo modello
  `Task` accanto a `TaskView` — duplicazione vietata da §5.0 del piano
  Phase 1 e senza alcun consumatore che la giustifichi.
- Regola di review: qualunque proposta di nuovo tipo-task in Phase 2 va
  respinta salvo giustificazione da algoritmo/campo mancante (che non
  c'e': §5.1 Phase 1 copre tutti i lettori).

### D-Req: un PlanningRequest sobrio, niente mini-framework

Raccomandazione: **una sola frozen dataclass con i campi che servono
oggi** (sotto §5), niente `constraints`/`preferences`/`timezone`
(Phase 4+), niente builder pattern, niente validatori a oggetti.

Contro la tentazione "completa subito il §6 dell'engine doc": ogni campo
speculativo diventa debito di compat quando la Phase 7 stabilizza.
La regola e': campo solo se un consumer Phase-2 lo passa davvero.

### D-Cap: capacity in pomodori nel Request, ore fuori

Il core ragiona in pomodori (`capacity_pomo`, `POMO_HOURS` interna);
le ore (`day_hours` config) sono vocabolario applicativo. Quindi
`PlanningRequest.capacity_pomo: float` e la conversione ore→pomo vive
nell'adapter app-side (`build_planning_request()`). Coerente con Phase 1
(stime normalizzate al bordo, mai nel core).

### D-Factor: nel core il factor e' dato, mai cercato

Sul path request `factor: None` = non calibrato, punto. L'auto-risoluzione
(`domain.calibration_factor`) si sposta nell'adapter app-side, che la
conosce gia' (la usano `system.py:567`, `views.py:1422` per display).
Il path legacy `Planner(factor=None)` conserva l'auto (compat + T7a).
Niente doppia semantica nascosta: i due path sono documentati fianco a
fianco in `service.py`.

### D-Seam: delega matematica resta, fetch della storia esce

Onesta' architetturale: Phase 2 **non rimuove** la delega D1
(`calibrated_estimate`+clamp) ne' il default D4 (`execution_confidence`)
— la matematica resta in `domain` fino alla Phase 5 per decisione
dell'engine doc, e duplicarla sarebbe peggio che delegarla. Quello che
Phase 2 rimuove dal path nuovo e' il **fetch**: `plan(request)` non
chiama mai `domain` per procurarsi dati (factor/sample arrivano gia'
risolti); l'unico uso runtime di `domain` resta matematica pura su
scalari. Il trasloco vero e proprio e' solo D3 (zero consumer, §7).

## 4. Target di fine Phase 2

```text
PHASE 2 TARGET

  app (screens / CLI)
  │  build_planning_request()  (app-owned: TodoItem→TaskView,
  │    hours→pomo, factor auto via domain, window→avail/busy)
  ▼
  ┌──────────────────────────────────────────────┐
  │ src/planner/  (domain core, still in-repo)   │
  │  PlanningRequest ──→ plan() ──→ PlanningResult│
  │    (frozen, TaskView-only, unstable-by-doc)  │  plan = DayPlan
  │  replan() invariato (gia' request-like)      │  sched = ScheduledDayPlan
  │  stages invariati (scoring…narrative)        │  decisions (+sample ctx)
  │  estimation seam dichiarato (solo capacity)  │
  │  legacy paths intatti (compat, testati)      │
  └──────────────────────────────────────────────┘
  │  fuori dal boundary: calibration_summary (→domain),
  │  factor auto (→adapter), history/executions (mai entrati)
  ▼
  store/domain.apply_replan (commit, invariati, fuori dal core)
```

## 5. Disegno di PlanningRequest / PlanningResult

```python
@dataclass(frozen=True)
class PlanningRequest:
    tasks: tuple[TaskView, ...]          # normalizzate in __post_init__
    day: date                            # esplicito, validato (ValueError se garbage)
    capacity_pomo: float                 # unita' core; <0 → 0.0 (come capacity.total)
    factor: float | None = None          # esplicito; None = non calibrato (D-Factor)
    availability: tuple[TimeWindow, ...] = ()
    busy: tuple[TimeWindow, ...] = ()    # TimeWindow; FixedEvent→busy resta
                                         # events_to_busy (app-side o core? vedi sotto)
    now: datetime | None = None          # clipping replan; None = finestra intera
    sample_count: int | None = None      # contesto calibrazione per decisions
```

Note vincolanti:

- `tasks` accetta `TodoItem | TaskView` in costruzione e normalizza una
  volta sola in `__post_init__` (via `object.__setattr__`, pattern
  frozen-safe); dopo, solo `TaskView`. Test fail-closed sui campi come T2.
- `day` accetta `date` (e `datetime` → `.date()`); stringhe garbage/None
  → `ValueError` (fail-fast al boundary: un Request invalido non deve
  produrre un piano silenziosamente spostato — differenza voluta rispetto
  alla tolleranza legacy).
- `busy` accetta anche `FixedEvent`? No: conversione via `events_to_busy`
  resta chiamata esplicita dell'adapter (un tipo solo per campo = meno
  ambJiguita'). L'adapter app-side la applica.
- Niente `constraints`/`preferences`/`timezone`/`calendar`: Phase 4+.

```python
@dataclass(frozen=True)
class PlanningResult:
    request: PlanningRequest              # eco (tracciabilita' input→output)
    plan: DayPlan                         # invariato (stessi campi)
    scheduled: ScheduledDayPlan | None    # None se availability vuota
    decisions: tuple[PlanningDecision, ...]  # via decide(); confidence da
                                             # request.sample_count (puo' essere None)
```

- `decisions` sempre presenti (anche a `scheduled=None` — decisione ≠
  schedulazione, principio M3). Nessun nuovo campo evidence (Phase 6).
- `ReplanProposal` resta IL risultato del replan (niente wrapper
  `ReplanResult`: churn senza lettori).

Entrambi in `src/planner/models.py`, esportati da `__init__` (solo
aggiunta), docstring con marcatura esplicita:

> **Instabile fino alla Phase 7**: forma di lavoro interna-al-repo, non
> promessa di stabilita', non versionata. La Phase 7 puo' rinominare e
> ricomporre liberamente.

## 6. Facade

```python
# src/planner/service.py (stesso modulo del Planner: un solo punto recipe)
def plan(request: PlanningRequest) -> PlanningResult:
    """propose + schedule (+decide) composti, nessun algoritmo nuovo."""
```

Comportamento: `propose` sui task del request (stessa pipeline di
`Planner.propose`, riuso interno — implementato come costruzione del
percorso esistente, non come duplicato) → se `availability` non vuota,
`schedule` → `decide(plan, tasks, sample_count=request.sample_count)`.
`replan()` **invariato** (firme, semantica, test): e' gia' esplicito e
view-compatibile; il seam factor esiste dalla 4b.

`Planner` (classe) resta com'e' (path legacy auto+compat+`plan_day`).
Doppia via d'ingresso in Phase 2–6, come `plan.py` e' doppione
compatibile oggi: la convergenza (deprecazioni) e' Phase 7, non ora.

## 7. Trattamento dei seam D1–D4 in Phase 2

| # | Seam | Trattamento Phase 2 |
|---|---|---|
| D1 | `capacity → calibrated_estimate + CAL_CLAMP_*` | **Resta delega, diventa contratto**: nuovo test-tabella (basi 0/1/N/garbage × factor None/clamp-edge/garbage) + nuovo guardrail "solo `capacity.py` importa matematica estimation da `domain`" (grep su import-lines, stile T8). Nessun trasloco (Phase 5). |
| D2 | auto factor | **Si sposta all'adapter**: `build_planning_request()` app-side risolve via `domain.calibration_factor`; il path `plan(request)` non chiama mai `domain` per procurarsi dati. `calibration.factor_for` resta per il path legacy + test. |
| D3 | `calibration_summary` | **Trasloco in `domain.py`** (pura aggregazione di `execution_*`, zero input planner; zero consumer produzione, 1 test da aggiornare). Rimozione da `src/planner/__init__.__all__` + adeguamento snapshot T9 (rimozione esplicita e motivata, non silenziosa). |
| D4 | `execution_confidence` default | **Resta** (seam Step 6 + `decide(confidence=)` gia' usabile dal path request via `sample_count`). Trasloco/wrap ulteriore = Phase 5. |

Verifica onesta del claim "il path nuovo non fetcha": test con import-hook che fallisce se `plan(request)` importa `src.domain`/`src.storage`/`src.app` a runtime oltre i moduli gia' caricati? Troppo fragile (capacity importa domain a import-time, gia' caricato). Misura giusta e stabile: **test statico** — `service.plan`, `models` (Request/Result), `scheduler`, `decisions`, `feedback`, `replan` non nominano `calibration_factor`, `load_`, `store`, `commit` fuori dai docstring (estensione del T8c esistente ai nuovi nomi). Il runtime resta delega matematica dichiarata.

## 8. Migrazione app (screens + CLI)

Nuovo helper app-owned in `screens/plan.py` (accanto a
`scheduled_for_today`/`day_window_parts`):

```python
def build_planning_request(todos, today, hours, window, *, include_done=False) -> PlanningRequest
```

fa: `todo_to_task` (via Request), `hours → capacity.total`, factor auto
via `domain.calibration_factor`, `window → availability + events_to_busy`.
Siti migrati (stesso comportamento, gate = UI suite invariata):

1. Buongiorno `PlanProposalScreen` (`plan.py:1377`) → `plan(request)`.
2. `scheduled_for_today` (`plan.py:224`) → request sui soli confermati
   (la semantica confermati-only resta identica, cambia solo il motore
   interno). E' il punto piu' delicato: equivalenza dedicata
   legacy-vs-request su matrice + `DayPlan` filtrato identico.
3. `ReplanPreviewScreen` (`plan.py:1170`) → `replan()` invariato ma con
   task da request? No — `replan()` resta com'e' (accetta TodoItem,
   normalizza dentro). Nessun cambio: solo documentare che e' gia' a posto.
4. `plan_decisions` (`views.py:1192`) → `plan(request).decisions` con
   `sample_count=domain.calibration_samples(...)` (stessi input, stesso
   output; T-gate: suite `test_detail_why` verde invariata).
5. CLI `_cli_replan` → invariato (usa `replan()` + `scheduled_for_today`;
   eredita la migrazione di (2) gratis).

`plan_day()`/`src/plan.py`: intatti (compat + test).

## 9. Strategia test

| # | Test | Tipo |
|---|---|---|
| U1 | Request: frozen, normalizzazione TodoItem→views, `day` garbage → `ValueError`, capacity negativa → 0.0, `datetime` → `.date()`, lista campi esatta (fail-closed come T2) | unit (nuovo) |
| U2 | Result: `scheduled=None` senza availability; `request` eco identico; decisions presenti con/senza sample_count; confidence solo con calibrated (regola invariata) | unit (nuovo) |
| E1 | Equivalenza facade: `plan(request)` ≡ path legacy (`Planner.propose` + `schedule` + `decide`) su matrice fixture completa — `DayPlan ==`, slot `==`, decisions `==` (a parita' di factor/sample) | characterization permanente (nuovo, il T1 della Phase 2) |
| E2 | `scheduled_for_today` legacy-vs-request: stessi confermati → stesso `ScheduledDayPlan` | characterization (nuovo, cancello migrazione §8.2) |
| D1c | Tabella estimation (basi × factor, clamp-edge 0.5/3.0, garbage) + guard "solo capacity importa estimation-math" | contract+arch (nuovo) |
| D3m | `domain.calibration_summary` ≡ vecchio comportamento (test esistente ri-puntato) + T9 aggiornato | regression (adattato) |
| R1 | Determinismo request→result (seeded shuffle, clock variato) | strengthened (nuovo) |
| G1 | Guard estesi: niente `planner.scoring/constraints/capacity` in screens/app/cli (gratis: verificare che oggi passi); Request/Result/`plan` mai in `test_arch` banned | arch (nuovo) |
| K1 | Tutte le suite esistenti invariate e verdi (incluso T1–T9 Phase 1, UI pilot, perf) | regression (retain) |

## 10. Sequenza di migrazione (un commit per step, ognuno verde da solo)

1. **P2-1 — Tipi**: `PlanningRequest`/`PlanningResult` in `models.py` + export + U1/U2. Solo additivo.
2. **P2-2 — Facade**: `plan(request)` in `service.py` (composizione, zero algoritmi) + E1 + R1. Legacy intatto.
3. **P2-3 — Adapter D2**: `build_planning_request()` in `screens/plan.py` + test adapter (factor auto ≡ legacy, window→avail/busy, confirmed-subset). Nessun consumer migrato ancora.
4. **P2-4 — D3**: trasloco `calibration_summary → domain` + T9 adeguato + test ri-puntato.
5. **P2-5 — D1 contratto**: tabella estimation + guard import-matematiche.
6. **P2-6 — Migrazione siti** (§8.1/8.2/8.4, uno per commit se serve): Buongiorno, `scheduled_for_today` (+E2), `plan_decisions`. CLI e ReplanPreview ereditano. Gate = UI suite invariata.
7. **P2-7 — Guard + docs**: G1, docstring request/facade ("instabile fino a Phase 7"), sprint log convenzionale (AGENTS.md solo se la convenzione lo richiede; CHANGELOG invisibile → intatto).
8. **P2-8 — Gate + reviewer**: full pytest + ruff + format + mypy + `@reviewer`, nessuna release (invisibile).

Rollback: ogni step e' additivo o a default-invariato; P2-6 e' il solo con
tocchi UI ma coperta da E2 + suite pilot.

## 11. Compatibilita'

- Firme legacy intatte (`Planner(...)`, `replan(...)`, `feedback`, `decide`,
  `plan_day`, `DayPlan` & co., fallbacks, `to_legacy`). Unica rimozione in
  tutto il programma: `calibration_summary` dal namespace planner (zero
  consumer produzione; test unico aggiornato; motivata in commit).
- `__all__` cresce di `PlanningRequest`, `PlanningResult`, `plan`
  (+ eventuale helper); cala di `calibration_summary` (T9 adeguato).
- `TaskView` input resta accettato ovunque (adapter permanente Phase 1).

## 12. Rischi

| Rischio | Mitigazione |
|---|---|
| Divergenza doppio path (legacy vs request) | E1 permanente su matrice; arch-test che i nuovi consumer usino solo `plan()`/`replan()` |
| Field-creep del Request | fail-closed U1 sui campi (come T2); regola "campo solo se un consumer Phase-2 lo passa" |
| Stabilizzazione prematura (trattare Request come pubblico) | marcatura "instabile fino a Phase 7" in docstring + §18 DoD; niente versioning |
| Drift `scheduled_for_today` in migrazione | E2 dedicato + suite pilot invariata |
| `ValueError` su day invalido rompe un caller tollerante | audit: l'adapter valida prima (window/today da config validata); legacy resta tollerante; test sui bordi |
| Trasloco D3 rompe import ignoti | grep pre-commit su tutto il repo (fatto: 1 solo test); T9 adeguato |
| Over-astrazione (protocolli Estimator, builder, validatori) | vietato in review salvo esigenza dimostrata; `build_*` e' una funzione, non una classe |

## 13. Non-goals (Phase 2 NON implementa)

- niente cambi a scoring/scheduler/estimation/capacity/replan-algoritmi;
- niente `constraints`/`preferences`/`timezone`/`calendar` nel Request;
- niente `Task` canonico nuovo, niente rinomina `TaskView`;
- niente stabilizzazione/versioning dell'API (Phase 7), niente package (Phase 8), niente REST/MCP;
- niente rimozione di path legacy (`Planner`, `plan_day`, fallback, `_PlannerInput` resta come kata interno o viene assorbito — dettaglio implementativo);
- niente diagnostica oltre decisions esistenti (Phase 6);
- niente bump versione/release/CHANGELOG (invisibile; AGENTS.md solo se convenzione).

## 14. Definition of Done (oggettiva)

1. `result = plan(request)` gira con soli input espliciti e planner-owned, senza app/UI/storage/integrazioni (test che costruisce il Request da `TaskView` puri, senza `TodoItem`/`domain`/store).
2. `plan(request)` ≡ path legacy su matrice completa (E1 verde permanente).
3. I flussi principali (Buongiorno, piano giorno, Why, replan CLI/UI) consumano il path request (o ereditano funzioni migrate) con UI suite invariata e verde.
4. D3 traslocato; D1 sotto contratto+guard; D2 auto all'adapter; D4 invariato e documentato.
5. Guard completi verdi: pytest + ruff check + format + mypy + `@reviewer`; T8 esteso (G1) verde.
6. ADR-001 byte-identico; nessuna API marcata stabile; nessuna dipendenza nuova in `pyproject`/`requirements`.
7. Docs: questo piano + docstring "instabile fino a Phase 7"; AGENTS.md/CHANGELOG solo se la convenzione lo richiede.

## 15. Split in commit/PR

P2-1…P2-8 come §10 (P2-6 eventualmente splittato per sito). Messaggi in
inglese, scope piccolo (`refactor(planner): phase2 step N - ...`), mai
`--force`, push dal tuo terminale, CI verde prima di proseguire.

## Appendice — evidenze (verifica pre-stesura 2026-10-01)

- `service.py` post-Phase 1 riletto (149 righe: `_PlannerInput` privata,
  `_resolve_day`, `_normalize`, `propose`, `schedule` thin).
- Consumer scannerizzati: 5 siti `Planner(`/2 `replan(` (§8); stadi interni
  mai importati fuori dal boundary; `explain` solo in `screens/plan.py`.
- Seam: D3 zero consumer produzione (solo `tests/test_execution_stats.py`);
  `factor_for`/`observe*` solo uso interno+test; `plan.py:22` docstring auto.
- Engine doc riletta (§16 Phase 2 + §§4–6, 12–13): Phase 2 = modelli +
  Request/Result + facade + boundary; stabilizzazione = Phase 7 (non ora).
- Test esistenti censiti: `test_arch.py` (9 test post-T8), T1–T9 Phase 1,
  `test_planner_*.py`, UI pilot (`plan_ui/operate`, `day_window`,
  `detail_why`, `replan_ui/cli`, `execution`), perf baseline.
