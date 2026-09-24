# CarpeDiem — contesto per le sessioni agent

> Leggere questo file all'inizio di ogni sessione di lavoro sul repo.
> Se il tuo commit cambia fatti documentati qui (architettura, convenzioni,
> workflow, lezioni apprese), aggiorna questo file nello stesso commit.
> In caso di dubbio, aggiorna.
> Lingua dell'utente: italiano. Risposte concise, niente emoji.

## 1. Cos'è

**CarpeDiem** (progetto `carpediem` su PyPI, entry-point `carpediem = src.main:main`) è una
TUI todo-list in italiano/inglese costruita con **Textual** (>=0.86,<4; in venv: 3.7.1).
Python >= 3.12. Repo: `git@github.com:fabx-dev/carpediem.git`, branch `main`.

Avvio: `carpediem` (TUI) oppure `python -m src.main ...` / `.venv/bin/python -m src.main ...`.
CLI non interattiva: `carpediem add|list|done|show` (+ `--porcelain`).

Feature principali: task con 3 stati, sotto-task annidati, ricorrenze, progetti/tag/priorità,
kanban (mini in home + full), agenda cronologica, calendario, settimana, piano giornaliero,
pomodoro persistente a cicli, template (creabili, anche da progetto), statistiche, goals,
salute progetti, archivio, backup/snapshot zip, import/export CSV + export Markdown +
export iCal, cifratura Fernet opzionale, onboarding demo, **chiusura giornata**
(review serale, tasto `R`), inserimento in linguaggio naturale (form `ctrl+l`, CLI add),
buongiorno unificato (tasto `P`: contesto di oggi + proposta con motivi da confermare),
resoconto sera (solo palette, zero rete), cockpit UX (riga giorno `!`/durata/scadenza,
Detail `Tu/CarpeDiem/Reale`, replan preview `G`, review settimana `W`).

## 2. Mappa del codice

```
src/main.py      entry point + re-export compatibilità + init lingua PRIMA degli import
src/app.py       TodoApp(App): orchestratore (~2570 righe, 166 funzioni) — è la god-class nota
src/screens/     package per area (form/views/plan/system/menu + _shared + re-export
                 in __init__): 34 modali + MenuRow; dipendono solo da models/storage/
                 lang/nlparse/plan/domain (+ _shared), mai app — via push_screen+callback;
                 MenuScreen a 2 colonne (voci a sx -> sottomenu a dx,
                 conftest ricarica i sottomoduli in ordine per le stringhe it)
src/nlparse.py   parser deterministico NL it/en → dict uguale al result di TodoFormScreen;
                 sigilli #tag *progetto !prio ~stima //note, parse_with_found() per merge
src/plan.py      plan_day() pura: score, capacita' ore/0.5 🍅, motivi (chiave, params)
src/planner/     service Planner (application boundary, Fase 1: propose() delega
                 a plan_day); usato da PlanProposalScreen; contratto in tests/test_planner.py
                 Fase 2: Planner orchestratore (scoring/constraints/capacity/explain);
                 plan.py resta wrapper compatibile; factor None = auto-calibrazione
                 Fase 3: propose() restituisce DayPlan (models.py: PlanItem/DayPlan
                 frozen, planned/cut/skipped + capacity_pomo/planned_pomo/factor);
                 plan_day() = propose().to_legacy(); screen consuma DayPlan via .rows
                 Fase 4: scheduler temporale deterministico (scheduler.py puro +
                 TimeWindow/ScheduledItem/ScheduledDayPlan in models.py);
                 Planner.schedule() thin wrapper; availability esplicita, niente default
                 Fase 5: feedback di esecuzione (feedback.py puro +
                 ExecutionFeedback in models.py: estimate/sessions/actual/completed);
                 solo derivazione, niente auto-calibrazione
                 Fase 6: boundary di calibrazione (calibration.py sottile:
                 observe/observe_all/factor_for, matematica in domain);
                 capacity.estimate delega a domain.calibrated_estimate
                 M3: decisions.py puro (PlanningDecision/decide/
                 refine_with_schedule/primary_reason; UI via Detail Why)
                 M4: replan.py puro (ReplanProposal/ReplanMove kept/moved/
                 dropped/added; availability clippata a [now, fine];
                 commit via domain.apply_replan + carpediem replan CLI)
src/domain.py    regole di dominio pure (stato+ricorrenza, pomodori, form, piani):
                 mutano solo i TodoItem passati, timestamp espliciti, mai I/O/UI;
                 app/screen applicano e persistono via store.commit();
                 M2: make_execution/variance/stats/confidence/predicted + POMO_MINUTES=30
                 (lock-step con planner.capacity.POMO_HOURS, import inverso = ciclo)
src/models.py    TodoItem, Priority, Recurrence, validazioni date, MAX_DEPTH=6;
                 campi extra: stima_pomo, planned_for, plan_skip (scarto piano smart, data);
                 M2: TaskExecution frozen-less (minuti canonici + snapshot estimate_pomo)
src/store.py     TodoStore: lookup id, mutazioni, next_id, commit() = UNICO punto di scrittura todos
src/storage.py   paths, load/save (todos/template/config/archive/pomodoro), lock, merge, backup;
                 config include day_hours (default 6, clamp 1-16);
                 M2: EXECUTIONS_FILE + load/append (append-only, dedup atomica, cap 5000)
src/crypto.py    Fernet + PBKDF2 (600k iter), chiave solo in RAM, envelope {"v","salt","data"}
src/cli.py       add/list/done/show/replan (add/done via TodoStore: lock+merge gratis); add senza flag = NL
src/commands.py  MENU_STRUCTURE (4 categorie: giornata/viste/dati/sistema, chiavi i18n +
                 action + shortcut) + CarpeDiemMenuProvider (palette `ctrl+p`, titoli
                 "Categoria › Voce"); MENU_IT piatta tenuta per compatibilita'
                 M-UI: ReplanPreviewScreen/WeekReviewScreen (cockpit #50/#51)
src/lang.py      catalogo STRINGS it/en + key_sections (help) — vedi §4
tests/           ~146 test; conftest.py con fixture di isolamento (vedi §5)
```

Flusso dati standard nelle action: muta oggetti → `store` → `_save_data()` (= `store.commit()`)
→ `_populate_table()`. Le screen non salvano mai su disco (solo lettura via `_backup_sources`).

## 3. Dati e persistenza

File in home (o `TASKO_HOME` se impostata — usata dai test): `.todo_app.json`,
`.todo_templates.json`, `.todo_config.json`, `.todo_pomodoro.json`, `.todo_archive.json`,
più `.bak.json` / `.corrotto.json` / `.lock` collaterali e `Tasko_backups/*.zip`.

Regole dure:
- Scritture sempre atomiche tmp+fsync+replace, sotto lock fcntl (`_locked`, timeout 10s,
  `StorageLocked` oltre). Niente lock stali (il kernel li rilascia).
- `store.commit()` = lettura+merge+scrittura sotto **un solo lock** (`save_todos_synced`).
  Merge three-way per id (`merge_todo_dicts`): nuovi da entrambi i lati in unione, vince chi
  ha modificato, entrambi modificati vince chi salva, cancellato-vs-modificato vince la
  modifica (cancellato da un lato con l'altro intonso → resta cancellato), stesso id creato
  da entrambi → disco tiene l'id, nostro riassegnato. Dopo il commit la memoria rispecchia
  il merged (item esterni compaiono, `_base` è sincronizzato col disco: si riusa l'oggetto
  live solo se coincide col merged). Disco cifrato non decifrabile con la chiave corrente
  (cambio password) → `save_todos_synced` riscrive la memoria com'è, senza merge.
- File cifrato senza chiave in RAM → `[]` **senza** backup `.corrotto` (non è corrotto, è
  blindato). Chiave errata → `[]` + backup. Dopo l'unlock l'app fa `_reload_all()`.

## 4. Convenzioni (rispettarle sempre)

- **i18n**: ogni stringa UI via `T("chiave", ...)`; `test_parita_chiavi` impone stesse chiavi
  it/en — chiavi nuove sempre in entrambe le lingue. `T()` valutato all'import (BINDINGS,
  MENU_IT) segue la lingua fissata da `_apply_startup_lang()` in main: non spostare gli import.
- **CSS**: shell modali condivisa in `TodoApp.CSS` (sezione "Shell modali condivisa": root
  `ModalScreen`, gruppo 24 box, gruppo 12 titoli, gruppi bottoni chiudi). Nuove screen:
  aggiungere i propri `#x-box`/`#x-title` a quei gruppi, dichiarare in screen solo lo specifico.
- **Bottoni**: tutti `variant="default"`; coppie azione = `form_save` ("Salva [s]") +
  `form_cancel` ("Annulla [esc]"); solo visione = `ui_close_esc` ("Chiudi [escape]").
  `ctrl+enter` resta come binding secondario ma NON affidarti solo a lui: molti terminali
  (Windows Terminal/WSL) non lo consegnano all'app — `s` funziona ovunque (i campi di
  testo consumano i caratteri, quindi non scatta mentre digiti).
- **Tasti globali**: superficie già ampia (~30 binding). Nuovi tasti solo su richiesta esplicita;
  preferire palette/menu. `m` = menu per funzioni (categorie -> voci),
  `ctrl+p` = palette di ricerca. Convenzione maiuscole = variante (`b/B`, `o/O`, `r` ricarica / `R` review;
  eccezione approvata: `P` = piano smart, coppia di `p` = piano giorno;
  cockpit: `G` = replan preview, `W` = review settimana, coppie di `g` filtro
  progetto / `w` settimana).
