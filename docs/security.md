# Security e persistenza — perché è fatto così

## Storage (`src/storage.py`)

- **Locking**: un sidecar `<nome>.lock` per file, `fcntl` su Unix /
  `msvcrt` su Windows, timeout 10s (`StorageLocked` oltre). Il kernel
  rilascia i lock alla morte del processo: niente lock stali. Mai lock
  annidati (nessuna inversione d'ordine).
- **Scritture atomiche**: tmp + flush + fsync + replace, sempre sotto lock
  (`_write_locked`/`_write_bytes_locked`). `with_bak` conserva il file
  precedente in `.bak.json` (un livello).
- **Unico punto di scrittura todos**: `TodoStore.commit()` →
  `save_todos_synced` (lettura + merge three-way + scrittura sotto UN
  solo lock). Il merge (`merge_todo_dicts`) non muta mai gli input;
  semantica: nuovi da entrambi i lati in unione, un solo lato modificato
  vince, entrambi modificati vince chi salva, cancellato-vs-modificato
  vince la modifica, stesso id creato da entrambi → disco tiene l'id,
  nostro riassegnato (i figli seguono il padre riassegnato).
- **Backup**: `create_backup()` legge ogni sorgente sotto il suo lock
  (niente snapshot a metà scrittura), nomi a microsecondi anti-collisione,
  verifica integrità subito (`testzip`, scarta se corrotto), prune a 14.
  Directory `0o700` e zip `0o600` quando supportato (POSIX; su Windows
  no-op senza rompere). Il token Outlook è **escluso** per disegno
  (`_backup_sources` non lo elenca; guardrail in
  `tests/test_backup_security.py` + `test_outlook_auth.py`).
- **Restore**: valida che ogni entry sia JSON *prima* di toccare il disco,
  salva rollback (`create_backup`), scrive per-file sotto lock con rollback
  dei file già sostituiti in caso di fallimento.

## Crypto (`src/crypto.py`)

- **KDF**: PBKDF2-SHA256 600k iterazioni, salt fresco 16 byte per file.
  Envelope `{"v": 1, "salt": hex, "data": token}`. File legacy in chiaro
  restano leggibili (migrazione trasparente).
- **Chiave solo in RAM** (`set_key`); file cifrato senza chiave → `[]`
  senza backup `.corrotto` (blindato ≠ corrotto); chiave errata → `[]` +
  backup. Cambio password in corso (envelope non decifrabile) → il merge
  riscrive la memoria com'è, senza fondere col disco illeggibile.
- **Cache KDF** (`lru_cache(8)`, decisione documentata Opzione C): una
  derivazione costa ~0.08s e le letture dello stesso file (salt stabile)
  sono frequenti; le scritture usano salt freschi e decadono le entry LRU.
  Non rimuovere senza benchmark.
- **Token Outlook separato**: file dedicato `0600` (+ envelope se lock),
  mai nei backup, mai nei log; lettura senza chiave = `None` (fail-closed).

## File generati — matrice

Percorsi nuovi standard per piattaforma (Linux `~/.local/share/carpediem`,
config `~/.config/carpediem`; macOS `~/Library/Application Support/CarpeDiem`;
Windows `%LOCALAPPDATA%\CarpeDiem` / `%APPDATA%\CarpeDiem`; override
`CARPEDIEM_HOME`). I nomi legacy (`~/.todo_*.json`, `~/Tasko_backups/`) sono
solo sorgenti di migrazione (copia byte-identica, mai cancellati).

| File | Contenuto | Permessi | Backup | Cifratura |
| --- | --- | --- | --- | --- |
| `todos.json` | task | default | sì | envelope se lock |
| `templates.json` | template | default | sì | envelope se lock |
| `config.json` | config (mai segreti) | default | sì | no (solo non-segreti) |
| `pomodoro.json` | timer | default | sì | envelope se lock |
| `archive.json` | archivio | default | sì | envelope se lock |
| `executions.json` | history M2 | default | no | envelope se lock |
| `outlook-token.json` | token MSAL | `0600` | **mai** | envelope se lock |
| `backups/carpediem_*.zip` | snapshot | `0600`, dir `0700` | n/a | come le sorgenti |
| `*.tmp` / `*.restore_tmp` | scritture in corso | default | n/a | già cifrati |
| `*.lock` | lock inter-processo | `0644` | n/a | vuoti |

## Error handling e segreti

- Le UI non devono mai crashare: `except` ampi intenzionali (ruff esclude
  `BLE/S110/S112` di proposito). Ai boundary critici (storage/crypto/
  Outlook/CLI) ogni `except` ha un fallback fail-closed: default sicuri,
  `None`, skip-entry, `OSError` con rollback — mai `pass` su stato
  persistito (verificato nell'audit 2026-09-30).
- Nessun segreto in log/eccezioni/output: `OutlookError` porta solo codici
  (+ dettagli troncati a 120 char, mai token); `_CallbackHandler`
  non logga (l'URL contiene il code); i `logging.exception` in app/views
  coprono solo fallimenti del planner (dati task, mai chiavi/token).

## Planner

Puro per costruzione: niente I/O, rete, UI, i18n (verificato via import
chain + guardrail `tests/test_arch.py`). A parità di input, stesso output.
