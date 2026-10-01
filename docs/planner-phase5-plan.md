# Phase 5 — Advanced Planning: implementation plan

*(Stesura in build mode, ma SOLO piano: nessuna modifica a codice/test in
questa sessione. Verificato contro il repo post-Phase 4 (P4 follow-ups, CI
verde). Riferimenti: `docs/planner-engine.md` §16 Phase 5 + §§8, 11,
`docs/planner-phase4-plan.md`, `docs/adr-001-planner-boundary.md`
(invariato), `AGENTS.md` §9.)*

---

## 1. Executive summary

Phase 4 ha chiuso i vincoli come vocabolario esplicito. Phase 5 fa il passo
previsto da `planner-engine.md` §16:

> **Evolve scoring, scheduling, estimation, calibration, replanning. This
> is the phase where the planner may become significantly more
> sophisticated (§§8, 11).**

"Mays" è operativa: Phase 5 rende il planner più sofisticato dove esiste
un problema reale e misurabile, NON ovunque sia attraente. Il programma
tenuto:

- **P5-A — Collocazione feasibility-first**: lo scheduler colloca prima le
  voci con scadenza odierna (a pari resto, ordine di merito invariato),
  così una deadline stretta non resta stranded dietro una voce libera.
  Solo riordino di collocazione: `DayPlan`, merito, ragioni intatte.
- **P5-B — Stima: il core diventa fonte unica**: la matematica estimation
  (mediana, min-samples, clamp, `calibrated_estimate`, livelli confidence)
  si sposta in `src/planner/estimation.py`; `domain.py` delega (stesse
  firme, stessi valori). A fine fase `src/planner/` non importa più
  `src/domain` (dipendenza solo app→core, mai core→app).

Esplicitamente NON in Phase 5 (§6): cambi pesi scoring, calibrazione
per-progetto/recency, execution-aware/remaining-work, dipendenze tra task,
finestre multiple, diagnostica nuova, API stabili.

## 2. Punto di partenza (verificato)

- Scheduler: first-fit **nell'ordine Planner** (merito). Con deadline
  (P3-2) una voce stretta dopo una libera può restare unscheduled anche
  quando invertirle collocherebbe entrambe — caso reale, non teorico:
  A (score alto, senza scadenza, 8🍅) riempie 09–13; B (scadenza 10:00,
  1🍅) resta fuori, ma B-09:00 + A-09:30 entrerebbero entrambi.
- Estimation: `domain` implementa, `capacity`/`calibration` delegano
  (seam D1/D4 testati). UI/display (`predicted_minutes`,
  `calibration_summary`, stats) consumano da `domain`. Nessuna divergenza
  nota, nessun reclamo di miscalibrazione: l'algoritmo NON cambia, cambia
  solo la casa (single source nel core).
- Calibration factor: mediano su completati con entrambi > 0, min 5
  campioni, clamp 0.5–3.0 — efficace e testato; nessuna evidenza che
  per-progetto/recency migliorerebbero (e segmenterebbero i campioni
  sotto soglia: con <5/progetto il factor sparirebbe ovunque).
- Replan: clip + factor + deadlines, testato. Execution-aware (worked-today
  → remaining) richiederebbe biforcazione estimate pieno/residuo con
  ricadute su DayPlan/feedback/calibrazione/display senza consumatore che
  lo chieda → rinviato (§6), non progettato a metà.

## 3. Decisioni (trade-off espliciti)

### S-Order: vincolate-prima a pari merito, DayPlan intatto

Raccomandazione: in `schedule()`, a ordine di merito invariato come
criterio primario, le voci con deadline odierna precedono quelle senza
nella **sequenza di collocazione** (stable sort su chiave
`(ha_scadenza_oggi ? 0 : 1)` — `DayPlan.planned` NON riordinato, niente
secondo scoring, niente ricalcolo merito).

- Pro: risolve lo stranding con garanzia (se esiste un collocamento che
  rispetta tutte le deadline, vincolate-prima lo trova nei casi
  first-fit; dimostrabile sui golden); fixture esistenti identiche
  (zero timed-dues → chiave sempre 1 → ordine invariato); `CONSTRAINED`
  resta il fallback onesto quando non entra comunque.
