# Changelog

Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Entries in English from now on.

## [0.8.1] - 2026-09-16

### Fixed
- The task-form calendar picker now actually shows the day numbers and
  weekday header: day cells were `height: 2`, which collapsed Textual
  `Button` content to zero, leaving an empty see-through grid. The popup
  is now properly centered (fixed-height box sized to fit all weeks).
- The calendar button is now a compact 📅 icon (with a tooltip) instead
  of the clipped "Scegli data" label, freeing space for the date input.

## [0.8.0] - 2026-09-16

### Added
- The due-date field in the task form now has a `📅` button that opens a
  clickable monthly calendar (`CalendarPickScreen`) to pick a date instead of
  typing it by hand. Picking a day sets `YYYY-MM-DD` and keeps any time
  already typed, so you can still add `HH:MM` afterwards. The popup supports
  `‹`/`›` month navigation, an `Oggi`/`Today` shortcut, arrow-key movement
  and `Enter` to select; `Esc` cancels.

## [0.7.2] - 2026-09-16

### Fixed
- Radar chart no longer gets stuck in text mode: the empty-chart fallback
  is now transient (never written to config) and the chart reappears
  automatically as soon as tasks with due dates exist. Explicit `b`/settings
  choices are never overridden. Note: if your radar is stuck in text mode
  from 0.7.0/0.7.1, press `b` once to restore the chart
- Radar caption now shows the count of open tasks without a due date, so
  additions without deadlines are visible too
- Silent radar draw failures are now logged instead of swallowed

## [0.7.1] - 2026-09-16

### Fixed
- Radar chart mode (`b` cycle) is now persisted across restarts instead
  of falling back to the chart every time
- Radar click no longer stacks duplicate detail screens on fast double
  clicks, and overlapping-task picker uses unique button ids
- Click hit-test narrowed to the pointed band, detail reopen re-reads
  the task from the store, settings no longer force text mode back to
  chart, and tasks without id are skipped by the radar data

## [0.7.0] - 2026-09-16

### Added
- Home mini-kanban is now a due-date radar chart (priority x horizon
  strip-scatter via textual-plotext, new dependency with automatic
  fallback to the text kanban if unavailable): overdue vs on-time dots, today line,
  legend with worst offenders, and click-to-open (single task opens the
  detail directly, overlapping tasks open a picker popup). Key `b` now
  cycles chart → text → hidden instead of show/hide

## [0.6.1] - 2026-09-15

### Fixed
- Daily-plan keys `o`/`O` now start/pause the pomodoro as the recommended
  workflow already promised (they only worked from home before)

## [0.6.0] - 2026-09-15

### Added
- Daily plan (`p`) is now operational, not just informative: `Enter` opens
  the task detail (editable via the form, short chain back to the plan)
  and `Space` opens the 3-state chooser exactly as in home, on any plan
  row (recurrences included) — as the recommended workflow already promised

### Changed
- Daily-plan legend, planned-section header and workflow step 3 updated
  to the real keys (no more "Space pauses")

## [0.5.4] - 2026-09-14

### Fixed
- App subtitle is now localized: English UI shows "Manage your tasks"
  instead of the hardcoded Italian string

## [0.5.3] - 2026-09-14

### Added
- Daily plan (`p`) shows an "Upcoming" section: tasks due after today are
  now visible and can be added to today's plan with `+` (they were
  invisible before, with no way to plan them)
- Welcome screen hints that data is stored in plain text and points to
  Menu → Sistema → Sicurezza to encrypt it

### Fixed
- Daily plan: overdue tasks already added to today's plan no longer show
  up duplicated in the overdue section

## [0.5.2] - 2026-09-13

### Fixed
- Welcome screen body no longer overflows its frame (long Italian line
  wrapped past the box instead of wrapping)

## [0.5.1] - 2026-09-13

### Changed
- Renamed the project to CarpeDiem (`tasko` is taken on PyPI): distribution,
  `carpediem` command, UI titles and generated file names. Data files
  (`~/.todo_app.json` and siblings), backups and `TASKO_*` variables are
  unchanged: updating loses nothing.

### Fixed
- Persistence: recurrence clone inherits `stima_pomo`, so follow-up occurrences keep their estimate in the plan
- Persistence: `store.commit()` counts unparsable entries in `last_skipped` instead of dropping them silently
- Persistence: after a same-id merge collision, our children follow the reassigned parent instead of sticking to the disk parent
- Persistence: backups read under per-file lock with microsecond-unique names (no torn reads, no overwrites)
- Persistence: restore validates JSON before touching disk, writes atomically per file, and rolls back on failure
- UI: user text (`[...]`) is escaped in every markup-rendered widget — titles containing `[/]` no longer crash the detail view with MarkupError (toasts and error messages included)
- UI: 11 more screens moved to the fixed-frame layout, holding at 70x20 and 80x24 terminals
- UI: App actions are inert under modals, so single-key bindings can no longer stack screens over dialogs or quit from under a confirm (focus navigation and calendar-to-day still work)
- UI: fixed dead click handlers (calendar day, pomodoro bar hints) and two misleading hints

## [0.5.0] - 2026-09-13

