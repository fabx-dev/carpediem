# Piano Ponte-Calendario — integrazione Calendario stile Todoist per CarpeDiem

> Stato: pianificato 2026-09-12, non iniziato. Non implementare senza via libera esplicito.
> Scelte utente vincolanti: subito API Google Calendar (non solo file), solo task con
> ora, overlay solo in Agenda, completati esclusi. Google prima, Outlook dopo.

## 0. Contesto e decisioni già prese

- CarpeDiem: TUI Textual offline-first, zero rete, JSON locali + Fernet (chiave solo RAM),
  workflow `n` cattura → `P` Buongiorno → `p` piano/pomodoro → `R` Review,
  `plan_day()` (`src/plan.py`) con capacità `day_hours/0.5🍅`, `due YYYY-MM-DD [HH:MM]`,
  `stima_pomo`, `planned_for`.
- Lezione mercato (sessione 2026-09-12): nessun big fa bidir Tasks↔To Do nativo;
  Todoist fa overlay eventi read-only + push task con ora su calendario separato.
  Copiamo quello, non la sync totale.
- Regole dure (stesse di AI-1, vedi AGENTS.md §8): consenso-sempre (la preview e'
  il consenso), mai segreti in config/log/notify/backup, mai rete nei test
  (fake provider), mai scritture senza conferma (solo additivo via `store.commit()`),
  niente nuovi tasti globali, tutto it/en, trasporto stdlib (niente nuove dipendenze).
  Regola OAuth: flusso non documentato che si rompe 2 volte per cause loro →
  la riga si toglie invece di inseguirla.

## 1. Obiettivo / non-obiettivi

- Obiettivo: eventi esterni come contesto read-only in Agenda + push manuale dei task
  CarpeDiem con ora su calendario separato `CarpeDiem` + reschedule-back limitato e confermato.
- Non-obiettivi v1: sync Google Tasks/MS To Do come task-list, auto-sync/background,
  multi-provider simultaneo, priorità/tag/progetto come campi nativi fuori,
  sotto-task profondi, ricorrenze complesse perfette, ora su Google Tasks.

## 2. Architettura e file

- Nuovo `src/cal.py`: seam `CalendarProvider` (`list_events(finestra)`, `push_diff()`,
  `ensure_calendar()`), mapping puri `carpediem_to_event/event_to_carpediem`, parse/serialize
  ICS stdlib (riuso per cache e debug), nessun import da `app`.
- Nuovo `src/cal_google.py`: trasporto stdlib (`urllib` + `http.server` loopback),
  OAuth desktop, refresh, chiamate `calendarList/list`, `events/list/insert/patch/delete`.
  Niente `google-api-python-client`.
- Innesti esistenti: `TodoStore.commit()` (`src/store.py:125`) unico punto di scrittura;
  `_ical_event_lines` (`src/app.py:1937-1970`) portata a livello Todoist;
  `AgendaScreen` (`src/screens.py:917-1015`) + `action_view_agenda` (`src/app.py:1000`);
  `plan.py` intoccato (esterni mai in capacità); menu `src/commands.py` cat
  Giornata/Sistema + palette; chiavi `lang.py` it/en.
- Dati nuovi: token `~/.todo_sync_tokens_calendar.json` (0600, fuori backup/log/config),
  cache `~/.todo_cal_cache.json` (ultimi eventi + `synced_at`, via `TASKO_HOME` nei test),
  mappa `~/.todo_cal_map.json` (`{carpediem_id: {eventId, calendarId, updated, sequence}}`).
  Mai in `Tasko_backups/*.zip`, mai con Fernet, mai nei log/notify.

## 3. Mapping e criteri (specchio Todoist)

- Push solo se `state == attivo`, `due` con `HH:MM` valida, non cancellato.
  Sospesi/completati/senza-ora esclusi.
- `title → summary`; `due HH:MM + stima_pomo (×0.5h, default 1🍅) → start.dateTime
  floating + end = start + durata`; `notes + progetto/tags/priorità → description`
  sola andata; `id → extendedProperties.private.carpediemId + UID carpediem-{id}@carpediem.local`
  (match mai per titolo); `recurrence` solo se semplice, altrimenti singola occorrenza;
  completamento → cancella evento (scelta "Esclusi").
- Overlay finestra ieri → oggi → +7gg, sezione `Impegni esterni (sola lettura)`
  non selezionabile, mai in Inbox/piano/widget/backup/digest; offline = cache + riga
  `offline, solo CarpeDiem`.
- Ritorno: solo eventi linkati (nome/data/ora/durata/ricorrenza globale) → `due` CarpeDiem
  dopo conferma per-riga, last-write-wins dichiarato; delete evento non tocca il task;
  nuovo evento in `CarpeDiem` non crea task; "solo questa istanza" ignorata con avviso.

## 4. Auth (BYO, un provider alla volta)

- Schermata **Connessioni** in Sistema (stile `SecurityScreen`): stato, Connetti
  (loopback), Disconnetti (+ chiede se rimuovere eventi `CarpeDiem`, mai altri calendari),
  campo client-ID mascherato o env/file 0600. Scope minimo `calendar.events`.
  Niente tasti globali nuovi; voci menu/palette `cal_*`; CLI `carpediem cal pull|push|status`.
- Mai rete in avvio/`commit`/`P`/`p`/`R`; solo azioni esplicite; `disconnect` cancella il token.

## 5. UI/i18n/CSS/test (convenzioni repo)

- Chiavi nuove `cal_*` sempre it+en (parità imposta da `test_parita_chiavi`);
  `SelectionList` senza `[...]` nelle label; cornice fissa `height: 90%` + figlio `1fr`;
  bottoni `form_save`/`form_cancel` o `ui_close_esc`; `s` salva, mai solo `ctrl+enter`.
- Test: fake `CalendarProvider`, mai rete, `TASKO_HOME` isolata,
  `run_test(size=(120, 40))`, `screen_texts()` + `T(chiave)`, layout 120×40/80×24/70×20,
  `ruff check` + `ruff format --check` + pytest 3.12/3.13.

## 6. Slice eseguibili con stop-criterion

- **S0 — fondamenta senza rete:** fix `_ical_event_lines` (DTEND da stima, SEQUENCE,
  fold 75 ottetti, filtro attivo+ora, UID stabile), `src/cal.py` mapping + fake,
  7 casi mapping. Stop: ruff ×2 + pytest verdi.
- **S1 — OAuth + calendario `CarpeDiem` + push con preview:** loopback, ensure calendario
  separato, preview additiva, mappa ID. Stop: push reale su calendario test,
  secondo push senza duplicati.
- **S2 — overlay Agenda + cache offline:** sezione read-only, cache, mai in `plan_day`.
  Stop: Agenda senza rete apre e dichiara offline; 3 taglie layout verdi.
- **S3 — reschedule-back limitato:** conferma per-riga, tabella sync documentata.
  Stop: round-trip senza resurrezioni/ghost.
- **S4 (futura) — Outlook + inbox Tasks:** riuso seam; device-code-first in TUI/SSH;
  inbox pull one-way separato, mai nello stesso passo.

## 7. Rischi e rimedi

- OAuth/revoke/quota → `disconnect/reconnect` guidato + diagnostica (quale token,
  quale calendario, quanti eventi), mai "errore generico".
- Fusi/ricorrenze → floating + degrado dichiarato in preview, mai perdita silenziosa.
- Supporto → una pagina help + `status`, niente background da debuggare.
