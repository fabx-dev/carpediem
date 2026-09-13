# CarpeDiem

CarpeDiem (carpe diem — cogli il giorno) trasforma appunti veloci in un piano giornaliero realistico: inserimento in linguaggio naturale, proposta smart al mattino, pomodoro durante il giorno, chiusura serale. Offline, in italiano o inglese, senza account.

```text
Segna tutto in secondi (n, linguaggio naturale) → al mattino Buongiorno con proposta da confermare (P)
→ lavora dal Piano giorno con pomodoro (o) → la sera Chiusura giornata (R).
```

Dentro l'app, apri il menu (`m`) → `Giornata` → `Workflow consigliato` per la checklist quotidiana in 5 passi.

[Read in English](README.md)

![CarpeDiem home](docs/screenshots/home.svg)
![CarpeDiem stats](docs/screenshots/stats.svg)

## Installazione in 2 minuti

1. Serve Python 3.12+: verifica con `python3 --version`.
2. Consigliato: installazione isolata con pipx (mette `carpediem` sul PATH):
```bash
pipx install .
```
Dal repo git:
```bash
pipx install git+https://github.com/fabx-dev/carpediem.git
```
3. Alternativa per sviluppatori (virtualenv):
```bash
python3 -m venv .venv
.venv/bin/pip install .
```
4. Avvia la TUI:
```bash
carpediem
```
Al primo avvio: carica i dati demo per esplorare, oppure inizia da zero.

Verifica che funzioni:
```bash
carpediem --help
carpediem list
```

Problemi comuni: `pipx: command not found` (installa prima pipx), Python vecchio (<3.12), dati separati con `TASKO_HOME=/tmp/carpediem-demo carpediem`. Docker (`docker compose up`) solo per sviluppo, non come installazione principale.

Serve Python 3.12+. Costruito con Textual; dati in JSON locali (vedi Dati sotto).

## Tasti

| Tasto | Azione |
|---|---|
| `n` / `s` | Nuovo todo / sotto-task del selezionato |
| `Space` poi `1/2/3` | Attivo / Sospeso / Fatto |
| `Enter` / `e` | Dettagli (con modifica) / Modifica |
| `d` / `u` | Elimina (conferma) / Annulla eliminazione |
| `o` / `O` / `X` | Avvia-apri pomodoro / pausa-riprendi / completa-salta |
| `b` / `B` | Mini-kanban / board completa |
| `c` / `w` / `p` / `k` | Calendario / settimana / piano / statistiche |
| `f` / `t` / `g` / `/` | Filtri stato, tag, progetto, ricerca |
| `T` / `v` / `m` / `h` | Template / tema / menu / aiuto |
| `q` | Esci |

Il menu `m` raccoglie impostazioni, obiettivi, backup, import/export e archivio. La voce `Tasti` elenca tutto.

## Dati

Tutto in JSON locali vicino alla home (offline-first):

| File | Contenuto |
|---|---|
| `~/.todo_app.json` | Task (+ copia `.bak.json` precedente) |
| `~/.todo_templates.json` | Template |
| `~/.todo_pomodoro.json` | Sessione timer + ciclo |
| `~/.todo_config.json` | Tema, filtri, obiettivi, lingua |
| `~/.todo_archive.json` | Completati archiviati |
| `~/Tasko_backups/` | Snapshot zip automatici (14 tenuti) |
| `~/CarpeDiem_screenshots/` | Screenshot SVG, export CSV/Markdown |

Ripristino dal menu (`Backup: ripristina`). Lingua automatica dal sistema, forzabile con `TASKO_LANG=it|en` o dalle Impostazioni.

## Sviluppo

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
python -m ruff check src/ tests/
```

Vedi [CONTRIBUTING.md](CONTRIBUTING.md). Progetto hobbistico, italiano-first: issue in italiano o inglese benvenute.

## Licenza

MIT — vedi [LICENSE](LICENSE) e [CHANGELOG.md](CHANGELOG.md).
