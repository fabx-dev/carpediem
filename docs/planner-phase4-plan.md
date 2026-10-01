# Phase 4 — Constraint Engine: implementation plan

*(Stesura in build mode, ma SOLO piano: nessuna modifica a codice/test in
questa sessione. Verificato contro il repo post-Phase 3 (P3-5, CI verde).
Riferimenti: `docs/planner-engine.md` §16 Phase 4 + §10 (constraint model)
+ §11 (scoring separation), `docs/planner-phase3-plan.md`,
`docs/adr-001-planner-boundary.md` (invariato), `AGENTS.md` §9.)*

---

## 1. Executive summary

Phase 3 ha chiuso il ragionamento temporale (deadline hard, durate uniche,
policy tz). Phase 4 fa il passo previsto da `planner-engine.md` §16:

> **Progressively formalize hard vs soft constraints and keep the system
> extensible without scheduler rewrites (§10).**

Con il vincolo esplicito dello stesso §10: **niente framework generico di
constraint finché il codice non lo richiede**. Phase 4 quindi NON crea
classi `Constraint`/`Preference`, registri, plugin o DSL. Fa tre cose
concrete e piccole:

1. **Dichiara** i vincoli esistenti per nome (oggi sono `if` sparsi +
   docstring che li racconta): ogni regola hard/soft ottiene casa
   nominale, verdetto esplicito e test dedicato.
2. **Compone** il loop di scheduling come congiunzione nominata
   (`_placeable`): un futuro bound = nuovo congiunto + mappa, non
   chirurgia del loop — la prova strutturale del "senza rewrite".
3. **Blocca** con guard la proliferazione di regole implicite (nuove
   esclusioni silenziose altrove vietate).

## 2. Censimento vincoli attuali (verificato, CURRENT)

Proposta (`_build_day_plan`):

| # | Regola | Tipo | Casa odierna |
|---|---|---|---|
| H1 | `state == "attivo"` altrimenti fuori | hard silenzioso | `constraints.is_eligible` |
| H2 | `id is not None` altrimenti fuori | hard silenzioso | `constraints.is_eligible` |
| H3 | `plan_skip == today` → sezione skipped con motivo, fuori capacita' | hard spiegato | `constraints.partition` |
| H4 | mandatory (scaduto/oggi) e gia'-pianificati mai tagliati (possono sforare) | hard con override | `capacity.allocate` |

Scheduling (`schedule` + replan):

| # | Regola | Tipo | Casa odierna |
|---|---|---|---|
| H5 | collocabile solo dentro availability | hard | `_subtract` (fuori = unscheduled) |
| H6 | mai overlap con busy (mergeati) | hard | `_subtract` |
| H7 | scadenza oggi+orario: fine-slot ≤ deadline | hard | `_deadline` (P3-2) |
| H8 | availability/busy clippati al giorno | hard | `_normalize`/`_clip` |
| H9 | replan: slot passati indisponibili (`[now, fine]`) | hard | `_clip_future` (replan.py) |

Merito (sacrificabili, NON vincoli — restano in `scoring.py`, Phase 5):

S1 pesi priorita', S2 progetto fermo, S3 domani, S4 bonus gia'-pianificato,
S5 annotazione calibrata. La separazione Eligibility/Scoring/Scheduling
(§11) resta intatta: Phase 4 non sposta una riga di merito.

## 3. Decisioni (trade-off espliciti)

### C-Verdict: verdetti nominati a 3 vie, non booleani + commenti

Raccomandazione: `constraints.py` espone `eligibility_of(view, today_s)`
→ `ELIGIBLE | SKIPPED | EXCLUDED` (costanti frozen, non enum: come
`SCHEDULED/...` di decisions) e `partition` la instrada (equivalenza
totale). H1+H2 collassano in `EXCLUDED` (silenzioso come oggi: il PERCHÉ
dell'esclusione resta interno — i non-eleggibili non compaiono da nessuna
parte, mostrare il motivo cambierebbe la UI).

