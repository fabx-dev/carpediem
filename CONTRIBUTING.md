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
- `domain.py` — pure domain rules (state, pomodoros, smart-match, calibration)
- `storage.py` — paths, load/save, backup/restore, config
- `store.py` — TodoStore, the single `commit()` write path with merge
- `screens/` — modal screens by area (`form`, `views`, `plan`, `system`, `menu`,
  plus `_shared`); they push via callbacks and never touch the disk
- `planner/` — explicit boundary (`service`, `scoring`, `constraints`,
  `capacity`, `scheduler`, `feedback`, `calibration`, `explain`); pure,
  no Textual, UI consumes `Planner → DayPlan → Scheduler`
- `plan.py` — legacy `plan_day()` wrapper (compat only, the app never calls it)
- `nlparse.py` — deterministic it/en natural-language parser
- `commands.py` — menu structure + palette provider
- `cli.py` — `carpediem add|list|done|show`
- `app.py` — TodoApp (the only one importing everything)
- `main.py` — entry point + compat re-exports
- `lang.py`, `crypto.py` — standalone, no internal dependencies

Architectural guardrails live in `tests/test_arch.py`: screens never duplicate
scoring, capacity or scheduling, and production code never calls legacy
`plan_day()`. Screenshots for the README are generated isolated
(fresh `TASKO_HOME` per run, `TASKO_LANG` + `set_lang` reload) — see AGENTS.md §5.

## What gets rejected

- New dependencies without discussion (offline-first, lean install).
- Features that break the JSON formats without migration + tests.
- AI/network calls in the default path (opt-in only, mocked in tests).
