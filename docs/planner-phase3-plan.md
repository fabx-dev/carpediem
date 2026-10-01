# Phase 3 — Temporal Engine: implementation plan

*(Stesura in build mode, ma SOLO piano: nessuna modifica a codice/test in
questa sessione. Verificato contro il repo post-Phase 2 (P2-7, CI verde).
Riferimenti: `docs/planner-engine.md` §16 Phase 3 + §9 (modello temporale),
`docs/planner-phase2-plan.md`, `docs/adr-001-planner-boundary.md`
(invariato), `AGENTS.md` §9.)*

---

## 1. Executive summary

Phase 2 ha chiuso il core come dominio a sé (`plan(request)`, adapter
app-side, seam dichiarati). Phase 3 fa il passo previsto da
`planner-engine.md` §16:

> **Strengthen timezone policy, DST, availability, deadlines, duration,
> partial completion, temporal reasoning (§9).**

Stato attuale onesto (`CURRENT`): lo scheduler colloca first-fit in
finestre naive ignorando del tutto gli orari di scadenza (usa solo la
parte data via scoring); le durate convergono all'edge via due costanti
in lock-step (`POMO_HOURS` planner, `POMO_MINUTES` domain); le conversioni
tz avvengono solo al bordo Outlook (testate su DST); `day_window` è
singola; non esiste modello di avanzamento parziale; `request.now` non è
usato da `plan()`.

Principio di scoping (AGENTS.md §9.5.3, §9.10): Phase 3 ragiona sul tempo
**con i dati che esistono oggi**, senza tirare dentro scoring evoluto
(Phase 5), preferenze/soft-constraint (Phase 4), diagnostica strutturata
(Phase 6) né persistenza nuova. Due voci del §9 (finestre multiple,
avanzamento parziale) sono esplicitamente rinviate con motivazione
tecnica (§6), non per dimenticanza.

## 2. Punto di partenza (verificato)

- `scheduler.py`: first-fit su `plan.planned` in `availability − busy`,
  clip al giorno, merge busy, mai overlap, mai ore inventate; durate da
  `PlanItem.estimate_pomo × POMO_HOURS`; cut/skipped mai schedulati.
- `TaskView.due`: solo parte data (adapter riduce via `_date_part`);
  l'orario `HH:MM` del `due` sopravvive solo in storage/display/export.
- Nessun test di scheduling usa `due` con orario (grep 2026-10-01:
  timed-dues solo in export/nlparse/taskview/agenda/display) → il seam
  deadline-time scatta solo su scenari nuovi; equivalenza garantita.
- `day_window` config: singola `{start, end, events[], allday[]}`,
  validata; `day_window_parts` + `events_to_busy` nell'adapter.
- tz mailbox configurabile e validata (`storage.py:587`, default
  Europe/Rome); parse Outlook naive-in-zona/aware-con-offset → naive
  (`outlook.py:_parse_dt`, DST pinnato in `test_timezone_dst.py`).
- `request.now`: usato solo dal clipping replan (`_clip_future`); `plan()`
  non clippa (availability = intento dichiarato).

## 3. Decisioni architetturali (trade-off espliciti)

### T-Deadline: l'orario di scadenza come vincolo duro di collocazione

Raccomandazione: lo scheduler colloca una voce con scadenza odierna con
orario **solo in slot che finiscono entro la scadenza**; altrimenti resta
`unscheduled` strutturale (senza reason nuova, come i mandatory senza
slot oggi).

- Semantica precisa: vale solo se `due-date == plan.day` **e** `due-time`
  presente. Scaduto (due-date < day) → nessun vincolo (già tardi, si
  schedula normalmente); futuro (>) → nessun vincolo; senza orario →
  comportamento odierno identico (deadline = fine giornata implicita).
  Mezzanotte-passata (`00:30` con availability dalle 09:00) → onestamente
  unscheduled, mai resuscitato.
- Pro: deterministico, spiegabile con macchinari esistenti (unscheduled
  → `CONSTRAINED` se mandatory — e due-oggi implica mandatory — quindi
  la Why-card racconta già la storia giusta senza nuove chiavi);
  equivalenza totale sulle fixture esistenti (zero timed-dues).