- Pro: la distinzione a 3 vie esiste nel codice invece che in due `if`
  in sequenza + docstring; `decide()` e sezioni DayPlan restano invariate.
- Respinte: (a) motivi distinti per H1/H2 (cambierebbe output/UI, non
  richiesto); (b) classe `Verdict` con payload (nessun consumatore del
  payload: stringa-frozen come gli stati decisione esistenti).

### C-Keep: privilegio capacity come predicato nominato

Raccomandazione: `capacity.keep_always(entry, today_s)` =
`mandatory or planned_for == today_s`; `allocate` lo usa (stesso
comportamento, contratto dedicato: mai tagliati anche a capacita' 0,
sforamento rappresentato, gli altri greedy). Piccolo, nominato, testato.

### C-Placeable: il loop consulta una congiunzione, non `if` inline

Raccomandazione: `schedule()` estrae il test di fit in
`_placeable(slot, start, need, limit)` = `start+need <= min(slot.end,
limit-or-slot.end)` — oggi due congiunti nominati (fit + deadline),
stessi output bit-identici. Un futuro bound temporale aggiunge un
parametro + congiunto + mappa esplicita (precedente `deadlines`), mai
ristruttura. Il consumo slot resta com'e' (il resto oltre-deadline
resta libero per voci senza vincolo — semantica P3-2 invariata).

- Non e' framework: e' una funzione pura di 3 righe con i congiunti in
  fila. La generalizzazione a "lista di predicati registrabili" è
  VIETATA in review (nessun secondo predicato esiste ancora).

### C-Guard: nuove esclusioni silenziose solo in constraints.py

Raccomandazione: guard grep — confronti di eleggibilita' su `.state`
(`== "attivo"`, `!= "attivo"`, `"completato"`, `"in_sospeso"`) fuori da
`constraints.py` ammessi solo dove gia' esistono per lettura (replan
current-set, decisions evidence, feedback completed, app/screens
display) — vietati NUOVI siti decisionali. Implementazione pragmatica:
test che elenca i file:linea ammessi (allowlist esplicita come T8-time)
e fallisce su nuove occorrenze. Ammettere candidamente: è un guard
euristico su stringhe, come T8 — sufficiente allo scopo, documentato.

## 4. Target di fine Phase 4 (delta vs Phase 3)

```text
constraints.py: eligibility_of() -> ELIGIBLE|SKIPPED|EXCLUDED (+costanti),
                partition instradata (stessi output)
capacity.py:    keep_always() usato da allocate (stessi output)
scheduler.py:   _placeable() congiunzione nominata (stessi slot)
catalogo:       docstring constraints.py = H1-H4, scheduler.py = H5-H8
                (+H9 rimando a replan), scoring invariato = S1-S5
guard:          allowlist siti state-decisionali + T8 esistenti
```

Zero cambi a: scoring/pesi, DayPlan/ScheduledDayPlan/Request/Result,
`replan`/`feedback`/`decisions`/`narrative`, UI, i18n, storage, config.

## 5. Sequenza (un commit per step)

1. **P4-1 — Censimento eseguibile**: `tests/test_phase4_constraints.py`
   con un test nominato per H1–H9+S1–S5 sul comportamento corrente
   (solo test, zero produzione — fissa il vocabolario).
2. **P4-2 — Verdetti**: `eligibility_of` + costanti + `partition`
   instradata + equivalenza (suite verdi = prova).