- Contro: a capacità tirata una voce libera ad alto merito può slittare
  dopo una vincolata a basso merito — MA lo slittamento è solo temporale
  (slot), mai di selezione: il DayPlan (cosa entra) non cambia, solo il
  dove/quando. Documentato come semantica voluta.
- Respinte: (a) riordino per merito ricalcolato (violerebbe "scheduler
  never re-scores", §11); (b) ottimizzazione esaustiva/backtracking
  (non determinismo-opaco e costo; first-fit resta); (c) toccare
  `DayPlan.planned` (contratto UI/CLI/test).

### S-Own: matematica estimation nel core, domain delega

Raccomandazione: nuovo `src/planner/estimation.py` puro con
`CAL_MIN_SAMPLES`, `CAL_CLAMP_MIN/MAX`, `ratios/factor/samples` su
coppie vista, `calibrated_estimate(view, factor)`, `confidence(count)`;
`domain.py` diventa thin-delegation (stesse firme/valori per UI/stats);
`capacity`/`calibration`/`decisions` importano dal core. A fine fase:
**zero import `src.domain` in `src/planner/`** (verificato da guard).

- Pro: chiude il decoupling architetturale (unica freccia app→core);
  matematica identica riga per riga (tabelle D1 + calibration esistenti
  come cancello); nessun caller cambia firma.
- Contro: `domain.py` importa `planner` (nuova direzione) — voluta e
  documentata (app dipende dal core, mai viceversa); ciclo impossibile
  (planner non importerà mai domain dopo P5-B — guard).
- Dettaglio delicato: `_calibration_ratios` legge `.stima_pomo`,
  `.actual_pomo`, `.state` — su TaskView via alias/campi esistenti ✓;
  su TodoItem invariato ✓ (stesse letture, solo spostate).
- Respinte: (a) duplicare invece di spostare (due fonti divergono —
  vietato); (b) cambiare l'algoritmo "già che ci siamo" (nessuna
  evidenza; mediana+clamp restano); (c) spostare anche `TaskExecution`/
  storage (persistenza, non matematica — resta in models/storage).

### S-NoScore: pesi intoccati

Nessuna evidenza di merito sbagliato (fixture 40+ verdi, nessuno
scenario utente che li smentisca). La procedura differenziale resta
armata per quando servirà. Cambiare pesi ora = churn su Why-card, UI,
fixture e CHANGELOG senza motivo dimostrabile. Vietato in review salvo
issue documentata.

## 4. Target di fine Phase 5 (delta vs Phase 4)

```text
scheduler.py:  sequenza collocazione = vincolate-oggi prima (stable),
               DayPlan e ragioni intatti
estimation.py: NUOVO — matematica calibration/estimation/confidence
domain.py:     delega a planner.estimation (stesse firme/valori)
capacity/calibration/decisions: import dal core, mai piu' da domain
guard:         zero 'src.domain' in src/planner/ + tabelle invariate
```

## 5. Sequenza (un commit per step)

1. **P5-1 — Spostamento matematica**: `estimation.py` + delega domain +
   rewire import interni + tabelle esistenti verdi (D1, calibration,
   execution_stats, task_execution). Solo trasloco, zero semantica.
2. **P5-2 — Guard zero-domain**: arch-test `src.domain` assente in
   `src/planner/*.py` (import-lines, stile T8) + docstring direzione
   dipendenze. Prova del disaccoppiamento.
3. **P5-3 — Feasibility-first**: chiave stabile in `schedule()` + golden
   (stranding risolto: A-libera-8🍅 + B-scadenza-10:00-1🍅 → entrambe
   collocate; fallback CONSTRAINED quando impossibile) + E-equivalenza
   date-only rieseguita identica.
4. **P5-4 — Documentazione semantica**: docstring scheduler (ordine vs
   merito), sprint log convenzionale; rivalutazione esplicita pesi =
   "nessuna evidenza, invariati".
5. **P5-5 — Gate + reviewer**: full pytest + ruff + format + mypy +
   `@reviewer`, nessuna release (cambi interni; lo slittamento slot su
   timed-dues è nicchia come P3-2 — §8).

