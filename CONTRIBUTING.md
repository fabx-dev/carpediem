# Contributing

Hobby project, Italian-first. Issues in Italian or English welcome.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Rules

- Every change ships with or updates tests in `tests/` (isolated temp files only —
  never touch real `~/.todo_*` files; see `tests/conftest.py`).
- Keep `ruff check` and `ruff format --check` green on `src/` and `tests/`.
- UI text goes through `src/lang.py` in **both** languages (`T("key")` + parity test).
- Small, focused commits; one feature per PR.

## Layout (`src/`)

- `models.py` — TodoItem, priorità, ricorrenze, validazioni
- `storage.py` — paths, load/save, backup/restore, config
- `screens.py` — tutte le schermate modali (dipendono solo da models/storage/lang)
- `commands.py` — provider menu/palette
- `cli.py` — `carpediem add|list|done|show`
- `app.py` — TodoApp (l'unico che importa tutto)
- `main.py` — entry point + re-export di compatibilità
- `lang.py`, `crypto.py` — standalone, senza dipendenze interne

## What gets rejected

- New dependencies without discussion (offline-first, lean install).
- Features that break the JSON formats without migration + tests.
- AI/network calls in the default path (opt-in only, mocked in tests).
