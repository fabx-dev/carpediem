# CarpeDiem — contesto per le sessioni agent

> Leggere questo file all'inizio di ogni sessione di lavoro sul repo.
> Se il tuo commit cambia fatti documentati qui (architettura, convenzioni,
> workflow, lezioni apprese), aggiorna questo file nello stesso commit.
> Lingua dell'utente: italiano. Risposte concise, niente emoji.
>
> Documenti collegati (non caricati di default, leggerli quando servono):
> - `docs/sprint-log.md` — storico delle iterazioni con precedenti e lezioni puntuali.
>   Ogni lavoro concluso aggiunge li' la sua voce, non qui.
> - `docs/roadmap.md` — roadmap architetturale (fasi 0-10, tutte chiuse) e milestone M1-M6.
> - `docs/planner-api.md`, `docs/planner-engine.md`, `docs/adr-*.md` — contratti e decisioni.

## 1. Cos'è

**CarpeDiem** (progetto `carpediem` su PyPI, entry-point `carpediem = carpediem.main:main`) è una
TUI todo-list in italiano/inglese costruita con **Textual** (>=0.86,<4; in venv: 3.7.1).
Python >= 3.12. Repo: `git@github.com:fabx-dev/carpediem.git`, branch `main`.

Avvio: `carpediem` (TUI) oppure `.venv/bin/python -m carpediem.main ...` (venv con `pip install -e .`,
altrimenti `PYTHONPATH=src` dal checkout). Dopo modifiche al codice riavviare la TUI: Python non
ricarica a runtime (un "bug" segnalato era il processo stantio).
CLI non interattiva: `carpediem add|list|done|show|replan` (+ `--porcelain`).

Feature principali: task a 3 stati, sotto-task annidati, ricorrenze, progetti/tag/priorità,
kanban/radar, agenda, calendario, settimana, piano giornaliero, pomodoro persistente,
template, statistiche, goals, salute progetti, archivio, backup zip, import/export CSV,
export Markdown/iCal, cifratura Fernet opzionale, smart list, inserimento in linguaggio
naturale (`ctrl+l`, CLI add), Buongiorno (`P`: contesto + proposta con motivi), piano giorno
operativo (`p`, timeline con eventi fissi/Outlook), chiusura giornata (`R`), replan preview
(`G`), review settimana (`W`), card Why nel dettaglio. Distribuzione: PyPI + Snap.

## 2. Mappa del codice

```
src/carpediem/main.py      entry point + init lingua PRIMA degli import + migrate_legacy()
src/carpediem/app.py       TodoApp: orchestratore (~2570 righe) — god-class nota, vedi §8
src/carpediem/screens/     package per area (form/views/plan/system/menu + _shared, re-export in
                           __init__): dipendono da models/storage/lang/nlparse/plan/domain/planner,
                           MAI da app — comunicano via push_screen + callback
src/carpediem/planner/     motore di pianificazione puro (contratto: docs/planner-api.md):
                           service.Planner (propose -> DayPlan, schedule -> ScheduledDayPlan),
                           scoring/constraints/capacity/explain, scheduler (best-fit atomico),
                           time_model (now vincolante), decisions/narrative (Why), replan (M4),
                           outcomes (3 stati), feedback/calibration (delega a domain), models frozen
src/carpediem/plan.py      wrapper compatibile: plan_day() = Planner.propose().to_legacy()
src/carpediem/domain.py    regole pure (stato+ricorrenza, pomodori, form, piani, execution,
                           calibrazione): mutano solo gli oggetti passati, timestamp espliciti,
                           mai I/O/UI. POMO_MINUTES=30 in lock-step con capacity.POMO_HOURS
src/carpediem/models.py    TodoItem, Priority, Recurrence, MAX_DEPTH=6, TaskExecution
src/carpediem/store.py     TodoStore: commit() = UNICO punto di scrittura dei todos
src/carpediem/storage.py   paths, load/save, lock, merge, backup, config, executions, migrazione
src/carpediem/crypto.py    Fernet + PBKDF2 (600k iter), chiave solo in RAM
src/carpediem/cli.py       add/list/done/show/replan (via TodoStore)
src/carpediem/commands.py  MENU_STRUCTURE (menu `m`) + provider palette `ctrl+p`
src/carpediem/nlparse.py   parser NL it/en deterministico (#tag *progetto !prio ~stima //note)
src/carpediem/lang.py      catalogo STRINGS it/en
src/carpediem/integrations/ Outlook (parse puro + auth: unico punto di rete, PKCE loopback)
tests/                     suite pytest; conftest con isolamento (vedi §5)
```