## 6. Non-goals + rinvii motivati (Phase 5 NON implementa)

- **Pesi scoring**: invariati (nessuna evidenza; procedura differenziale pronta).
- **Calibrazione per-progetto/recency**: segmenterebbe i campioni sotto
  soglia (min 5) azzerando il factor ovunque — peggiorativo dimostrabile,
  non migliorativo ipotetico.
- **Execution-aware/remaining-work**: biforcazione estimate pieno/residuo
  con ricadute DayPlan/feedback/calibrazione/display senza consumatore —
  prematuro (9.5.3); rivisitare solo su domanda esplicita con disegno
  completo (candidato naturale: flusso replan G con progress reale).
- **Dipendenze tra task** (blocchi/predecessori): nessun modello, nessun
  consumatore — fuori anche da Phase 6/7, solo se mai richiesti.
- **Finestre multiple/UI temporali**: vedi rinvio Phase 3, invariato.
- **Diagnostica oltre esistente** (Phase 6), **API stabili** (Phase 7),
  **bump/release** di default (§8).

## 7. Strategia test

| # | Test | Tipo |
|---|---|---|
| M1 | Trasloco: tabelle D1 + calibration + execution_stats verdi su delega (rieseguiti, non riscritti) + parità TodoItem/TaskView | regression (retain) |
| G4 | `src.domain` assente negli import di `src/planner/*.py` | arch (nuovo) |
| F1 | Golden stranding-risolto + fallback + date-only identico + stabilità (stesso input, stesso output; DayPlan non riordinato) | unit (nuovo) |
| K2 | Suite complete invariate e verdi (merito/UI/fixture: prova del non-cambio) | regression (retain) |

## 8. Compatibilita' e release

- Firme invariate ovunque (spostamento interno + un ordinamento di
  collocazione). `domain.*` stesse firme/valori (solo delega).
- Slot possono slittare SOLO in scenari con scadenze-orario (nicchia);
  DayPlan/selezioni/motivi identici sempre.
- Default: **nessuna release**. Eccezione possibile (decisione utente):
  se lo slittamento feasibility-first merita annuncio — ma resta nicchia
  come P3-2, quindi default no.

## 9. Rischi

| Rischio | Mitigazione |
|---|---|
| Trasloco rompe import circolari | direzione unica domain→planner; planner mai importa domain (G4); suite piena |
| Domain delega con semantica driftata | delega letterale 1:1 + tabelle esistenti (nessuna riscrittura) |
| Feasibility-first sorprende (slot slittati) | solo con timed-dues; DayPlan invariato; golden + CONSTRAINED onesto |
| Tentazione pesi "già che ci siamo" | vietato in review senza issue documentata |
| Tentazione remaining-work parziale | vietato (§6): o disegno completo o niente |

## 10. Definition of Done

1. `estimation.py` fonte unica; `domain` delega identica; zero import
   domain nel planner (G4 verde).
2. Stranding deadline risolto con golden; date-only identico (E3 + suite).
3. Pesi/scoring/calibration-algoritmo intoccati (fixture verdi invariate).
4. Full gate + `@reviewer` OK; ADR-001 intatto; zero dipendenze nuove.
5. AGENTS.md/CHANGELOG solo se convenzione; nessuna release di default.

## 11. Split in commit

P5-1…P5-5 come §5. Messaggi `refactor(planner): phase5 step P5-N - ...`,
push utente, CI verde se la fase si allunga.

## Appendice — evidenze (verifica pre-stesura)

- Scheduler riletto: first-fit in ordine Planner; caso stranding
  costruibile e verificabile (A libera capiente + B stretta dopo).
- `domain.py:313-348` + `:543-560`: ratios/samples/factor +
  execution_factor/confidence — stessa policy (min 5, mediana, clamp),
  spostabile 1:1 (letture `.stima_pomo/.actual_pomo/.state` presenti
  su TaskView via alias/campi).
- Nessuna issue di miscalibrazione nota; fixture merito 40+ verdi.
- `pomodoro_log` per-task esiste (sessions oggi derivabili) ma senza
  consumatore di remaining → rinvio §6 (non mezza misura).
- `_clip_future`, factor seam, deadlines invariati in Phase 5.