- **Nuove screen con lista scrollabile**: box ad altezza definita (`height: 90%`) + figlio
  flessibile (`height: 1fr`) — MAI box auto + `max-height` con figli auto (lezione stats:
  il contenuto sborda o avanza cornice vuota). `plan-box`/`rev-box`/`arc-box`
  verificati al pattern nuovo (pilot 70x20/80x24, Chiudi dentro la cornice).
- **SelectionList**: le label interpretano il markup Rich — niente `[...]` nelle option
  (vengono mangiate come tag di stile); usare parentesi tonde. Precedente: motivo
  di taglio sparito dal piano smart.
- **Edit**: blocchi BINDINGS/CSS duplicati tra classi diverse (es. form vs import-CSV):
  usare sempre contesto ampio in oldString e verificare con grep dove è finito l'edit.
- **Mai crash da UI**: except ampi intenzionali (ruff esclude BLE/S110/S112 di proposito).
- Date wall-time `"YYYY-MM-DD [HH:MM]"` (niente aware — romperebbe i dati, ruff esclude DTZ).
- `ruff check` **E** `ruff format --check` (la CI li corre entrambi + pytest su 3.12 e 3.13).
- Prima di ogni commit puoi lanciare `@reviewer`: subagente read-only in
  `.opencode/agents/reviewer.md` che controlla diff contro queste convenzioni
  + ruff + pytest, e chiude con `OK per il commit` o elenco bloccanti.

## 5. Verifica (obbligatoria prima di dire "fatto")

- Test: `.venv/bin/python -m pytest tests/ -q`. Mai toccare i file reali di `~`:
  usare `TASKO_HOME` temporanea o la fixture `tmp_files` di conftest (autouse, redireziona
  tutti i path). Precedente grave: un test scrisse su `~/.todo_app.json` cancellando dati veri.
- Gate completi prima del push: `pytest` + `ruff check` + `ruff format --check` +
  `mypy src/` (la CI corre tutti e quattro; un push e' fallito solo per mypy mai
  lanciato in locale: `getattr` non restringe `str | None` per mypy).
- `conftest` fa `reload()` dei moduli a inizio sessione: nei test usare import di modulo
  (`import src.storage as s`) e non `from ... import nomi` (restano stali).
- Pilot Textual: `async with app.run_test(size=(120, 40))`, `await pilot.pause()` doppia dopo
  le action modali. `SelectionList`: option `(label, value, selected_init)`, metodi
  `select/deselect/toggle(value)`, prop `selected`.