Flusso standard nelle action: muta oggetti → `store` → `_commit_refresh(chiave_notify, ...)`
(= `store.commit()` + `_populate_table()` + notify). Le screen non salvano mai su disco.

## 3. Dati e persistenza

Percorsi da `storage.config_dir()/data_dir()/backup_dir()` (XDG / Application Support / AppData;
sotto Snap `SNAP_USER_COMMON`). Override `CARPEDIEM_HOME` (alias legacy `TASKO_HOME`), usato dai test.
File: `todos.json`, `templates.json`, `config.json`, `pomodoro.json`, `archive.json`,
`executions.json`, `outlook-token.json` + `.bak.json`/`.corrotto.json`/`.lock` e `backups/*.zip`.
I file legacy (`~/.todo_*.json`, `~/Tasko_backups/`) sono solo sorgenti di `migrate_legacy()`
(copia byte-identica, mai cancellati).

Regole dure:
- Scritture atomiche tmp+fsync+replace sotto lock fcntl (timeout 10s → `StorageLocked`).
- `store.commit()` = lettura+merge three-way+scrittura sotto **un solo lock**
  (`save_todos_synced`): vince chi ha modificato; entrambi modificati vince chi salva;
  cancellato-vs-modificato vince la modifica; collisione id → disco tiene l'id, il nostro
  viene riassegnato (figli inclusi).
- **Fail-closed**: i writer sollevano `StorageUnreadable` su disco illeggibile/corrotto invece
  di sovrascriverlo; `force_rewrite=True` solo per il cambio password. Regression suite:
  `tests/test_storage_failclosed.py`.
- File cifrato senza chiave → `[]` senza `.corrotto` (è blindato, non corrotto). Dopo
  l'unlock l'app fa `_reload_all()`.
- Ogni nuova chiave di config va nella whitelist di `save_config` + validatore in load E save
  (test round-trip su tutte le `DEFAULT_CONFIG`).
- Nuove dipendenze: aggiornare SIA `pyproject.toml` SIA `requirements.txt` (la CI usa il secondo).

## 4. Convenzioni (rispettarle sempre)

- **i18n**: ogni stringa UI via `T("chiave", ...)`, sempre in it E en (`test_parita_chiavi`).
  `T()` valutato all'import (BINDINGS, MENU) segue la lingua fissata da `_apply_startup_lang()`:
  non spostare gli import in `main`.
- **Markup**: ogni interpolazione di testo utente passa da `_escape_markup` (un `[/]` in un
  titolo crasha). Nelle option di `SelectionList` niente `[...]`: usare parentesi tonde.
