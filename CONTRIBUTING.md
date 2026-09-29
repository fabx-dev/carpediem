# Contributing

Hobby project, Italian-first. Issues in Italian or English welcome.

## Issues: only real user reports

**This repository's GitHub Issues is for user-facing bug reports and feature
requests from people who actually use CarpeDiem.**

Until September 2026 the issue tracker held the project's own development plan
(issues #1–#53, the M1–M6 milestones). Those were created by the maintainer to
drive the work, not reported by users, and they were closed in a single triage
against the real code. Only #6 (the M6 umbrella) and #43 (the missing
*temporal fit*) remain open, and they are maintainer-owned.

So please do not treat the open issue count as a roadmap, and do not file a
planning issue. The development plan is tracked in `AGENTS.md` §9, the
milestone status in §9.12, and every user-visible change in `CHANGELOG.md`.

What belongs in Issues:

- something the app does wrong, with the version, the language and steps;
- a workflow you cannot complete with the current UI or keys;
- a data-loss or privacy problem (these are treated as urgent).

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

## Planning features

Open a discussion (or read the existing plan) **before** writing the code if a
change touches the planner. The project's rule is that scoring, constraints and
capacity move one at a time, each with its own tests, and that the planner stays
pure, deterministic and explainable — no Textual, no I/O, no network. A patch
that changes what the planner decides without a deterministic fixture or an
equivalence test will be asked to grow one.