- Testo screen nei test: helper `screen_texts()` di conftest (gestisce `.content`/`.renderable`);
  attese via `T(chiave)` non stringhe hardcodate (la lingua effettiva dipende dall'env).
  Mai `.content` diretto: non esiste in tutte le versioni di Textual (la CI installa
  la più recente <4, diversa dalla venv) — ha rotto la CI una volta.
- Script ad-hoc (`python -c`, screenshot): senza `TASKO_LANG=it` l'app parte in inglese
  (auto→locale container). Per output italiani: `TASKO_LANG=it` davanti al comando.
- Script ad-hoc con pilot (`make_app` + `run_test` fuori pytest): SEMPRE con `TASKO_HOME`
  fresca e isolata (`export TASKO_HOME=$(mktemp -d)`), perché qualunque action che
  chiama `store.commit()` (es. `+` nel piano) scrive sui path reali. Precedente
  2026-09-14: script senza `TASKO_HOME` sovrascrisse `~/.todo_app.json` con 4 task
  finti, recuperato dal backup zip del giorno prima (i test `pytest` erano salvi
  grazie alla fixture `tmp_files`). **Recidiva 2026-09-21, piu' grave**: heredoc di
  debug di 10 righe senza isolamento durante il fix di test -> wipe dei dati reali
  cifrati (recuperati dal zip auto-backup del mattino) — vedi incidente in §7. Le
  due regole dure: (a) nessun `TodoApp()`/`run_test`/import di `src.app` senza
  `TASKO_HOME` nel MEDesimo comando, verificato con `echo` prima dei run sensibili;
  (b) dopo un debug sospetto, controllare mtime/dimensione di `~/.todo_app.json`
  PRIMA di continuare (un wipe e' un file non-envelope o un envelope minuscolo).
- Screenshot SVG per cambi visivi: script con `TASKO_HOME` **fresca per run** (il restore del
  pomodoro altera i run successivi!), estrazione testo via regex `<text>` + `html.unescape`
  (gli spazi sono `&#160;`: normalizzare prima di cercare), verifica sopra+SOTTO il fold
  (`scroll_end` per i bottoni). Byte-compare = falso.
- LockScreen nei test ad-hoc = file reali cifrati sotto `~`: usare sempre `TASKO_HOME` isolata.

## 6. Git e CI

- Commit piccoli e descrittivi in inglese (stile log esistente). Mai `--force`/push da sandbox.
- **La sandbox NON può pushare** (SSH senza passphrase): commit in locale, l'utente pusha dal
  suo terminale con `git push origin main`, poi si ricontrolla la CI con `gh run list`.
- CI (`.github/workflows/ci.yml`): `ruff check` + `ruff format --check` + pytest su 3.12/3.13.
  Lezione: un push è fallito solo per `ruff format` mai lanciato in locale — correrlo sempre.
- Split di commit misti: classificare hunk per marker (occhio alle righe di contesto vuote nei
  diff, che non hanno prefisso e sballano i conteggi) e validare con round-trip
  stash → apply → commit → md5 dei file. `git apply --check` su un diff del working tree
  fallisce sempre per costruzione: non è un segnale utile.
- **Versionare per PyPI a ogni cambiamento visibile**: bump `version` in
  `pyproject.toml` + voce in `CHANGELOG.md` (inglese, stile Added/Changed/Fixed
  esistente) prima del push — mai lasciare una feature committata senza versione
  (la publish parte dalla release GitHub, `publish.yml`, e la versione pubblicata
  deve già contenere tutto). Numerazione: patch per fix, minor per feature.

## 7. Sprint log (fatto)

- **S1**: `TodoStore` + `commit()` centralizzato; `todos`/`next_id` restano property compatibili.
- **S2**: lock fcntl + merge three-way + CLI via store; `test_concurrency.py`, `test_failure_paths.py`.
- **S3**: rimossi `_trash`, `action_toggle_theme`, `_apply_startup_lang` duplicato; CSS condiviso
  (−298 righe); `build/` untracked + gitignore esteso; pyproject 0.3.0 + CHANGELOG Unreleased.
- **S5**: `ReviewScreen` (riepilogo oggi vs goal + pomodori, `SelectionList` candidati con top-3
  preselezionati, conferma = piano di domani esatto); ingresso da palette/menu + tasto `R`;
  `test_review.py`. Fix successivi: bottoni uniformati, box 100 col, label help "chiusura giornata".
- **AI-1**: `src/nlparse.py` (`parse(text, lang)` → dict del form; `#tag *progetto !prio ~stima`,
  date it/en, regole ambiguità nel docstring) + `tests/test_nlparse.py` (57 it + 49 en).
- **AI-2**: `ctrl+l` nel form (pre-compila + anteprima persistente) + `carpediem add "<frase>"` NL
  (con flag = modalità classica, titolo alla lettera); chiavi `nl_*`, `cli_empty_title`;
  `tests/test_nl_integration.py`. Lezione: binding finito per sbaglio su ImportCsvScreen
  (blocchi BINDINGS duplicati) — vedi §4.
- **AI-3**: `src/plan.py` (`plan_day`: pesi espliciti, capacità ore/0.5, `plan_cut`, motivi
  `(chiave, params)`) + chiavi `plan_*` + `tests/test_plan.py` (9 scenari).
- **AI-4**: `PlanProposalScreen` (tasto `P` + palette; conferma SOLO additiva: i già
  pianificati non si ripropongono, per togliere c'è il piano `p` con `x`; scarti del
  giorno in `plan_skip`) + settings `day_hours`; `tests/test_plan_ui.py`. Lezione: `[]`
  mangiati dal markup nelle option — vedi §4.
- **AI-5**: `BriefingScreen` mattina/sera (solo composizione dati esistenti, zero rete) da
  palette; `tests/test_briefing.py`. Stop-criterion manuale: lettura reale 5 giorni.
- **Menu**: `m` = `MenuScreen` a 2 colonne (voci a sx -> sottomenu a dx,
  tutto allineato a sinistra, righe compatte titolo+aiuto; click/Enter apre,
  Enter entra sempre, nuovo click = toggle; frecce + 1-4 + type-to-filter,
  esc a stadi filtro/sottomenu/menu),
  categoria `Giornata` raggruppa le viste temporali (Agenda, piano giorno, piano smart,
  settimana, calendario, briefing/resoconto/review); `ctrl+p` resta palette
  (`CarpeDiemMenuProvider`, titoli "Categoria › Voce") ma è nascosto dal footer
  (`Footer(show_command_palette=False)`); nel footer si mostra solo `m` come `☰ Menu`;
  menu completo anche delle azioni con tasto; `tests/test_menu.py`.
  Lezioni: righe come `MenuRow` (Label focusable), non Button — il Click del
  mouse (on_click sulla riga) e l'Enter (binding activate) restano
  distinguibili (Button.Pressed li confonde) e niente debounce -active;
  alle coordinate dell'evento in bolla non affidarsi (offset consumati);
  il filtro cattura i caratteri in on_key + stop() (i binding globali
  scattano prima); gruppi dropdown pre-costruiti e commutati via classi
  (remove+mount rapidi in sequenza danno `DuplicateIds`); focus via
  `call_after_refresh` con guardia su `_open_idx`.
- **Agenda/iCal/Menu giornata**: `AgendaScreen` cronologica (scaduti, oggi, domani,
  prossimi 7 giorni, alta priorità senza data) solo da menu/palette; export iCal `.ics`
  manuale dei task non completati con `due`; menu ripulito spostando calendario/settimana
  nella categoria `Giornata`; `tests/test_agenda_ical.py`.
- **Health layout**: `HealthScreen` passata al pattern cornice fissa
  (`#hea-box height 90%` + `#hea-list height 1fr`): a terminale piccolo la
  lista sforava e il Chiudi usciva dalla cornice; regression test
  `test_health_layout_terminale_piccolo` (120x40, 80x24, 70x20).
- **Test Pilot**: `pilot.click` ravvicinati sullo stesso `Button` sono inghiottiti
  dal debounce visivo (`-active` 0.2s in `Button._on_click`) — nei test con
  toggle azzerare `active_effect_duration`; dopo i click usare attesa a
  condizione (`_wait_for`) invece di pause fisse (runner CI lenti).
- **Workflow**: `WorkflowScreen` statica (guida operativa checklist in 5 blocchi:
  cattura/mattina/giorno/sera/settimana), prima voce di `Giornata`
  (`action_view_workflow`, nessuno shortcut); chiavi `menu_workflow_*` +
  `workflow_*` it/en; sezione settimana con rimando esplicito a
  `Viste e analisi → Obiettivi`; `tests/test_workflow.py`.
- **Release 0.4.0**: bump `pyproject` 0.3.0 → 0.4.0, CHANGELOG datato 2026-09-12,
  descrizione `pyproject`/README riscritte in tono pratico + installazione in 4 passi
  (pipx consigliato, venv per dev, verifica con `carpediem --help`/`list`).
- **Buongiorno unificato**: briefing mattina + piano smart fusi in un'unica
  `PlanProposalScreen` (voce `Buongiorno`, tasto `P`): contesto ex briefing
  (conteggi/carico/ieri/serie) + proposta con motivi inline, senza stampa
  (il piano su disco e' il documento vero); legend `s salva` come il bottone;
  `BriefingScreen` resta solo sera (hint morto `R...` → riga guida onesta
  `chiudi + R`); `ReviewScreen` al pattern cornice fissa (`#rev-box 90%` +
  `#rev-list 1fr`) con regression test a 3 taglie; `#brief-*`/`#planp-*`
  nei gruppi CSS condivisi; chiavi `menu_morning_*`, rimosse `menu_plan_*`,
  `menu_brief_*`, `brief_m_title/empty/sec_top/hint`;
  `tests/test_plan_ui.py` (+2), `test_briefing.py` riscritto sera-only,
  `test_review.py` (+layout piccolo).
- **Buongiorno UX fix**: riga `planp_additive` (solo aggiunge, N restano, Esc non
  scrive), summary con già-pianificati, flag con `—`, notify con aggiunti/
  presenti/rimandati, fix stato vuoto mai mostrato, contenuto in scroll con
  legend+bottoni fissi (test layout 80x24/70x20); test Esc-no-write + DB vuoto.
- **Cambia stato uniformato**: griglia 2x2 con frecce spaziali (`_focus_shift` ±1/±2)
  + Enter, via binding `1/2/3` e hint numerici; label senza tasti (`Attivo` ecc.,
  ex `O/P/X` mai bindati), titolo con stato attuale + `●` sul bottone corrente
  (focus sul corrente, `current_state` passato dal caller), `#state-msg` nel
  gruppo titoli condiviso, legend `state_legend`; copertura dedicata
  `tests/test_state.py` (Space, frecce su/giu/sx/dx, Enter, numeri inerti,
  click, esc-no-write). Lezione test: filtro default `attivo` nasconde i
  sospesi; `screen_texts` ignora i bottoni (marker verificato sul widget).
- **Flusso sera**: `ReviewScreen` con riga `rev_additive` (sovrascrittura
  dichiarata) + notify con rimossi + label senza `#id` + escape `[...]` nei
  titoli (helper `_escape_markup`, riusato anche in Buongiorno); contenuto in
  scroll con legend+bottoni fissi (il test a 70x20 falliva dopo l'aggiunta
  della riga); `BriefingScreen` sera con hint fisso fuori scroll + bottone
  ponte `brief_goto` (dismiss `"review"` + callback `on_briefing_done`, niente
  shortcut nuovi), stampa senza hint, empty mai-pianificato vs svuotato;
  chiavi `rev_additive/brief_goto/brief_e_left_never`; niente fusione
  (intenti distinti: celebrare oggi vs decidere domani).
- **Refactor Fase 1/2 (fatti)**:
  - Quick win: stringhe tabella i18n (`col_id/col_tags/table_empty`), `clear_filters`
    resetta anche `config["filter_state"]` + salva, `StatsScreen.TIME_SLOTS` da
    attributo a property (i18n a runtime), rimosso `TEMPLATES` morto, `load_templates`
    usa `_default_templates()`, `load_config` riusa `_clamp_int`; test: via check su
    `~` hardcodato, sleep reali rimosse (fake `datetime` + attesa a condizione),
    helper `run`/`wait_for` in conftest.
  - Convenzioni nuove (da rispettare): le action che mutano+salvano usano
    `_commit_refresh(chiave_notify, **params)` invece della tripletta
    save+refresh+notify; le screen di pianificazione ricevono `self._on_plan_changed`
    (non closure duplicate); screen modali con `action_close` = solo `dismiss()`:
    usare `CloseMixin` (le screen tengono i propri BINDINGS); righe bottone a
    `width:1fr; min-width:14; height:3; margin:0 1` → `classes="btn-row"` (regola
    condivisa in `TodoApp.CSS`), le varianti specifiche (form/confirm/brief/pomo/sec)
    restano per-screen. Lezione: non mettere bottoni-pair (es. `#planp-close`) nel
    gruppo close full-width — la regola id batte `.btn-row` e allarga il bottone.
  - Aggregatori condivisi: `_completed_by_date`/`_pomodoros_by_date` come helper di
    modulo; Review/Briefing/Stats non reimplementano più streak/done/pomo per giorno.
- **Refactor Fase 3/4/5 (fatti)**:
  - `src/domain.py`: transizioni stato+ricorrenza, pomodori, form, piani come funzioni
    senza I/O/UI (timestamp espliciti); app/screen applicano e persistono via store.
  - `src/screens/` package per area (form/views/plan/system/menu + _shared, re-export
    in `__init__`); conftest ricarica i sottomoduli in ordine per le stringhe it.
  - Dati: `restore_snapshot` con backup preventivo + lock; `descendants`/`depth`
    resistenti a cicli parent_id; `created` vuoto resta vuoto (lo stampa `store.add`);
    noid deduplicati in forma canonica nel merge; `_derive` in cache LRU;
    `password_to_key` → `encode_password`; scrittura semplice solo `_save_todos_plain`
    (seed/test, mai produzione).
- **Bug-hunting dati (2026-09-13, fatto)**: 7 fix persistenza — ricorrenza eredita
  `stima_pomo`; `commit()` conta gli scarti in `last_skipped`; merge: figli nostri
  seguono il padre riassegnato dopo collisione id (input non mutati); backup con
  letture sotto lock + nomi a microsecondi; restore con validazione JSON upfront,
  lock per-file, tmp+fsync e rollback; guardrail `test_plain_mai_in_produzione`;
  lock: test contesa cross-thread. Nota: restore con entry non-JSON ora rifiuta
  con OSError senza toccare il disco (prima scriveva spazzatura).
- **Bug-hunting UI giro 2 (2026-09-13, fatto)**: escape `_escape_markup` su OGNI
  interpolazione utente (titoli/note/tag/progetti/nomi template/filtri/notify/errori):
  `[/]` nei titoli sollevava `MarkupError` e crashava il dettaglio
  (`tests/test_markup_escape.py`); 11 screen al pattern cornice fissa
  (`tests/test_layout_small.py`, 70x20/80x24); `check_action` blocca le action App
  sotto modale (tranne `focus_next/previous` — il Tab passa dal guard! — e `open_day`
  calendario→giorno); click `[@click]` negli Static mai dispensati da Textual
  (solo hover): handler rinominati sui metodi reali + test per parti. Nota: screen
  che aprono altre screen usano `push_screen` diretto o dismiss+callback (mai action),
  quindi il guard non rompe i flussi legittimi.
- **Screenshot README (2026-09-14, fatto)**: `home.svg`/`stats.svg` rigenerati
  (mostravano ancora `Tasko` pre-rinomina) + 4 nuovi `buongiorno-it/en.svg`
  (`P`) e `review-it/en.svg` (`R`) da dati demo via pilot isolato
  (`TASKO_HOME` fresca per run, `set_lang`+reload come conftest per le stringhe
  all'import; lezione: impostare anche `TASKO_LANG` in env, altrimenti il reload
  di `src.main` riesegue `_apply_startup_lang()` che col locale non-it congela i
  BINDINGS/footer in inglese mentre il resto resta italiano); README.it punta ai `-it`, README.md ai `-en`.
- **SUB_TITLE i18n (2026-09-14, fatto)**: `TodoApp.SUB_TITLE` hardcoded it →
  `T("app_subtitle")` (chiavi `app_subtitle` it/en); segue la lingua di avvio
  come BINDINGS/footer (lingua a runtime richiede riavvio da Settings).
- **Rinomina CarpeDiem + prima pubblicazione PyPI (2026-09-13, fatto)**:
  `tasko` occupato su PyPI (omonimo SQLite) → progetto/comando `carpediem`
  (verificati liberi: xtasko/ytasko/mytasko/daydone/buondi valutati e scartati).
  Invariati per continuita': dati `~/.todo_*`, backup `tasko_*.zip`+manifest,
  env `TASKO_*`, dir `Tasko_backups/`. Publish via trusted publishing OIDC
  (`.github/workflows/publish.yml`, zero token): release GitHub → PyPI auto,
  dispatch manuale → TestPyPI. Prima release reale 0.5.1 su PyPI. Nota: repo
 GitHub rinominato `fabx-dev/carpediem` (redirect automatici).
- **Piano operativo (2026-09-15, fatto)**: il piano giorno `p` non e' piu' solo
  espositivo — `Enter` apre `DetailScreen` (con modifica via form, catena corta
  form→piano) e `Space` apre `StateChoiceScreen` a 3 stati come in home
  (su qualunque riga, ricorrenze via `on_add`), come prometteva il workflow sez.3
  (`tests/test_plan_operate.py`, 7 test; `test_dailyplan.py` adeguato al nuovo Space).
  Lezioni: `ListView` binda Enter a `select_cursor` (ombra i binding della screen)
  ed emette `Selected` anche al click → sottoclasse `PlanListView` che ribinda solo
  Enter a un dispatch (`getattr` su screen per mypy), click invariato; push diretto
  con `self.app.push_screen` (la Screen non ha `push_screen`); screen→screen con
  import lazy nei metodi (niente dipendenze tra aree all'import); rilettura per id
  dopo ogni push annidato (oggetti stale); highlight con fallback alla prima riga
  della stessa sezione quando il task ne esce.
- **Pomodoro nel piano (2026-09-15, fatto)**: la riga workflow sez.3 `(o)`/`(O)`
  era falsa (binding solo in home) → `DailyPlanScreen` ha ora `o` avvia/riapre
  e `O` pausa globale via callback `on_pomodoro_start(tid)`/`on_pomodoro_pause`
  (stesso seam di `on_add`); `action_start_pomodoro` generalizzata in
  `_start_pomodoro_for(task_id)` a code path unico; legend `plan_legend` it/en
  estesa (il testo workflow resta com'e', ora vero); 4 test in
  `tests/test_plan_operate.py`. Lezione: header disabilitati non evidenziabili
  neanche col click → il caso noop reale e' il piano vuoto (`plan_empty`,
  niente `#plan-section`); conteggi 🍅 con stale minore fino al recompose.
- **Radar scadenze in home (2026-09-16, fatto)**: mini-kanban testuale
  sostituito da strip-scatter priorita' x orizzonte (`PlotextPlot` di
  `textual-plotext`, nuova dipendenza con fallback testuale automatico);
  `kanban_plot_data`/`radar_hit` pure in `domain.py`, `b` a ciclo
  grafico→testo→nascosto (`kanban_mode`, fallback da `kanban_visible`),
  click sul punto = dettaglio diretto (1 task) o `RadarPickScreen` (N),
  caption con peggiori `#id`. Lezioni: serie con tuple RGB (il tema auto
  rimappa i nomi — "yellow" usciva viola); mapping cella→dato calibrato
  sullo spike con golden test che urla se plotext cambia geometria
  (zero sempre a w//2); tuple test con forma esatta `(tid,h,y,serie)`.
- **Radar refresh perso (2026-09-16, fatto)**: il fallback grafico→testo a
  radar vuoto scriveva `kanban_mode=testo` in config e non tornava mai
  indietro (neanche ai nuovi task, neanche al restart) → ora il fallback e'
  transitorio (`_kb_auto_text` in memoria, mai in config, auto-restore ai
  punti) e solo le scelte esplicite (`b`, settings) scrivono la preferenza;
  caption con `radar_nodate` (solo se >0); `except` di `_update_kanban`
  loggato invece di `pass`. Lezione: un fallback che scrive la config deve
  avere il percorso di ritorno, altrimenti diventa preferenza fantasma.
- **Calendario nel form (2026-09-16, fatto)**: il campo scadenza libero del
  form ha un bottone `#due-cal-btn` che apre `CalendarPickScreen` (grid
  mensile, frecce ‹/›/Oggi, giorno cliccabile, Esc annulla); al pick il form
  imposta la data preservando l'orario gia' digitato (`_due_time_part`);
  `#calpick-box/title/close` nei gruppi CSS condivisi; chiavi `form_due_cal`,
  `cal_today`; `tests/test_form_date_picker.py` (9 test). Lezioni: le celle
  del giorno devono essere `width:1fr` senza margini, altrimenti la riga
  (7 celle ~49 col) sborda la griglia e i giorni a destra/clip non sono
  cliccabili; le celle dei giorni devono avere `height:3` — un `Button`
  Textual a `height:2` collassa il contenuto a 0 (numeri invisibili, griglia
  trasparente); box ad altezza fissa che copra le 6 settimane (`30` = grid
  15 a `1fr`, zero scroll a 120x40) e a terminali piccoli `max-height:90%`
  la cappa e la grid scrolla; il bottone di apertura e' un'icona compatta
  📅 `width:4` con `tooltip` (label lunga clippata in `width:8`); a terminali
  piccoli il bottone data resta sotto il fold del form (il layout test apre
  il picker direttamente via `push_screen`, non col click).
- **Picker: oggi troncato (2026-09-17, fatto, 0.8.4)**: la cella di oggi
  mostrava "1" invece di "17" — `border: thick` su `.calpick-today` e
  `.calpick-sel` (dentro il border-box) consuma le colonne della stretta
  cella `1fr` (~5-6 col) e il contenuto a 2 cifre clippa; a terminale stretto la selezionata collassava
  a 0 col e crashava il renderer (`ValueError` in `divide_line`). Fix:
  `outline: thick` (stessa cornice visiva, zero spazio di layout) +
  regression test con `render_lines` alla region reale (`b.render()` usa
  la larghezza intrinseca e non vede il taglio).
- **Primo paint tabella col radar (2026-09-16, fatto)**: aprendo l'app con
  `kanban_mode=grafico` la tabella restava a colonne compatte e note
  nascoste finche' un evento (mouse dentro, cambio tab) non ridipingevasi;
  col mini-kanban (testo) mai — riportato su WSL/Windows Terminal,
  irriproducibile in `run_test` e pty (console inchiodata/pump diverso).
  Causa: Textual calcola larghezze/dimensioni del `DataTable` in `_on_idle`,
  DOPO il primo paint, e `_populate_table` gira in `on_mount` con il pump
  occupato dal `build()` del radar → il primo frame esce con dimensioni
  provvisorie. Fix: `_sync_table_dimensions()` a fine populate chiama
  `_update_dimensions(rows)` in modo SINCRONO, azzera
  `_require_update_dimensions` e svuota `_new_rows` (evita il doppio
  passaggio in idle). Lezione: il paint segue il pump, non le mutazioni —
  qualsiasi widget il cui layout dipende da un calcolo lazy-on-idle va
  finalizzato esplicitamente se qualcosa allunga l'avvio (es. un widget
  pesante come il radar); in `run_test` il bug sparisce perche' la console
  e' inchiodata a 80x25, non e' un controesame affidabile per il timing.
- **Click su area grigia (2026-09-16, fatto)**: cliccare nello spazio vuoto
  sotto le righe lasciava una riga evidenziata come in hover senza
  selezionarla: `ClickableDataTable._on_click` chiamava
  `_set_hover_cursor(True)` incondizionatamente e il delegate a
  `super()._on_click` la riattivava (anche il base la chiama sempre).
  Fix: hover attivato SOLO nel ramo riga valida; su area vuota
  `_set_hover_cursor(False)` + `return` (niente delegate, super non fa
  nulla di utile con meta vuoto). Bug pre-esistente al radar, emerso nel
  debugging. Test: `tests/test_home_table_hover.py` con evento `_Event`
  minimale (`style.meta` + `stop()`) — in `run_test` `pilot.hover` produce
  meta vuoto e non accende l'hover, quindi va invocato `_on_click` diretto.
  Nota collegata: il toast di backup all'avvio si sovrappone all'area radar
  (bug separato, non affrontato).
- **Smart list + piano che impara, strato dati (2026-09-17, fatto, S0/S1)**:
  `TodoItem.actual_pomo/actual_minutes` additivi (clamp ≥0, retrocompat),
  `config["smart_lists"]` con `_validate_smart_lists` (max 10, dedup
  case-insensitive, wildcard, mai solleva) in load E save (la whitelist di
  `save_config` troncava le chiavi nuove: test round-trip su tutte le
  `DEFAULT_CONFIG`); `domain.matches_smart/record_actual/calibration_factor`
  (min 5 campioni, mediana, clamp 0.5–3.0, None sotto soglia)
  + `calibrated_estimate` (mai <1, mai riscrive la stima);
  `plan._estimate(todo, factor=None)` retrocompatibile (riusa le costanti di
  domain, niente letterali duplicati); guardrail anti god-class
  (`test_arch_purezza_no_import_app_ui`); comportamento filtri congelato
  (stato persiste, resto volatile). Lezione review: `SMART_STATES` parla il
  vocabolario filtri (`completati` plurale) ma `todo.state` è singolare —
  `matches_smart` normalizza come `app._matches_state`, altrimenti match
  silenzioso a zero. UI (S2 smart list, S3 actual) rimandata; niente bump
  versione (strato invisibile).
- **Smart list UI (2026-09-17, fatto, S2, 0.9.0)**: `SmartListScreen` in
  `screens/views.py` (righe applica/elimina con Bottoni a id unici, snapshot
  filtro attuale, Input nome inline, pattern cornice fissa + regression test
  a 3 taglie in `tests/test_smart.py`); voce menu `Viste e analisi` +
  palette automatica via provider (nessun nuovo tasto globale);
  `app.active_smart` solo etichetta (i 4 filtri restano la verità,
  `_apply_smart` li imposta dalla spec), sgancio silenzioso su qualunque
  tocco manuale `f/t/g//`/settings/clear (la barra `Smart:n` è il segnale);
  validazione nome pura in `domain.validate_smart_name` (vuoto/dup/limite,
  testabile senza DOM — `_save_smart` chiamava `_populate_table` fuori
  pilot e rompeva i test puri). Lezioni: niente `row.mount()` prima che la
  riga sia montata (`Horizontal(B1, B2)` via costruttore); le action async
  vanno attese (`await self.action_save()` in `on_button_pressed`,
  warning `never awaited` altrimenti).
- **Tempo effettivo + piano che impara (2026-09-17, fatto, S3, 0.10.0)**:
  `ActualScreen` dumb in `screens/form.py` (`ModalScreen[int|None]`, default =
  contati, scarto live, `Esc` = None) chiamata da `app._apply_state` (home) e
  `DailyPlanScreen._on_state_picked` (piano, via `push_screen`+callback, mai
  chiesto senza stima o con actual già presente); persistenza resta del
  chiamante (`record_actual` + commit/refresh); `plan_day(..., factor)` con
  motivo `plan_calibrated` solo sui task stimati + capacità calibrata;
  `PlanProposalScreen` passa `calibration_factor` globale (niente per-progetto:
  media di mele e pere); `DetailScreen` riga actual, `StatsScreen` riga fattore
  con `calibration_samples`; `tests/test_actual.py` (9 pilot) + unit factor in
  `test_plan.py`. Lezione: validazione pure testabile senza DOM vale anche qui
   (`_save_smart` precedent); gli hook duplicati home/piano condividono la
   stessa popup dumb invece di un nuovo seam.
- **Planner boundary Fase 1 (2026-09-18, fatto)**: `src/planner/` package
  (`__init__` re-export + `service.Planner`, delega pura a `plan_day()`,
  nessuna normalizzazione, nessuna eccezione trasformata);
  `PlanProposalScreen` usa `Planner(...).propose()` (unico call-site);
  `factor` resta calcolato nella screen (equivalenza byte-identica);
  contratto in `tests/test_planner.py` (6 test) + guardrail purezza esteso
  a `src/planner/*.py`. Niente bump versione (cambio invisibile).
- **Planner Fase 2 (2026-09-18, fatto)**: `Planner` da boundary a orchestratore
  (`scoring.py` merito+mandatory, `constraints.py` eleggibilita'/skip,
  `capacity.py` monte-ore+selezione, `explain.py` chiavi reason congelate +
  builder); `plan.py` wrapper compatibile (stessa firma, re-export costanti e
  `_estimate` per i test); `factor=None` (omesso o esplicito) = auto via
  `domain.calibration_factor`, esplicito rispettato — niente sentinella
  (il legacy non distingueva omesso/esplicito, verificato su call-site+test);
  screen non calcola piu' il factor e usa le costanti explain; pesi/euristiche
  intoccati (differenziale legacy-vs-nuovo su 40+ scenari: zero divergenze);
  test `test_planner_{scoring,constraints,capacity,explain}.py` (21 test) +
  lock chiavi contro `STRINGS` it/en; `domain`/`app` intoccati. Niente bump
  versione (cambio invisibile).
- **Planner Fase 3 (2026-09-18, fatto)**: `Planner.propose()` restituisce
  `DayPlan` esplicito (`src/planner/models.py`: `PlanItem`/`DayPlan` frozen,
  tuple immutabili, unita' in pomodori); sezioni `planned`/`cut`/`skipped`
  (hard-excluded fuori dal modello, come prima invisibili) +
  `capacity_pomo`/`planned_pomo` (il mandatory puo' sforare: nessun
  invariante)/`factor` usato; `PlanItem` con `todo_id/score/reasons` +
  `estimate_pomo` (stima effettiva usata in capacity) + `mandatory` esplicito
  (mai ricostruito dalle reasons); `to_legacy()` sul modello (unica via
  `DayPlan → legacy`, niente `propose_legacy`); `plan.py` =
  `propose().to_legacy()`; internamente `partition`/`allocate` propagano il
  flag mandatory (test unitari adeguati, asserzioni invariate); screen
  consuma `DayPlan` (`self.plan` + `self.rows` filtrati additivi, niente
  logica duplicata); contratto `test_planner.py` via `to_legacy()` +
  nuovo `test_planner_dayplan.py` (18 test: costruzione, sezioni, capacity,
  determinismo `==`, matrice equivalenza legacy); niente scheduling
  temporale, niente persistenza/serializzazione, pesi intoccati.
  Niente bump versione (cambio invisibile).
- **Planner Fase 4 (2026-09-18, fatto)**: scheduling temporale deterministico
  (`src/planner/scheduler.py` puro: `schedule(plan, availability, busy)` greedy
  first-fit nell'ordine Planner, niente secondo scoring, durate da
  `estimate_pomo` x 30min senza arrotondamenti); modelli in `models.py`
  (`TimeWindow`, `ScheduledItem` che riusa `PlanItem`, `ScheduledDayPlan` con
  `plan` originale + `scheduled`/`unscheduled` + eco availability/busy
  normalizzati); solo `plan.planned` si schedula (cut/skipped fuori, gia'
  decisi); mandatory senza slot = unscheduled strutturale senza reason nuova
  (niente chiavi i18n, UI invariata); busy hard constraint (sort+merge+clip al
  giorno); availability parametro esplicito senza default (day_hours resta
  monte-ore, mai working-hours); `Planner.schedule()` thin wrapper statico,
  `propose()`/`plan_day()` intoccati; `tests/test_scheduler.py` (16 test:
  casi §24, invarianti §25, determinismo, conservazione); `domain`/`app`/
  pomodoro intoccati, niente calendario esterno, niente AI.
  Niente bump versione (estensione non usata ancora da nessun consumer).
- **Planner Fase 5 (2026-09-18, fatto)**: feedback di esecuzione come pura
  derivazione (`src/planner/feedback.py`: `feedback(scheduled, todos)` →
  un `ExecutionFeedback` per voce planned, stesso ordine, niente scritture);
  modello in `models.py` (frozen: `estimate_pomo` unita' astratta +
  `estimate_minutes` via `POMO_HOURS`, `scheduled_start/end` o None,
  `sessions` = pomodoros, `actual_pomo/minutes` = dichiarazione utente,
  `completed` da stato); semantica 25/30 chiusa a unita' astratte
  (`POMO_HOURS` unica fonte stima→minuti, timer resta 25 di default,
  calibration gia' count-based e invariata); riuso meccanismi esistenti
  (`credit_pomodoro` accredita solo focus completati, stop = 0, `X`
  anticipato = 1 sessione); niente wiring app/UI, niente actual auto,
  niente rescheduling, niente calibration automatica (Fase 6);
  `tests/test_feedback.py` (9 test); `domain`/`app`/pomodoro/scoring/
  scheduler intoccati. Niente bump versione (solo derivazione).
- **Planner Fase 6 (2026-09-18, fatto)**: boundary di calibrazione come adapter
  sottile (`src/planner/calibration.py`: `observe`/`observe_all` derivano
  coppie (estimate, actual) dagli `ExecutionFeedback` completati con entrambi
  > 0 — sessions escluse, fonte resta `actual_pomo` manuale;
  `factor_for` delega a `domain.calibration_factor`; mediana/min-samples/
  clamp restano solo in `domain`, nessun secondo algoritmo, nessun ciclo
  import); `capacity.estimate` delega a `domain.calibrated_estimate`
  (equivalenza verificata su 81 combinazioni, chiude follow-up B);
  `service` usa `calibration.factor_for` (stessi risultati);
  test `test_calibration.py` (6 test: delega, observe, equivalenza
  feedback↔todos a parita' di dati, edge <5/outlier/determinismo);
  solo future (piani/actual/slot passati mai toccati), niente history in
  Planner, niente auto-update, niente rescheduling. Niente bump versione.
- **Slot in Buongiorno (2026-09-18, fatto, Fase 6.5)**: `PlanProposalScreen`
  mostra gli slot dello scheduler da ora di partenza esplicita (`#planp-start`
  HH:MM, vuoto = niente slot, invalido = hint senza crash, mai persistita);
  finestra `[inizio, inizio + day_hours]` (durata di capacita', non working
  hours, niente default 09-18); `Planner.schedule()` sul `DayPlan`, rendering
  puro di `scheduled` (`HH:MM–HH:MM titolo`) + sezione `Senza orario` dagli
  `unscheduled` strutturali (niente `plan_unscheduled`, cut fuori); conferma
  `planned_for` invariata, niente auto-start/rescheduling/pomodoro/calendario;
  chiavi `planp_start(_ph/_bad)` + `planp_slots_none/un` it/en;
  `tests/test_plan_slots.py` (6 pilot: vuoto, slot+ordine, invalido,
  unscheduled, midnight-clippato, conferma); `src/planner/` intoccato.
  Niente bump versione (solo display).
- **Fallback stima assente (2026-09-18, convenzione esplicitata, non cambio)**:
  task senza `stima_pomo` (= 0 nel modello) vale 1 pomodoro → 30 min negli
  slot (`domain.calibrated_estimate`: `base = int(...) or 1`; docstring in
  `plan.py`/`domain.py` + placeholder form `form_stima_ph` lo dichiarano come
  fallback di pianificazione, mai come stima utente). Pre-esiste alla 6.5
  (la 6.5 lo ha solo reso visibile); unico punto che distingue assente da
  presente: `scoring.has_est` (solo motivo `plan_calibrated`, mai durata).
  **Follow-up separato (mini-fase futura, non implementare ora)**: "stima
  mancante ≠ stima 1" — es. `estimate_pomo = None` nel modello, rendering
  onesto ("durata da definire"), gestione apposita in scheduler/testi.
- **Eventi fissi in Buongiorno (2026-09-18, fatto, Fase 7)**: `FixedEvent`
  frozen in `models.py` (title/start/end, mai un Task, fuori da scoring/
  capacity/calibration); `scheduler.events_to_busy()` proiezione pura
  (niente merge, core `schedule()` intoccato, busy resta hard constraint);
  `PlanProposalScreen` con `#planp-events` (TextArea temporanea, mai
  persistita, una riga `HH:MM-HH:MM Titolo`, parsing puro
  `parse_event_lines`, invalide ignorate con hint); timeline unita
  FixedEvent+ScheduledItem ordinata per start con tag `EVENTO:` (rendering
  da eventi originali, mai da `busy` normalizzato; fuori-availability non
  mostrati; niente free-time); sezione `Senza orario` invariata, conferma
  invariata; chiavi `planp_events(_bad)` + `planp_event_tag` it/en;
  `tests/test_phase7_events.py` (11 puri: parsing/proiezione/casi §4/
  midnight/mandatory/DayPlan invariato) + 3 pilot in `test_plan_slots.py`;
  niente calendario esterno, niente ricorrenze, niente rescheduling.
  Niente bump versione.
- **Sorgenti esterne (2026-09-18, fatto, Fase 8)**: `TodoItem.source/external_id`
  persistiti (`to_dict`/`from_dict`, file vecchi → `""`); `TodoStore.by_external`
  (match solo se entrambi non vuoti, source case-insensitive); import CSV
  idempotente (`_import_csv_file`: colonne `source`/`external_id` o fallback
  alla colonna `id` con source `csv`; match → skip senza duplicato/merge con
  id interno invariato e `old_id` rimappato per i figli; senza external_id →
  sempre nuovo, esplicito); Planner/Scheduler ignari (solo modello interno);
  niente sync bidirezionale, niente OAuth/rete, niente UI nuova;
  `tests/test_external_import.py` (5 test: modello, lookup, idempotenza,
  no-id, planner/scheduler). Niente bump versione.
- **Fase 9 (2026-09-18, verifica + guardrail, zero produzione)**: la
  migrazione UI era gia' realizzata in 6.5/7 (`PlanProposalScreen` unico
  percorso `Planner→DayPlan→Scheduler→ScheduledDayPlan`); audit: zero
  chiamate produttive a `plan_day()` (solo wrapper compat + test),
  DailyPlan/Agenda/Calendar/Day/Week sono viste di lettura su
  `planned_for`/`due` (non planning), `ReviewScreen._candidates` e'
  presentazione intenzionale (NON migrare). Aggiunto solo
  `tests/test_arch.py` (3 guardrail UI: niente costanti merito/capacita'
  in screens+app, niente definizioni locali di propose/schedule/Planner,
  niente `plan_day(`/`src.plan` legacy in produzione — con regex che non
  inghiottano `action_plan_day`/`src.planner`); nessuna screen vietata in
  quanto tale: future consumer legit via boundary. Niente bump versione.
- **Fase 10 (2026-09-18, chiusa come audit puro, zero produzione)**: audit
  di estrazione del Planner eseguito (dependency graph completo, verifica
  import `src.planner` senza bootstrap — niente Textual/Rich/storage/app/
  screens; unico modulo applicativo transitivo `src.lang` via `models`,
  senza side-effect; API pubblica esplicita senza dettagli interni).
  Risultato: **non estrarre** — il boundary e' gia' isolato e protetto
  (guardrail purity + arch), le dipendenze da `domain` sono deliberate
  (calibration source of truth), nessun consumer esterno giustifica
  packaging/versioning/CI. Estrazione richiesta potrebbe essere riesaminata
  solo con un consumer esterno reale. Nessuna modifica di produzione, nessun
  refactor propedeutico (micro-rafforzamento guardrail scartato: valore
  marginale basso). Niente bump versione.
- **Bugfix UX Buongiorno (2026-09-18, fatto, post-release 0.11.0)**: disponibilita'
  con start/end espliciti (`TimeWindow(start, end)`, niente piu' `end = start +
  day_hours`; overnight `end <= start` rifiutato con hint; `day_hours` resta
  capacita', etichette disambiguate: `planp_summary`/`brief_m_load`/`set_hours`
  dicono "capacita'"); riga unica affiancata `[09:00] – [18:00]` (input 14 col
  per superare border+padding dell'Input: contenuto utile 8, le cifre stanno
  in cornice); colonna stima form 20→28 (placeholder allungato in 0.11.0
  troncato); focus apertura sulla lista + `scroll_home` differito via
  `call_after_refresh` (il pannello si apre in cima: prima lo scroll partiva
  dal fondo e si vedevano solo le scelte). Lezioni: (a) focus iniziale su
  Input NON si puo' fare — consuma `s` e rompe "s = salva ovunque"
  (`test_conferma_con_s` l'ha beccato); (b) `scroll_visible` del layout
  provvisorio sopravvive al relayout -> scroll_home differito; (c) "eventi
  fissi ignorati" segnalato dall'utente era il PROCESSO TUI STANTIO (python
  non ricarica a runtime: riavviare dopo le modifiche, non e' un bug);
  (d) `.venv` aveva il fossile `carpediem 0.5.1` installato (l'entry point
  `carpediem` del venv girava la copia vecchia!) -> reinstallato editable
  con `pip install -e .`; test: `test_plan_slots.py` riscritto (12 pilot:
  start/end espliciti, end mancante/uguale/minore, pausa pranzo senza overlap,
  apertura in cima a 3 taglie) + `test_form_stima_colonna_larghezza`
  (>=28 a 120x40 e 70x20). Commits `06d546e`, `bb58e98`.
- **Piano giorno scheda operativa (2026-09-21, fatto, 0.12.0)**: la finestra
  orari + eventi fissi di Buongiorno ora vengono PERSISTITI alla conferma in
  `config["day_window"]` (strutturata: `{date, start, end, events:
  [{start, end, title}]}` — eventi gia' campi separati, mai stringhe da
  riparsare; conversione esplicita config->FixedEvent via
  `day_window_parts`). Il piano giorno `p` la rilegge e ri-schedula
  ESATTAMENTE i confermati (`planned_for == oggi`, ordine di merito da
  `propose()` filtrato sull'insieme confermato, `Planner.schedule()` per gli
  slot): timeline come prima sezione lista (righe disabled, consultabile non
  operativa), eventi con tag `EVENTO:`, coda "Senza orario". Nessuna seconda
  selezione: Buongiorno decide cosa entra nel piano, il piano giorno lo
  organizza temporalmente. Degradazione pattuita: senza finestra (o stale di
  un giorno prima) -> solo task, zero timeline, mai default 09:00-18:00;
  conferma con finestra invalida/vuota -> cancella lo stale; Esc non scrive
  mai. Whitelist config: `_validate_day_window` in load E save (mai solleva,
  cap 30 eventi, titolo 120 char) + round-trip su tutte le chiavi.
  Rendering timeline condiviso in `_timeline_lines` (Buongiorno e piano
  giorno, stesso modulo). Chiavi nuove: `plan_sec_window` it/en; riuso
  `planp_event_tag`/`planp_slots_un`. `tests/test_day_window.py` (15:
  validazione, roundtrip, conferma/Esc/stale, timeline confermati, eventi,
  degradazione, layout 3 taglie). Revisione deliberata della decisione
  Fase 6.5 "mai persistita" su richiesta utente (Buongiorno = proposta,
  Piano Giorno = scheda operativa della giornata).
  Nota (superata in 0.12.2): i 6 fallimenti in `tests/test_ui_regression.py`
  visti qui erano del WIP non ancora fissato — vedi voce apposita sotto.
  Commit `51e79de`.
- **Righe timed operative nel piano giorno (2026-09-21, fatto, 0.12.0
  secondo commit)**: la prima versione della timeline era una sezione
  read-only separata sopra i pianificati (duplicazione: timing non
  lavorabile, task lavorabili senza timing, segnalati dall'utente). Ora la
  sezione `Pianificati per oggi` DIVENTA la timeline quando c'e' finestra:
  task schedulati = `PlanRow` operative con prefisso orario in riga
  (`HH:MM–HH:MM titolo`, Enter/Space/o/O/x funzionano), eventi fissi inline
  disabled informativi in posizione cronologica, task senza slot operativi
  in coda senza prefisso (niente riga-riassunto "Senza orario", niente
  suffisso). Ordine: slot first-fit = cronologico = merito, nessuna seconda
  selezione/ordinamento; `_planned_children` presenta i risultati
  Planner+Scheduler, `compose` usa `custom` per la sezione planned quando
  c'e' finestra (loop generico invariato per le altre sezioni). Header
  planned esteso con `{win}` ("— Timeline HH:MM–HH:MM", chiave
  `plan_sec_window`); `plan_sec_slots` rimossa (mai pubblicata).
  `_timeline_lines` resta di Buongiorno (stringhe); il piano giorno
  costruisce righe, non linee. Verifica manuale: pattern esatto
  A/B/EVENTO/C/D con interazioni full (Enter/Space/x su righe timed).
  mypy: payload union `TodoItem | FixedEvent` va ristretto con
  `isinstance` (le tuple eterogenee non bastano), variabile `row` riusata
  in loop diversi -> rinominare.
- **Planning ↔ Pomodoro ↔ Execution (2026-09-21, fatto, commit 386bfe2)**:
  primo collegamento reale dei tre mondi, zero rescheduling.
  (12.1) `_refresh_open_plans()` in app: ricompone i DailyPlanScreen nello
  `screen_stack` dopo gli eventi Pomodoro (start/complete_focus/
  finish_break/stop), preservando l'highlight via `_keep_id` letto da
  `_current()` PRIMA del recompose; `_restore_pomodoro` non toccato (gira
  solo a startup/unlock, nessun piano puo' essere aperto). Un solo refresh
  per evento (`_start_phase` aggiorna solo la home). (12.3) seam
  `current_pomo` (getter `task_id | None`) + `_marker()`: `▶` sulla riga
  del task corrente, solo presentazione, max una riga, sparito a stop/fine
  break. (12.6) `scheduled_for_today()` = UNICA costruzione
  Piano-Giorno/Briefing (confermati -> merito propose -> slot schedule;
  degenere senza finestra: ScheduledDayPlan con slot None, mai orari
  inventati); `include_done=True` (briefing) include i confermati non
  attivi nel ritorno ma FUORI dal dayplan (lo Scheduler non colloca i non
  attivi) — individuati via `completed_at == oggi` perche' `apply_state`
  azzerava `planned_for` al completamento (comportamento pre-esistente,
  domain.py:122). `_exec_lines` nel Briefing sera = PRIMO consumer in
  produzione di `planner.feedback()`; attivi in ordine di merito con slot,
  non-attivi derivati dal todo (slot None, stima raw senza fallback or-1,
  che resta solo di pianificazione); la stampa plain include la sezione.
  D1–D4 approvate: stop=0 sessioni, actual_pomo solo manuale (ActualScreen),
  Pomodoro richiede un task, feedback nel briefing. i18n:
  `brief_e_sec_exec`/`brief_exec_row` it/en. `tests/test_execution.py`
  (13). Lezioni: nei test import di MODULO (`plan_mod.PlanRow`) — i
  `from ... import` di classi restano stale dopo il reload di conftest e
  rompono ogni `isinstance`; l'ActualScreen si salva via bottone
  (`#actual-save`), l'Input consuma la `s`; 2 🍅 = 1h (POMO_HOURS, non
  1.5h); `calendario-picker` nel WIP e' flaky sotto carico (passa
  standalone).
- **INCIDENTE dati (2026-09-21, ~13:49, risolto)**: ripetuto l'errore del
  2026-09-14 — heredoc di DEBUG con `TodoApp()` + `run_test` lanciati
  SENZA `TASKO_HOME` durante il debug dei test Fase 12. Il processo
  senza chiave ha incontrato il file cifrato reale ->
  `save_todos_synced` con `_is_crypto_unreadable=True` ha riscritto la
  memoria (task finti del debug) al posto dei dati, in plaintext; i
  `.bak.json` successivi hanno distrutto la catena di backup a un livello
  (il vero dato e' sopravvissuto SOLO nello zip auto-backup del mattino).
  Ripristinato da `Tasko_backups/tasko_20260921_102022_*.zip` (solo
  todos.json, config/pomodoro intatti); perdute le modifiche 10:20->13:49
  (planned_for di Buongiorno, ri-fatte in 10 secondi). REGOLE PIU' DURE:
  (1) QUALUNQUE processo che importi `src.app` o monti l'app — anche un
  heredoc di 10 righe, anche read-only NELLE INTENZIONI — parte SEMPRE
  con `export TASKO_HOME=$(mktemp -d)` nel MEDesimo comando (l'export di
  un comando precedente non basta: ogni invocation bash e' un'altra
  shell? no, la shell e' persistente, ma l'export va verificato con
  `echo` prima di ogni run sensibile); (2) il copia-incolla di script di
  verifica va controllato per il prefisso TASKO_HOME PRIMA di eseguire;
  (3) dopo qualsiasi debug non isolato sospetto, controllare mtime e
  dimensione di `~/.todo_app.json` PRIMA di continuare; (4) un wipe da
  debug plaintext e' riconoscibile dal file che diventa   non-envelope
  (leggibile) o da envelope minuscolo.
- **Buongiorno sopra il fold (2026-09-22, fatto)**: con finestra+eventi
  compilati la proposta usciva dal viewport a 120x40 (contenuto ~27 righe
  vs 21 visibili: la lista stava a y=32, fold a 30) — chi apriva `P` non
  vedeva cosa doveva confermare (emerso rigenerando gli screenshot README:
  la lista esisteva nel DOM ma non nel render). Fix: `SelectionList`
  composta subito dopo il summary, PRIMA di disponibilita'/eventi/slot
  (causa -> effetto resta scorrendo verso il basso); focus-on-list e
  `scroll_home` differito invariati. Regression test
  `test_proposta_sopra_il_fold` (ordine DOM + `sl.region.y < fold` a
  120x40). Lezione: un widget presente nel DOM non e' necessariamente
  visibile — gli shot vanno verificati via regex `<text>`, non per
  esistenza widget.
- **Stats undated mai negativo (2026-09-22, fatto)**: `stats_undated` con
  `if pomo_undated:` mostrava `di cui senza data: -6` con dati incoerenti
  (log senza contatore: totale < datati) — ora `> 0`; test
  `test_stats_undated_mai_negativo`. L'app coerente non lo produce mai
  (`credit_pomodoro` tiene log+contatore in sync), ma la guardia e'
  dovuta.
- **Esc pulisce la ricerca (2026-09-22, fatto)**: a ricerca attiva sulla home
  `Esc` azzera il SOLO `filter_search` (stato/tag/progetto intatti, sgancio
  smart come ogni tocco manuale, no-op silenzioso a ricerca vuota); sotto
  modale resta inerte via `check_action` (fuori `_MODAL_SAFE_ACTIONS`), quindi
  `SearchScreen` resta annulla-chiudi. Test `test_esc_pulisce_ricerca_attiva`.
  Lezione test: dopo il dismiss lo screen base si chiama `Screen`, non
  `TodoApp` — asserire `!= "SearchScreen"`.
- **UI regression WIP fissato (2026-09-23, fatto, 0.12.2)**: i 6 scenari
  falliti di `tests/test_ui_regression.py` (45 scenari x 4 taglie) erano
  quasi tutti veri bug, non aspettative sbagliate: Review/Settings aprivano
  pre-scrollate (focus trascina lo scroll, fix con `scroll_home` differito
  come Buongiorno); Pomodoro/Goals a 70x20/80x24 nascondevano i bottoni
  fuori viewport senza scroll possibile (passate al pattern cornice fissa
  + scroll + bottoni fissi); menu con Esc a stadi (il runner preme fino a
  3 volte). Due fix di test legittimi: lo scenario archivio scriveva nello
  store invece che nel file archive (passava per trasparenza della tabella
  home nel render!) e il content-check ignora le label dei Button (ora
  incluse: presenza del dato, troncamenti restano sul render).
- **Outlook in Buongiorno (2026-09-23, fatto, 0.13.0)**: bottone `Carica da
  Outlook [o]` (tasto `o` + click): configurato -> fetch e compila e basta
  (append senza duplicati, manuale preservato); non configurato -> apre
  `OutlookSetupScreen` annullabile (Esc = niente). Adapter in
  `src/integrations/` (`outlook.py` parse puro calendarView -> FixedEvent +
  allday + scartati, `outlook_auth.py` unico punto di rete: MSAL device flow
  + urllib, dipendenze iniettabili); screen via `OutlookHooks` (dict, mai
  eccezioni oltre il seam), rete mai nelle screen (guardrail test); token in
  `.todo_outlook_token.json` 0600 + envelope se lock (mai nei backup);
  gate fail-closed senza cifratura; scope `Calendars.Read` congelato,
  tenant pinnato (niente common), account binding, verification_uri
  validata; allday persistiti in `day_window` (validati come events) e riga
  informativa in Buongiorno + piano giorno; tag timeline `IMPEGNO:`.
  Test: `test_outlook_parse.py` (fixture anonime) + `test_outlook_auth.py`
  (doppi, permessi, mapping HTTP) + `test_plan_outlook.py` (pilot con hook
  finti) + scenario `outlook-setup` nel registry. Lezione: conftest
  `tmp_files` deve redirigere OGNI nuovo path (qui `OUTLOOK_TOKEN_FILE`),
  altrimenti i test scrivono in `~` reale; `_dump_state_text` serializza
  da solo (niente `json.dumps` prima, doppia codifica); hook opzionali via
  `getattr` + `callable`; mypy: `self._outlook_pending` va annotato
  (`: object`) altrimenti la prima assegnazione fissa il tipo e `= None`
  fallisce. Lezione CI (0.13.1): le dipendenze vivono in DUE file
  (`pyproject.toml` + `requirements.txt`, la CI installa dal secondo) —
  aggiornarli entrambi; `ZoneInfo` su Windows richiede il pacchetto
  `tzdata` (niente zoneinfo di sistema: parser vuoto senza), e i check
  sui mode-bit (0600) sono POSIX-only (ACL Windows non mappano).
- **Outlook via browser (2026-09-23, fatto, 0.14.0)**: login con auth-code
  + PKCE e callback loopback (RFC 8252, al posto del device code):
  `LoopbackListener` stdlib su `127.0.0.1` esplicito + porta effimera
  (mai `0.0.0.0`, mai hostname `localhost` che puo' risolvere a ::1 —
  guardrail test), `webbrowser.open` best-effort con URL copiabile a mano,
  hook `cancel` dedicato (Esc in setup chiude il socket, niente orfani),
  attesa con timeout 180s. Lezione: `self._server` va tipizzato `Any`
  (mypy non vede gli attributi dinamici `auth_result`/`got_result`).
  L'account di setup passa come `login_hint` (browser con email
  precompilata: password+2FA solo lì, mai ROPC — con MFA fallirebbe
  comunque con AADSTS50076).
- **M1 Planning Foundation (2026-09-24, fatto)**: contratti del Planner
  congelati prima di ogni estensione — `test_planner_contract.py` (pipeline,
  firme, invarianti DayPlan/ScheduledDayPlan), `test_planner_fixtures.py`
  (10 scenari con output `to_legacy`/slot esplicito), `test_planner_perf.py`
  (baseline 50/100/500/1000 task: ~0.3/0.6/2.9/5.4ms, soglie CI larghe
  anti-flaky), guardrail `test_arch.py` esteso (UI mai stats/calibration).
  Zero produzione toccata.
- **M2 Task Reality (2026-09-24, fatto)**: un `TaskExecution` per task
  completato (mai per pomodoro), minuti wall-time canonici + snapshot
  `estimate_pomo`, actual 0 = senza actual; storage separato append-only
  `.todo_executions.json` (lock singolo, dedup atomica su
  (task_id, ended_at), cap 5000, cifrato come gli altri); statistiche
  robuste + confidence LOW<10/MED<30/HIGH + `calibration_summary`
  derivato on-demand (mai persistito); hook nei 3 ingressi di chiusura
  (home via `_record_completion_execution`, piano via `on_completed`
  opaco, CLI done con fallback stima); slot ricostruito via
  `scheduled_for_today(include_done=True)` perche' `apply_state` azzera
  `planned_for` prima dell'actual. Lezioni: `capacity` importa `domain`
  -> la conversione pomo/minuti vive in `domain.POMO_MINUTES` (niente
  import inverso, sarebbe ciclo); i test nuovi usano import di modulo
  (le classi from-importate restano stale per `isinstance` dopo il reload
  di conftest). Niente bump versione (invisibile).
- **M3 Explainable Planner (2026-09-24, fatto, 0.15.0)**:
  `src/planner/decisions.py` puro (`PlanningDecision` frozen +
  `decide()` lettura del DayPlan: planned→SCHEDULED, cut→NOT_SCHEDULED,
  skipped→DEFERRED; `refine_with_schedule()` restituisce NUOVE decisioni
  con slot, solo mandatory-senza-slot→CONSTRAINED; `primary_reason()`
  flag CUT/SKIPPED poi primo motivo, mai testo inventato); evidence solo
  dati (due/priority/overdue/score/rank/rank_of/estimate_pomo/minutes/
  mandatory/capacity/planned_pomo); confidence solo con `plan_calibrated`
  (livelli M2 su sample_count esterno, mai calcolato in decisions.py).
  Why nel `DetailScreen` (`_why_lines`, sezione dopo lo stato; non
  valutato→messaggio esplicito per stato); `DetailScreen(todo, all_todos,
  today, hours)` con capacita' reale dai 3 call-site (helper
  `app._detail_context`, piano `self.today/self.hours`) + test di
  coerenza Planner/Detail a parita' di input; summary Buongiorno splittato
  tagliati/rimandati (`planp_summary` it/en); chiavi `why_*` it/en;
  guardrail anti stadi-planner in `views.py`. Lezioni: `views.py` non
  importava domain/planner (ordine isort `from src import` prima di
  `from src.lang`); stub `_why_lines` aveva inghiottito il `def compose`
  (verificare sempre con read dopo edit di firme).
- **M4 Replanning (2026-09-24, fatto, 0.16.0)**: `src/planner/replan.py`
  puro (`replan()` riusa propose+schedule senza toccarli: completati fuori
  da soli, pianificati privilegiati in allocate, slot passati esclusi via
  availability clippata a [now, fine]; `ReplanProposal` con kept/moved/
  dropped/added + motivi da decide/primary_reason); commit separato
  `domain.apply_replan` (added→planned, dropped→plan_skip oggi,
  kept/moved intatti); CLI `carpediem replan [--now HH:MM] [--apply]`
  (preview read-only verificata via hash, --apply esplicito, --now
  invalido exit 2 senza scritture). Scoperta: DROPPED quasi irraggiungibile
  per capacita' (allocate non taglia mai i pianificati) — caso reale solo
  planned+skipped. Lezioni: `import x.y as z` dopo from-import omonimo lega
  la funzione (shadowing package) → `sys.modules[...]`; `events_to_busy`
  ritorna tuple (mypy); CLI importa `screens.plan` lazy (solo parsing
  day_window, debito documentato).
- **UX Planning Cockpit (2026-09-24, fatto, 0.17.0)**: issue #46/#47/#50/#51
  + audit #52/#53. Daily Cockpit: `DailyPlanScreen._row` con `!` (solo
  priorita' alta) + durata (slot `30m` se schedulato, altrimenti stima
  `~N🍅`) + scadenza anche su planned/due (unica `_row` condivisa da tutte
  le sezioni). Detail: riga `cockpit_ear_row` Tu/CarpeDiem/Reale da
  `stima×30` / `predicted_minutes(stima, calibration_factor)` / actual
  (`resolve_actual_minutes`, `—` se assente), mai riscritta la stima.
  `ReplanPreviewScreen` (tasto `G` + menu/palette): preview read-only del
  motore M4 (kept/moved/deferred/added + residua), commit solo con `s`
  (`apply_replan` + `_on_replan_applied`), Esc zero scritture (hash test).
  `WeekReviewScreen` (tasto `W`): insight execution-based da
  `load_executions` (lette in app, passate alla screen) + `domain.execution_summary`
  + `_completed_by_date`/`_pomodoros_by_date`; sola lettura, offline.
  Guardrail `test_arch.py` riallineato: le screen non fanno I/O execution
  ne' costruiscono record (`make/append/load_executions` vietati), ma
  possono consumare helper di LETTURA del dominio (precedente StatsScreen).
  Lezioni: `_row` modifica copre tutte le sezioni (un solo punto); il
  picker/`render_lines` serve per il no-wrap a 70 col; `s`/Esc coerenti
  nelle due nuove screen; i test #51 scrivono via `save_todos_synced` +
  `append_execution` (la screen legge dallo storage, non da una lista
  locale).

## 8. Decisioni aperte (non implementare senza discuterle)

- **Lancio/visibilita'** (discusso 2026-09-14, in attesa): testi annuncio it/en pronti
  in chat + screenshot per lingua; r/commandline bloccato (progetti <30 giorni
  rimossi + regola 8 alternative + disclosure AI) — candidati ora: r/tui,
  r/SideProject (formato storia), Discord Textual; r/commandline dopo il mese
  di vita del repo. Partire solo su via libera esplicito, senza fretta.

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

Il planning esiste già in `src/plan.py` (`plan_day(todos, today, hours,
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
(`src/planner/service.py` orchestra scoring → constraints → capacity, motivi
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

`src/app.py` è la god-class nota (~2570 righe, 166 funzioni). **Non è
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
completata: esiste `Planner` (`src/planner/service.py`), usato da
`PlanProposalScreen`. Phase 2 completata: `Planner` orchestra
`scoring`/`constraints`/`capacity`/`explain`, `plan.py` e' wrapper compatibile,
`factor=None` auto-calibra; contratto in `tests/test_planner*.py`. Phase 3
completata: `Planner.propose()` restituisce `DayPlan`
(`src/planner/models.py`, niente scheduling temporale), `plan_day()` e'
`propose().to_legacy()`; contratto in `tests/test_planner*.py` +
`test_planner_dayplan.py`. Phase 4 completata: `schedule()` deterministico
su `DayPlan` + `availability` esplicita (`src/planner/scheduler.py`,
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