3. **P4-3 — keep_always**: predicato + contratto (mai-tagliati a
   capacita' 0, sforamento, greedy resto) + `allocate` instradato.
4. **P4-4 — _placeable**: estrazione congiunzione + golden P3-2 + full
   verdi (prova "senza rewrite": il diff tocca solo il test di fit).
5. **P4-5 — Guard + catalogo**: allowlist state-decisionali, docstring
   catalogo H/S, sprint log convenzionale.
6. **P4-6 — Gate + reviewer**: full pytest + ruff + format + mypy +
   `@reviewer`, nessuna release (invisibile).

Rollback: P4-1 test-only; P4-2..P4-4 a output-identici (revert = reinline);
P4-5 solo test/docs.

## 6. Strategia test

| # | Test | Tipo |
|---|---|---|
| C1 | H1–H9: un test nominato per regola (silenziosi invisibili, skipped in fondo con motivo, mandatory mai tagliati, busy/availability/deadline/clip/now) | characterization (nuovo, P4-1) |
| C2 | S1–S5: merito resta influenza, non veto (pesi da fixture esistenti, richiamati per nome) | characterization (nuovo, P4-1) |
| V1 | `eligibility_of` 3 vie + `partition` identica (suite esistenti = cancello) | unit+regression |
| K1 | `keep_always`: mandatory+planned a capacity 0/0.5, sforamento rappresentato, resto greedy+cut | unit (nuovo) |
| P1 | `_placeable`: fit/deadline/bordi + golden P3-2 rieseguiti identici | unit (nuovo) |
| G3 | allowlist siti state-decisionali | arch (nuovo) |
| K2 | suite complete invariate e verdi | regression (retain) |

## 7. Compatibilita' e release

- Firme e modelli invariati (`partition` stessa firma; `allocate` stessa
  firma; `schedule` stessa firma; verdetti interni a constraints).
- UI/storage/config/i18n intoccati. Default: **nessuna release**
  (invisibile; rivalutazione solo su decisione utente).

## 8. Rischi

| Rischio | Mitigazione |
|---|---|
| Refactor cosmetico senza valore | ogni step ha cancello output-identici + catalogo testato (valore = leggibilita' + estensibilita' provata) |
| Verdetti usati altrove in futuro come stringhe magiche | costanti frozen + import unico; guard ne vieta duplicati letterali fuori constraints (estensione G3 se serve) |
| `_placeable` diventa framework per proliferazione | review vieta terzo congiunto senza consumer reale + test |
| Guard allowlist fragile (righe che si spostano) | marker-based come T8 (commento `# constraint-site`), non numeri di riga |
| Tentazione soft→hard (es. stale diventa veto) | vietato: cambierebbe scoring = Phase 5; C2 lo inchioda come influenza |

## 9. Non-goals (Phase 4 NON implementa)

- niente classi/framework/registri/plugin di constraint;
- niente nuovi vincoli (per-item busy, earliest-start, dipendenze, limiti per progetto);
- niente soft-constraint esplicite oltre il censimento (pesi restano in scoring);
- niente motivi/reason nuove, niente diagnostica (Phase 6);
- niente cambi a scheduling-output su qualunque fixture esistente;
- niente bump versione/release di default.

## 10. Definition of Done

1. Censimento C1/C2 verde e permanente (vocabolario hard/soft eseguibile).
2. `partition` via verdetti + `allocate` via `keep_always` + `schedule` via `_placeable`, output identici (suite complete verdi).
3. Catalogo H/S nei docstring; guard G3 verde.
4. Full gate + `@reviewer` OK; ADR-001 intatto; zero dipendenze nuove.
5. AGENTS.md/CHANGELOG solo se convenzione; nessuna release di default.

## 11. Split in commit

P4-1…P4-6 come §5. Messaggi `refactor(planner): phase4 step P4-N - ...`,
push utente, CI verde se la fase si allunga.

## Appendice — evidenze (verifica pre-stesura)

- `constraints.py` riletto (41 righe: docstring gia' classifica H/S a
  parole; `is_eligible`/`is_skipped`/`partition` booleani).
- Engine §10 riletto: hard impliciti confermati; TARGET = distinguere
  progressivamente + estensibile senza rewrite; divieto framework
  prematuro (vincola §9 del piano).
- Engine §11 riletto: Eligibility/Scoring/Scheduling separati per sempre
  (P4-2..P4-4 non spostano merito).
- Nessun altro `schedule(` produttivo oltre i 4 con mappa (audit P3-2
  del reviewer, confermato).