- **CSS**: shell modali condivisa in `TodoApp.CSS` ("Shell modali condivisa"): nuove screen
  aggiungono `#x-box`/`#x-title` ai gruppi, dichiarano solo lo specifico. Righe bottoni con
  `classes="btn-row"`; non mettere bottoni in coppia nel gruppo close full-width (l'id batte la classe).
- **Layout a cornice fissa** per screen con contenuto scrollabile: box `height: 90%` + figlio
  `height: 1fr`, legend e bottoni fuori dallo scroll. MAI box auto + `max-height` con figli
  auto. Verificare a 70x20 e 80x24 (`tests/test_layout_small.py`, `test_ui_regression.py`).
- **Bottoni**: `variant="default"`; coppia azione `form_save` ("Salva [s]") + `form_cancel`;
  solo visione `ui_close_esc`. `s` salva ovunque (`ctrl+enter` non arriva su molti terminali):
  per questo il focus iniziale non va mai su un Input.
- **Tasti globali**: superficie già ampia. Nuovi tasti solo su richiesta esplicita; preferire
  menu `m` / palette `ctrl+p`. Maiuscola = variante (`b/B`, `o/O`, `r`/`R`, `p`/`P`, `g`/`G`, `w`/`W`).
- **Screen modali**: `CloseMixin` per `action_close`; screen che ne aprono altre usano
  `self.app.push_screen` o dismiss+callback (mai action App: `check_action` le blocca sotto modale);
  import lazy fra aree di screen; rileggere gli oggetti per id dopo un push annidato.
- **Mai crash da UI**: except ampi intenzionali (ruff esclude BLE/S110/S112), ma i fallback
  che nascondono errori vanno loggati (`_log.exception`).
- **Fallback senza ritorno**: un fallback automatico non scrive mai la config (diventerebbe
  una preferenza fantasma); solo le scelte esplicite dell'utente persistono.
- Date wall-time `"YYYY-MM-DD [HH:MM]"`, niente datetime aware (ruff esclude DTZ).
- **Edit**: BINDINGS/CSS sono duplicati fra classi diverse: usare contesto ampio in old_string
  e verificare con grep dove è finito l'edit.
- Prima del commit si può lanciare il reviewer read-only `.opencode/agents/reviewer.md`.

## 5. Verifica e sicurezza dei dati (obbligatorio prima di dire "fatto")

Gate (la CI li corre tutti; ognuno ha già fatto fallire un push):

```
.venv/bin/python -m pytest tests/ -q
ruff check && ruff format --check
mypy src/
```

**Isolamento dati — regola più importante del repo.** Due incidenti (2026-09-14, 2026-09-21)
hanno sovrascritto i dati reali con task finti da script di debug non isolati; recuperati solo
dai backup zip. Il fail-closed (§3) oggi fa fallire rumorosamente invece di wipare, ma la regola resta:
- Qualunque processo che importi `carpediem.app`, crei `TodoApp()` o usi `run_test` fuori da
  pytest parte con `CARPEDIEM_HOME=$(mktemp -d)` **nello stesso comando** (verificarlo con `echo`).
- Dopo un debug sospetto controllare mtime/dimensione dei file dati reali prima di continuare.
- Nei test la fixture autouse `tmp_files` di conftest redirige tutti i path: ogni nuovo file
  di storage va aggiunto lì, altrimenti i test scrivono in `~`.

Test:
- `conftest` ricarica i moduli: usare import di modulo (`import carpediem.storage as s`),
  mai `from ... import Classe` (stale: rompe `isinstance`).
- Pilot: `async with app.run_test(size=(120, 40))`, doppio `await pilot.pause()` dopo azioni
  modali; preferire attese a condizione (`wait_for`) alle pause fisse. Click ravvicinati sullo
  stesso `Button` vengono assorbiti dal debounce (`active_effect_duration`).
- Testo delle screen via `screen_texts()`; attese via `T(chiave)`, mai stringhe hardcodate;
  mai `.content` diretto (non esiste in tutte le versioni Textual, la CI usa la più recente <4).
- Ogni test con finestra oraria assoluta congela l'ora (seam `plan_mod.datetime`, come
  `test_plan_slots`): altrimenti passa solo di mattina.
- Script ad-hoc: `CARPEDIEM_LANG=it` per output italiano (default: locale → inglese).
- Screenshot SVG: `CARPEDIEM_HOME` fresca **per ogni run**, testo estratto con regex `<text>` +
  `html.unescape` (spazi `&#160;`), verificare anche sotto il fold. Un widget nel DOM non è
  necessariamente visibile; `run_test` non riproduce i problemi di timing del primo paint.

## 6. Git, release e CI

- Commit piccoli in inglese, stile log esistente. Mai `--force`.
- **La sandbox non può pushare**: la chiave SSH ha passphrase e non c'è `ssh-agent`, quindi
  senza terminale `ssh` fallisce con `Permission denied (publickey)`. Commit in locale, poi
  l'utente esegue `git push origin main` dal suo terminale. Non "risolvere" con chiavi senza passphrase.