- Contro: è un hard constraint che può svuotare il piano in scenari
  tirati (onesto, ma visibile all'utente) — mitigato dal fatto che scatta
  solo con orari espliciti digitati dall'utente.
- Respinte: (a) preferenza soft "prima della scadenza se possibile"
  (è Phase 4: preferenze sacrificabili, non di questa fase); (b) nuovo
  motivo `plan_deadline_*` (sarebbe diagnostica Phase 6 dalla porta di
  servizio; lo strutturale basta); (c) toccare lo scoring per l'orario
  (il merito resta a grana-giorno — Phase 5 semmai).

### T-Field: `TaskView.due_time`, non riuso del campo `due`

Raccomandazione: **nuovo campo `due_time: str` (`"HH:MM"` o `""`)**,
parsato nell'adapter dalla stessa semantica di `_due_time_part`
(copiata, non importata — come `_date_part` in Phase 1).

- Pro: `due` resta data-pura per scoring/ordinamento/evidence (zero
  regressioni nei confronti stringa); il tempo è esplicito e testabile
  fail-closed (T2 passa da 13 a 14 campi con modifica approvata: il
  consumer — scheduler — esiste davvero).
- Respinte: (a) tenere `due` intero e ri-estrarre ai siti d'uso
  (incoerente con la normalizzazione Phase 1, confronti `due` già
  sparsi); (b) `datetime` completo nel campo (il core ragiona a
  giorno+orario separati; un timestamp suggerirebbe aware-semantics che
  non esistono).

### T-Duration: un solo punto di conversione nel planner

Raccomandazione: `capacity.pomo_minutes(n)` unico convertitore
pomodori→minuti nel planner, usato da `scheduler._duration`,
`feedback` (estimate_minutes), `decisions` (evidence estimate_minutes);
`domain.POMO_MINUTES` resta (direzione import vietata) con commento
lock-step esistente. Zero matematica cambiata, solo chiamata unica.

### T-TZ: policy documentata, niente aware nel core

Raccomandazione: il core resta naive per vincolo storage (datetime aware
romperebbero i dati — convenzione repo). Phase 3: (1) policy canonica in
UN posto (docstring `scheduler.py` + header test); (2) audit wiring
mailbox-tz (config `tz` → header `Prefer` + target parse: verificare che
il `tz` di `parse_graph_events` arrivi davvero dalla config in tutti i
path, fix seemplici se no); (3) NESSUNA aritmetica aware nel core, NESSUN
handling del fold/gap DST nei calcoli naive — dichiarato come limite
noto (lo slot a cavallo dell'ora mancante dura 1h reale: documentato,
non fixato; il bordo Outlook resta l'unico punto tz-aware, già testato).

### T-Defer: finestre multiple e avanzamento parziale fuori

- **Finestre multiple**: lo scheduler supporta già liste; il meccanismo
  corrente (singola finestra + busy da eventi, incluso pranzo) copre il
  caso d'uso reale. Config-list + UI multi-input = lavoro UI + migrazione
  config senza domanda attuale → rinviato a Phase 4/5, motivato qui.
- **Avanzamento parziale** (`remaining = stima − lavorato`): richiede
  semantica stimata-vs-dichiarato-vs-sessioni (dominio estimation,
  Phase 5) + quasi certamente persistenza (stato avanzamento) + UI.
  Senza consumatore e con semantica controversa, qualunque scheletro ora
  sarebbe speculativo (9.5.3) → rinviato a Phase 5, motivato qui.
- **`now` in `plan()`** (auto-clip al passato): cambia output del
  Buongiorno e duplica il lavoro di `replan` (a cui il clipping
  appartiene, testato). L'availability resta intento dichiarato →
  nessun clip in `plan()`, documentato. Rivalutabile in Phase 5.

## 4. Target di fine Phase 3

```text
PHASE 3 TARGET (delta vs Phase 2)

  TaskView + due_time ("HH:MM"/"")     <- adapter parse, T2 a 14 campi
  scheduler: slot.end <= deadline       <- solo se due-date==day + time
             (scaduti/futuri/senza-ora: invariati)
  capacity.pomo_minutes()               <- unico convertitore planner
  policy tz canonica + wiring mailbox   <- docs + audit/fix
  guard: niente aware nel core, due_time formato, deadline golden
```

## 5. Disegno scheduler con deadline

```python
# scheduler.py — stesso first-fit, un filtro in più per voce:
def _deadline(item_due_date_s, item_due_time, plan_day) -> datetime | None:
    """Scadenza come limite superiore di fine-slot, o None se non applicabile.
    Solo due-date == plan.day + orario valido. Puro, totale."""
```

Collocazione: per voce con deadline `D`, candidati solo slot con
`slot.start + need <= min(slot.end, D)`. Il resto identico (consumo
progressivo dei free, unscheduled strutturale). Complessità invariata
(O(voci × free)).

Casistica (da fissare in test golden):

| due | day | window | risultato |
|---|---|---|---|
| oggi 10:00, 2🍅 | oggi | 09–18 | 09:00–10:00 ✓ |
| oggi 09:30, 2🍅 | oggi | 09–18 | unscheduled (non entra entro 09:30) |
| oggi 09:30, 1🍅 | oggi | 09–18 | 09:00–09:30 ✓ (bordo inclusivo: end <= deadline) |
| ieri 10:00 | oggi | 09–18 | schedulato normale (scaduto: merito, non vincolo) |
| domani 10:00 | oggi | 09–18 | schedulato normale |
| oggi, senza ora | oggi | 09–18 | invariato |
| oggi 00:30 | oggi | 09–18 | unscheduled (finestra già oltre) |
| busy 09–12 + oggi 10:00 | oggi | 09–18 | unscheduled (il buco 12+ è oltre) |

`_clip_future` (replan) invariato — opera su availability, ortogonale.

## 6. Sequenza di migrazione (un commit per step)

1. **P3-1 — Campo**: `TaskView.due_time` + parse adapter (`_due_time_part`
   locale in `models.py`) + T2 a 14 campi + U-test normalizzazione
   (`"2026-09-10 14:00"` → due+due_time; garbage → `""`). Solo additivo.
2. **P3-2 — Scheduler**: `_deadline` + filtro first-fit + golden §5 +
   E-equivalenza (matrice esistente date-only identica: già garantita
   dal fatto che nessun fixture usa orari, ma pinnata esplicitamente).
   Nessuna chiave i18n nuova, nessuno scoring toccato.
3. **P3-3 — Durate**: `pomo_minutes()` + riuso in scheduler/feedback/
   decisions + lock-step comment; tabella minuti (30/60/90…) + full green.
4. **P3-4 — TZ policy**: docstring canonica + audit wiring mailbox-tz
   (fix solo se il grep trova un path che non passa la config) + test
   bordo esistenti rieseguiti; dichiarazione limite DST-naive.
5. **P3-5 — Guard + docs**: T8-style — niente `tzinfo`/`astimezone`/
   `ZoneInfo`/`utcoffset` in `src/planner/` (solo docstring ammesse);
   `due_time` formato `HH:MM`/`""` (test); sprint log convenzionale.
6. **P3-6 — Gate + reviewer**: full pytest + ruff + format + mypy +
   `@reviewer`, nessuna release (comportamento nuovo ma interno? —
   vedi §8).

## 7. Strategia test

| # | Test | Tipo |
|---|---|---|
| D1 | `due_time` parse/normalizzazione + T2 a 14 campi | unit (nuovo/adattato) |
| D2 | Golden §5 (8 righe) + first-fit invariato fuori deadline | unit (nuovo) |
| E3 | Equivalenza date-only: matrice Phase-1/2 + scheduler esistenti identici (dovuto: nessun orario) — rieseguiti come cancello, non riscritti | characterization (retain+pin) |
| M1 | `pomo_minutes` tabella + lock-step comment entrambi i lati | unit (nuovo) |
| Z1 | Policy doc test? No — policy in docstring; wiring tz audit via test se fix, altrimenti grep-evidence | audit/fix |
| G2 | Guard aware-free + due_time-formato | arch (nuovo) |
| K2 | Tutte le suite esistenti invariate e verdi (UI pilot incluse: nessun cambio UI in Phase 3) | regression (retain) |

## 8. Compatibilita' e release

- `DayPlan`/`ScheduledDayPlan`/`PlanningRequest`/`PlanningResult` invariati
  (nessun campo nuovo sui contratti — la deadline viaggia dentro
  `TaskView`, già parte dell'input).
- T2 cambia (13→14 campi): modifica approvata con consumer reale (§3 T-Field).
- UI: zero modifiche (slot/unscheduled già renderizzati; CONSTRAINED già
  raccontato). Niente chiavi i18n nuove.
- Release: visibile solo in scenari con scadenze-orario (nicchia: chi
  digita `HH:MM` nel due + Buongiorno con finestra). Default: **nessuna
  release dedicata** (invisibile per la maggioranza); rivalutare solo se,
  a fase chiusa, il comportamento deadline risulta da annunciare —
  decisione utente, non automatica.

## 9. Rischi

| Rischio | Mitigazione |
|---|---|
| Deadline svuota piani tirati (unscheduled a sorpresa) | scatta solo con orari espliciti utente; CONSTRAINED lo spiega in Why; golden pinnati |
| Bordo `end == deadline` ambiguo | convenzione inclusiva (`<=`), golden dedicato |
| Tentazione preferenze soft ("meglio prima") | vietato in review (Phase 4); il filtro è binario |
| Tentazione motivi/diagnostica nuovi | vietato (Phase 6); riuso unscheduled/CONSTRAINED |
| Scope-creep finestre/partial/clip | §6 li chiude con motivazione; review li respinge |
| `_due_time_part` duplicata (terza copia dopo models) | copia locale minima in `planner/models.py` con commento-fonte (precedente `_date_part` Phase 1) |

## 10. Non-goals (Phase 3 NON implementa)

- niente scoring/ordinamento per orario; niente pesi nuovi;
- niente finestre multiple in config/UI; niente working-windows;
- niente modello avanzamento parziale né persistenza nuova;
- niente aware/DST nel core; niente handling fold/gap naive;
- niente auto-clip `now` in `plan()`; niente chiavi i18n/motivi nuovi;
- niente stabilizzazione API, package, adattatori esterni;
- niente bump versione/release di default (§8).

## 11. Definition of Done (oggettiva)

1. Task con scadenza-oggi-orario collocati solo entro la scadenza (golden §5 verdi); resto identico (E3 + suite verdi).
2. `due_time` in TaskView con T2 a 14 campi; adapter parse totale.
3. `pomo_minutes()` unico convertitore planner; lock-step documentato.
4. Policy tz canonica scritta; wiring mailbox verificato (fix se rotto); limite DST-naive dichiarato.
5. Guard G2 verdi; full gate (pytest+ruff+format+mypy) + `@reviewer` OK.
6. ADR-001 intatto; nessuna dipendenza nuova; nessuna chiave i18n nuova.
7. AGENTS.md/CHANGELOG solo se convenzione; release solo su decisione utente.

## 12. Split in commit

P3-1…P3-6 come §6 (P3-2 eventualmente in due: helper+test poi filtro).
Messaggi `refactor(planner): phase3 step P3-N - ...`, push dal terminale
utente, CI verde tra un blocco e l'altro se la fase si allunga.

## Appendice — evidenze (verifica pre-stesura 2026-10-01)

- Scheduler riletto (first-fit, clip-day, merge-busy, `_duration` da
  estimate×POMO_HOURS); `due` usato solo come data in scoring/ordering.
- Grep timed-dues: solo export/nlparse/taskview/agenda/display + 1 test
  facade documentato — zero in scheduling. Seam sicuro.
- `storage.py:476,502` day_window singola validata; `outlook.py:71-96`
  conversioni edge; `storage.py:587` tz mailbox validata default
  Europe/Rome; `test_timezone_dst.py` 8 test bordo DST.
- `request.now` usato solo da `_clip_future` (replan); `plan()` non clippa.
- Engine §9 riletto: la lista è direzione, non checklist obbligatoria —
  §9.10 autorizza il defer motivato (qui: finestre multiple, partial,
  clip-auto).