### Added
- Unified morning view ("Buongiorno", key `P`): today context (counts, load, yesterday, streak) plus the smart proposal with inline reasons and confirm in a single screen, no print (the plan on disk is the real document)
- Buongiorno explains its additive semantics (already planned stay, Esc writes nothing) and the summary counts items to confirm, already planned and excluded
- Evening report has a "Go to Day closing" bridge button (one click instead of close plus `R`)
- Evening report distinguishes "nothing planned today" from a cleared plan
- Day closing explains its overwrite semantics (selection becomes exactly tomorrow plan) and the notification reports removed counts
- Windows support: inter-process file locking via msvcrt, full test suite running on windows-latest in CI

### Fixed
- Evening report print no longer exports the navigation hint and notifies "Resoconto salvato"
- Evening report hint and buttons are pinned outside the scroll, holding the frame on small terminals
- Day closing content scrolls with pinned legend and buttons (frame held at 70x20)
- Review and proposal labels hide internal `#id` and escape user `[brackets]` in titles

### Fixed
- State picker is now a 2x2 grid with arrow-key navigation and Enter to choose; labels carry no key hints and the unbound `1`/`2`/`3`/`O`/`P`/`X` shortcuts are gone (legend: arrows move, Enter chooses, Esc cancels)
- State picker title states the current state plainly and marks it with `●`, focusing its button
- Buongiorno empty state always shown when there is nothing to plan (was silently missing)
- Buongiorno content scrolls with pinned legend and buttons, so the frame holds on small terminals
- Buongiorno proposal labels use an em-dash for over-capacity/dismissed flags instead of extra parentheses
- Post-confirm notification reports added, already present and postponed counts
- Removed dead morning briefing / smart plan duplication (single `plan_day` call, no fake `P`/`m` hints in modals)
- Evening report hint now states the real steps (close, then `R` for day closing)
- Briefing and smart-plan popups use the shared modal frame; day closing uses the fixed-frame pattern (list no longer overflows on small terminals)
- Buongiorno proposal labels no longer show internal `#id` and omit empty `()` so reasons are not cut off by the terminal width
- Concurrent edits are no longer lost: deletions made by another process (e.g. CLI while the TUI is open) stay deleted, and external changes appear in memory instead of being silently overwritten on the next commit
- Clearing all filters also clears the persisted filter state (it no longer comes back after a restart)
- Legacy items without a creation date keep it empty instead of getting a fake "now" timestamp on every save
- Legacy items without an id no longer duplicate on every commit
- Restoring a snapshot first saves the current state as a rollback backup and writes under lock

### Removed
- Morning-only briefing keys and menu entries (`menu_plan_*`, `menu_brief_*`, `brief_m_title/empty/sec_top/hint`)

## [0.4.0] - 2026-09-12

### Added
- Recommended workflow guide: first Day menu entry with a 5-step daily checklist (quick add, morning, day, evening, week)
- Natural-language capture in form (`ctrl+l`) and `tasko add "<phrase>"` with `#tag *project !prio ~estimate //note`
- Smart day planner (`P`) with hour capacity plus morning briefing and evening report
- Agenda view: chronological radar for overdue, today, tomorrow, next 7 days and important undated tasks
- Manual iCal (`.ics`) export for active tasks with due dates
- `TodoStore`: central todo container with id lookup, mutations and single `commit()` write path
- Inter-process file locking (fcntl) with timeout for all state saves
- Three-way per-id merge on save: CLI and TUI no longer overwrite each other
- Tests: `test_store.py`, `test_concurrency.py`, `test_failure_paths.py`

### Fixed
- Day menu now groups temporal views together (agenda, plans, week, calendar, briefings/review)
- Locked (encrypted, no key) files no longer faked as corrupt `.corrotto.json` backups
- CLI `add`/`done` go through the store (lock + merge)

### Removed
- Dead code: write-only `_trash`, unbound `action_toggle_theme`, duplicated `_apply_startup_lang`
- Stale `build/` artifacts untracked (now git-ignored with caches and `dist/`)


### Added (sprint 5)
- Day closing review: today summary (done vs goal, pomodoros) and tomorrow plan picker with top-3 preselection (menu entry, no new global key)
## [0.3.0] - 2026-09-10

### Added
- Project health view (OK / At risk / Critical) with key and menu entry
- CLI (`add`, `list`, `done`, `show`) with `TASKO_HOME` isolation
- Complete Italian/English coverage: all screens, notifications, dates, defaults
- Due-time reminders polish and fully isolated test fixture

### Fixed
- Removed useless Maximize entry from menu

## [0.2.0] - 2026-09-10

### Added
- Optional file encryption (Fernet) with startup lock screen and Security menu
- Due-time reminders (10 min lead) with bell, pomodoro end sounds, sound settings
- Onboarding with demo data, app settings screen, template editing
- Archive for done tasks with viewer and restore, CSV import
- Goals with streaks, per-project breakdown, peak hours, punctuality, heatmap, stats CSV export
- Full Italian/English UI with system detection

### Fixed
- Isolated test fixture (tests can no longer touch real home files)
- Double detail popup on repeated clicks, pomodoro bar countdown, calendar alignment

## [0.1.0] - 2026-09-09

First public release.

### Added
- Tasks with subtasks, states, priorities, due dates, tags, projects, recurrences, 🍅 estimates
- Home kanban + full board, calendar, week view, daily plan, detail view
- Full pomodoro cycles (focus/short/long breaks) with persistence and live bar
- Stats: goals and streaks, per-project breakdown, time slots, punctuality, heatmap
- Creatable/editable templates, CSV import/export, archive, zip backup + restore
- Optional file encryption (Fernet) with startup lock screen
- Italian/English UI with auto-detection
- pytest suite + CI on Python 3.12/3.13
