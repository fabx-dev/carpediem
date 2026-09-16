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
resoconto sera (solo palette, zero rete).

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
src/domain.py    regole di dominio pure (stato+ricorrenza, pomodori, form, piani):
                 mutano solo i TodoItem passati, timestamp espliciti, mai I/O/UI;
                 app/screen applicano e persistono via store.commit()
src/models.py    TodoItem, Priority, Recurrence, validazioni date, MAX_DEPTH=6;
                 campi extra: stima_pomo, planned_for, plan_skip (scarto piano smart, data)
src/store.py     TodoStore: lookup id, mutazioni, next_id, commit() = UNICO punto di scrittura todos
src/storage.py   paths, load/save (todos/template/config/archive/pomodoro), lock, merge, backup;
                 config include day_hours (default 6, clamp 1-16)
src/crypto.py    Fernet + PBKDF2 (600k iter), chiave solo in RAM, envelope {"v","salt","data"}
src/cli.py       add/list/done/show (add/done via TodoStore: lock+merge gratis); add senza flag = NL
src/commands.py  MENU_STRUCTURE (4 categorie: giornata/viste/dati/sistema, chiavi i18n +
                 action + shortcut) + CarpeDiemMenuProvider (palette `ctrl+p`, titoli
                 "Categoria › Voce"); MENU_IT piatta tenuta per compatibilita'
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
  eccezione approvata: `P` = piano smart, coppia di `p` = piano giorno).
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
  grazie alla fixture `tmp_files`).
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

## 8. Decisioni aperte (non implementare senza discuterle)

- **Sync**: accantonato (idee non chiare) — file-sync vs server vs SQLite+replica vs CRDT
  vs BaaS, vedi thread in chat. Non riaprire di iniziativa.
- **AI provider / Sprint AI-6** (sostituito da AI-1, vedi sotto; non implementare
  il vecchio disegno: la condizione sui 5 giorni di briefing non esiste piu').
- **Progetto AI-1** ("Chiedi a CarpeDiem", pianificato 2026-09-12, non iniziato):
  comandi NL (rimanda/concentra/cosa-ci-sta/scomponi) con diff da confermare +
  schermata "AI: connessioni" stile `/connect` + calibrazione stime personale.
  Provider in ordine Locale → ChatGPT-login (OAuth riuso Codex) → Copilot
  (OAuth ufficiale) → API key; implementare in ordine locale, apikey, copilot,
  codex. Regole dure: consenso-sempre (la preview e' il consenso), mai segreti
  in config/log/notify/backup, mai rete nei test (fake provider), mai scritture
  senza conferma (solo additivo via `store.commit()`), niente nuovi tasti
  globali, tutto it/en, trasporto stdlib (niente nuove dipendenze).
  Slices: 0 seam `AIProvider` → mini-slice `scomponi` end-to-end → 1a connessioni
  (device-flow-first, token in file 0600 per provider) → 1b altri comandi → 2
  calibrazione (locale default, sempre conferma), ognuna con stop-criterion.
  Regola OAuth: flusso non documentato che si rompe 2 volte per cause loro →
  la riga si toglie invece di inseguirla. Dettagli nei report UX + tecnico
  della sessione 2026-09-12 (connessioni stile SecurityScreen, diff stile
  Buongiorno/Review, schermata AI dedicata in Sistema, chiave via
  `TASKO_AI_KEY`/file 0600/campo mascherato, schermata Connessioni prima dei
  comandi). Non partire senza via libera esplicito.
- **Progetto Ponte-Calendario** (integrazione Calendario stile Todoist, pianificato
  2026-09-12, non iniziato): overlay eventi read-only solo in Agenda + push manuale
  dei soli task con ora su calendario separato `CarpeDiem` + reschedule-back limitato.
  Google Calendar prima (BYO client-ID, loopback stdlib), Outlook dopo; mai sync
  Tasks/To Do come task-list, mai auto-sync. Dettagli in
  `docs/piano-ponte-calendario.md`. Non partire senza via libera esplicito.
- **Web app sullo stesso backend** (proposta utente): opzioni A read-only → B server locale CRUD
  (TUI/CLI client, telefono via LAN) → C hosting pubblico. Serve risposta a: basta la LAN?
  autostart invisibile? stack Python+template o altro? Slice A come validazione con stop se inutile.
- Quick-win rimasti: da rivalutare dopo agenda/export iCal. ("Smart oggi" fatto dal planner; stime esistevano già.)
- Pomodoro cross-device dichiarato fuori scope v1 (timer resta locale).
- **Packaging distro** (discusso 2026-09-14, accantonato): PyPI/pipx resta l'unico
  canale; niente `.deb`/PPA, `.rpm`/COPR, `PKGBUILD`/AUR per ora — rivalutare solo
  su domanda reale o volontario per-distro. Se si riparte: prima slice AUR da sdist
  PyPI (repo AUR separato, test `makepkg` + `namcap` in container Arch fresco,
  `python-textual` gia' in `[extra]`), poi PPA/COPR; `[extra]` ufficiale solo dopo
  trazione AUR (10 voti/1% pkgstats) + sponsor Package Maintainer.
- **Lancio/visibilita'** (discusso 2026-09-14, in attesa): testi annuncio it/en pronti
  in chat + screenshot per lingua; r/commandline bloccato (progetti <30 giorni
  rimossi + regola 8 alternative + disclosure AI) — candidati ora: r/tui,
  r/SideProject (formato storia), Discord Textual; r/commandline dopo il mese
  di vita del repo. Partire solo su via libera esplicito, senza fretta.