- **CHANGELOG**: i commit di feature scrivono solo sotto `## [Unreleased]` e non toccano
  `pyproject.toml`. Il commit `chore(release): bump to X.Y.Z` porta il bump, data la sezione
  e riapre `[Unreleased]` vuota. Patch per fix, minor per feature; ogni cambiamento visibile
  va rilasciato.
- **Release**: push → CI tutta verde (`gh run view <id>`) → `gh release create`. `publish.yml`
  (PyPI, trusted publishing) e `snap-release.yml` partono da `release: published`, non dal push:
  un tag a CI rossa pubblica comunque. Verifica finale dell'upload via API JSON di PyPI.
  Dettagli in `docs/release.md` e `docs/snap.md`.
- CI (`ci.yml`): ruff + format + mypy + pytest 3.12/3.13 su Linux (cov ≥75%) e Windows 3.13,
  `build-smoke` della wheel; `snap.yml` builda lo snap. Su Windows: `tzdata` necessario,
  niente check sui mode-bit POSIX.
- Packaging: cancellare `build/` prima di fidarsi del contenuto della wheel (setuptools riusa
  la dir stantia).
- Split di commit misti: classificare gli hunk e validare con round-trip stash → apply →
  commit → md5. `git apply --check` su diff del working tree fallisce per costruzione.

## 7. Lezioni Textual ricorrenti

- `Label` ha `width: auto`: per testo che deve andare a capo serve `width: 1fr`.
- `Button` a `height: 2` collassa il contenuto: usare `height: 3`. Bordi (`border: thick`)
  consumano colonne in celle strette: usare `outline`.
- Focus su un widget trascina lo scroll: per aprire in cima usare `scroll_home` differito con
  `call_after_refresh`.
- `ListView` binda Enter a `select_cursor` (ombra i binding della screen): sottoclassare.
- `DataTable` calcola le dimensioni in idle, dopo il primo paint: finalizzarle esplicitamente
  se l'avvio è lento (`_sync_table_dimensions`).
- Remove+mount rapidi danno `DuplicateIds`: pre-costruire e commutare via classi. Mai
  `mount()` su un widget non ancora montato.
- Le action async vanno attese (`await self.action_x()`).
- mypy: `getattr` non restringe `str | None`; annotare attributi inizializzati a `None`;
  restringere union eterogenee con `isinstance`.

## 8. Architettura (principi vincolanti)

Dettaglio, fasi e milestone in `docs/roadmap.md`. Stato: fasi 0-10 chiuse; M1-M5 fatte;
M6 parziale (#43 *temporal fit* aperta, epic #6 umbrella); decomposizione e AI layer
**non pianificati** per scelta. GitHub Issues contiene solo segnalazioni utente.

- **Evolvere, non riscrivere**: piccoli passi con test, prima preservare il comportamento.
- Planner **puro, deterministico, spiegabile, offline**: niente Textual/storage/rete/AI nel
  planning; ogni decisione ha un motivo `(chiave_i18n, params)`. Guardrail in `tests/test_arch.py`.
- **La UI consuma il Planner** e non decide regole di scheduling (niente costanti di merito o
  capacità in screens/app). Il Planner propone, l'utente conferma.
- Prima di cambiare il Planner rispondere a: input, output, vincoli hard/soft, scoring,
  determinismo, spiegabilità, testabilità senza UI, interazione con capacità e calibrazione.
  Se non è chiaro, fermarsi e discuterne.
- Distinguere sempre stima / durata pianificata / tempo reale. La stima assente vale 1 pomodoro
  solo come fallback di pianificazione (follow-up aperto: "stima mancante ≠ stima 1").
- `app.py`: estrarre una responsabilità alla volta quando esiste un boundary testabile, mai
  mega-refactor.
- Niente astrazioni premature; non eliminare test per semplificare un refactoring.

## 9. Decisioni aperte (non implementare senza discuterle)

- **Lancio/visibilità** (discusso 2026-09-14, in attesa): testi annuncio it/en pronti;
  candidati r/tui, r/SideProject, Discord Textual; r/commandline solo dopo il primo mese di vita
  del repo. Partire solo su via libera esplicito.
- Igiene dei `planned_for` passati: nessuno li pulisce mai (da valutare).
