# Phase 1 — Planner Domain Consolidation: implementation plan (revised)

*(PLAN MODE origin — produced read-only, refined read-only. Verified against the repo on 2026-09-30. This revision preserves the baseline plan's architecture, evidence, dependency analysis, test strategy, and migration structure; it applies exactly four corrections plus a consistency pass. Related: `docs/planner-engine.md` §16 Phase 1, `docs/adr-001-planner-boundary.md` (unchanged), `AGENTS.md` §9.)*

---

## 1. Executive summary

> **The planner is already extracted; this phase consolidates the existing boundary.**

Current state (verified, `CURRENT`):

- `src/planner/` is a real, working application boundary: `service.Planner.propose()` / `Planner.schedule()`, plus `scoring`, `constraints`, `capacity`, `explain`, `scheduler`, `decisions`, `narrative`, `replan`, `feedback`, `calibration`, `models` (`DayPlan`, `PlanItem`, `ScheduledDayPlan`, `ScheduledItem`, `TimeWindow`, `FixedEvent`, `ExecutionFeedback`). Public re-exports in `src/planner/__init__.py`.
- `src/plan.py` is a compatibility wrapper (`propose().to_legacy()`), production-consumer-free (only `tests/test_planner.py`, `tests/test_scheduler.py` use `plan_day`; `tests/test_arch.py` forbids it in `src/screens/*` + `src/app.py`).
- The pipeline is deterministic **given explicit inputs** (eligibility → merit → selection → `DayPlan` → `schedule` → `decisions`), pure modules (no I/O, UI, Textual, storage, network inside `src/planner/` — enforced by `tests/test_domain.py::test_arch_purezza_no_import_app_ui`), with read-only replanning (commit = `domain.apply_replan` + store, owned by app/CLI).
- `docs/planner-engine.md` (§16, Phase 1) and ADR-001 (`docs/adr-001-planner-boundary.md`, unchanged by this plan) agree: Phase 1 is **Domain Consolidation, not extraction** (Known conflict #1).

Goal of Phase 1 (`PHASE 1 TARGET`): make the existing boundary **cleaner, more deterministic, and more self-contained** while preserving behavior byte-for-byte where it matters:

1. Own task projection — stop typing the public path on `TodoItem` (Known conflict #3) via a planner-owned **projection/compatibility** view, explicitly not the future canonical model.
2. Explicit time in production — all production callers provide explicit `today`/`now`; planner internals prefer explicit values; legacy `None` fallbacks remain temporarily as isolated, documented, characterization-tested compatibility paths (removed definitively in a later phase, not Phase 1).
3. Make `planner → domain` / `planner → models` couplings explicit at the boundary (calibration source of truth stays in `domain` until Phase 5).
4. Introduce the single input/output shape as an **internal** normalization first; public `PlanningRequest`/`PlanningResult` and `planner.plan(request)` remain Phase 2+/7 work.

Explicitly **not** in Phase 1: `planner.plan(request)` / `planner.replan(request)` as frozen public API, timezone/DST, constraint framework, diagnostics engine, REST/MCP/package extraction (§17 non-goals).

---

## 2. Current dependency map

Verified by import scan (`src/planner/*.py`, consumers in `src/`, guardrails in `tests/`).

```text
CURRENT (verified)

  UI / app / CLI                          (consumers, never consumed)
  ├── src/screens/plan.py                 Planner, events_to_busy, explain,
  │                                       feedback, DayPlan/FixedEvent/PlanItem/
  │                                       ScheduledDayPlan/TimeWindow, replan+constants,
  │                                       + scheduled_for_today() (app-side builder,
  │                                       NOT planner code), day_window_parts()
  ├── src/screens/views.py                Planner, decide (+narrative), plan_decisions()
  │                                       helper + domain.calibration_samples()
  ├── src/cli.py                          replan + TimeWindow + events_to_busy (lazy),
  │                                       + screens.plan.day_window_parts/
  │                                       scheduled_for_today (documented debt),
  │                                       + _domain.apply_replan
  └── src/app.py                          (no direct planner import; orchestrates
                                          via screens; guardrail-forbidden from
                                          execution_stats/summary — test_arch.py)
                    ↓
  src/planner/__init__                   (public re-export surface, no logic)
  ├── service.Planner                     propose() / schedule() [static thin wrapper]
  ├── scoring / constraints / capacity / explain   (propose pipeline)
  ├── scheduler.schedule / events_to_busy          (temporal placement)
  ├── decisions / narrative              (read-layer over DayPlan)
  ├── replan.replan                       (reuses propose+schedule, pure)
  ├── feedback.feedback                   (pure derivation)
  └── calibration                         (thin wrappers over domain)
                    ↓
  src/models.TodoItem + helpers           Priority, TodoItem (service, scoring),
                                          _due_date_part (scoring, capacity)
  src/domain                              calibrated_estimate + CAL_CLAMP_* (capacity),
                                          calibration_factor (calibration.factor_for),
                                          execution_* (calibration.calibration_summary),
                                          execution_confidence (decisions),
                                          apply_replan (NOT imported by planner —
                                          owned by app/CLI, correct)
  stdlib only                             models.py, explain.py, scheduler.py
                                          (scheduler imports capacity.POMO_HOURS —
                                          intra-planner, fine)
```

Purity guardrails (must keep passing unchanged): `tests/test_domain.py::test_arch_purezza_no_import_app_ui` (no `src.app`/`src.screens`/`src.lang` imports in planner — `models.py` exempted for lang) and `tests/test_arch.py` (6 tests: no merit constants, no planner reimplementation, no legacy `plan_day`/`src.plan`, no execution I/O in screens, no execution stats in app, no internal stages in `views.py`).

Dependencies that **remain** (deliberate): stdlib; intra-planner imports; frozen planner models; `domain.apply_replan` staying **outside** the planner (called by app/CLI only).

Dependencies **targeted for reduction** in Phase 1: `TodoItem` typing on the public path; `Priority` enum + `_due_date_part` imports from `models`; direct `domain` value-math imports (`calibrated_estimate`, `execution_confidence`, `execution_*` summary functions) — wrapped, not duplicated; implicit wall-clock reads — isolated behind explicit-first resolution with documented compat fallback.

---

## 3. Current planner contract

Real API today (no invention):

| Entry | Signature (effective) | Input | Output |
|---|---|---|---|
| `Planner(todos, *, today=None, hours=6.0, factor=None).propose()` | `src/planner/service.py:25-38` | `list[TodoItem]`, `today: str\|None` (`""`/`None`/unparseable → `datetime.now()` fallback, line 40), `hours: float`, `factor: float\|None` (`None` → auto via `calibration.factor_for`) | `DayPlan` (frozen: `day: date`, `planned/cut/skipped: tuple[PlanItem]`, `capacity_pomo`, `planned_pomo`, `factor`) + `.to_legacy()` compat |
| `Planner.schedule(plan, availability, busy=())` | `service.py:93-96`, static thin wrapper | `DayPlan`, availability/busy iterables of `TimeWindow` (also accepts raw tuples in tests — `_normalize` ignores non-`TimeWindow`) | `ScheduledDayPlan` (frozen: `plan`, `scheduled/unscheduled` covering exactly `plan.planned`, echo `availability/busy` normalized) |
| `replan(todos, today, hours, availability, busy=(), now=None, *, current=None, sample_count=None)` | `replan.py:85-95` | same task set + `today: str`, `hours`, windows, `now: datetime\|None` (`None` → `datetime.now()`, line 104), optional `current: ScheduledDayPlan` | `ReplanProposal` (frozen: `day`, `now`, `moves: tuple[ReplanMove]` kept/moved/dropped/added, `capacity_pomo`, `planned_pomo`, `residual_pomo`) |
| `feedback(scheduled_plan, todos)` | `feedback.py:25` | `ScheduledDayPlan` + `list[TodoItem]` | `tuple[ExecutionFeedback]` (one per `plan.planned`, same order) |
| `decide(plan, todos, *, sample_count=None)` / `refine_with_schedule(decisions, scheduled)` / `primary_reason(d)` | `decisions.py` | `DayPlan` + todos (evidence lookup; tolerant: `todos=None`/mismatch → `""` evidence) | `tuple[PlanningDecision]` (frozen: `todo_id`, `decision ∈ {scheduled,not_scheduled,deferred,constrained}`, `reasons`, `evidence` dict, `confidence: str\|None`) |
| `explain_decision(d)` / `explain_proposed(d)` | `narrative.py` | `PlanningDecision` | `(chiave_i18n, params) \| None` — keys only, never rendered text |
| `calibration.factor_for(todos)` / `observe[_all](fb)` / `calibration_summary(executions)` | `calibration.py` | todos / `ExecutionFeedback` / executions history | `float\|None` / observation pairs / summary dict |
| `events_to_busy(events)` | `scheduler.py:87` | `FixedEvent`s | `tuple[TimeWindow]` |
| App-side builders (NOT planner): `screens/plan.py::scheduled_for_today()` (line 190), `screens/views.py::plan_decisions()` (line 1179), `cli.py::_cli_replan` | — | todos + today + hours + day_window dict | `ScheduledDayPlan` / decisions / printed preview; commit via `domain.apply_replan` + `store.commit()` |

Data flow today: `PlanProposalScreen → Planner.propose() → DayPlan → Planner.schedule() → ScheduledDayPlan → UI`; `DailyPlanScreen`/`Briefing` via `scheduled_for_today()` (propose filtered to confirmed `planned_for == today`, re-wrapped in a new `DayPlan` — no second scoring); `DetailScreen` Why via `plan_decisions()`; `ReplanPreviewScreen` (`G`) + CLI via `replan()` → `apply_replan` commit.

---

## 4. Target Phase-1 architecture

Narrower than the engine vision (`planner-engine.md` §§5–6, 13). After Phase 1:

```text
PHASE 1 TARGET

  callers (screens / CLI / tests)
    │  pass TodoItem lists + explicit today/now (compat adapters)
    ▼
  ┌─────────────────────────────────────────┐
  │ src/planner/  (domain core, still in-repo)│
  │                                           │
  │  boundary adapters (NEW, thin):           │
  │    todo_to_task() / resolve_day()         │
  │    (only place that knows TodoItem/str;   │
  │     anti-corruption edge, NOT domain      │
  │     modeling — see §5)                    │
  │                    ↓                      │
  │  core (TodoItem-free, explicit-first):    │
  │    Planner.propose() / schedule()         │
  │    scoring / constraints / capacity       │
  │    scheduler / replan / feedback          │
  │    decisions (+confidence injection)      │
  │    narrative (keys only, unchanged)       │
  │    frozen models (+ TaskView projection,  │
  │      internal PlannerInput normalization) │
  │                    ↓                      │
  │  explicit seams outward:                  │
  │    factor= (injected, auto = compat path) │
  │    confidence= (injected, no domain import│
  │      in decisions)                        │
  │    estimate= (delegates to domain via ONE │
  │      wrapped seam in capacity)            │
  │  isolated compat fallbacks (allowlisted,  │
  │    documented, characterization-tested):  │
  │    today/now None → wall-clock (removal   │
  │    deferred to a later phase, see §6)     │
  └─────────────────────────────────────────┘
    │  commits stay outside:
    ▼  domain.apply_replan + store (app/CLI, unchanged)
```

What changes vs CURRENT: one adapter layer at the boundary; explicit-first time resolution with the legacy fallback isolated (not removed); zero `models`/`domain` imports in scoring/constraints/decisions core paths (single wrapped seams); internal-only normalized input shape. What does NOT change: file layout (no new package), public names/signatures (backward compatible), algorithm (weights, ordering, capacity semantics, scheduler first-fit), `DayPlan`/`ScheduledDayPlan` field layout, reason keys, UI flows.

---

## 5. TodoItem strategy

### 5.0 Architectural status of `TaskView` (binding for implementation)

```text
TodoItem                  (application-owned storage model, unchanged)
   ↓
todo_to_task()            (anti-corruption / compatibility edge, total, pure)
   ↓
TaskView                  (planner-owned PROJECTION, frozen, minimal)
   ↓
Planner Core              (TodoItem-free internals)
```

`TaskView` is a **planner-owned projection**: a minimal normalized input shape and an anti-corruption/compatibility boundary. It is intentionally **not** the future canonical `Task` domain model, not the future public `Task`, and not a precursor that must necessarily evolve into `Task`. The future canonical domain model remains an open Phase 2+ architectural decision (engine doc §4 TARGET list).

Implementation rule:

> **Do not add domain semantics to `TaskView` merely because they might be useful in the future.**

`TaskView` stays as close as possible to a normalized projection of the fields actually required by current planner algorithms (§5.1). Any field addition during implementation requires a concrete, current-algorithm justification recorded in the commit message; otherwise it is rejected in review. If Phase 2 later defines a canonical `Task`, it may consume, replace, or bypass `TaskView` — no Phase-1 commitment constrains that decision.

### 5.1 Fields actually required (verified per module)

| Field | Used by |
|---|---|
| `id` | constraints (`is_eligible`), capacity ordering, service (`PlanItem.todo_id`), feedback key, replan sets |
| `state` (`attivo` + `done`/`paused` derivation) | constraints eligibility, stale_days, calibration ratios, feedback `completed`, replan `current_ids`, `apply_replan` (outside planner) |
| `due` (string, date part only) | scoring (overdue/today/tomorrow), capacity tie-break, decisions evidence/overdue flag |
| `priority` | scoring (`PRIO_SCORES` + `plan_prio` reason), decisions evidence |
| `project` | scoring `stale_days` grouping |
| `planned_for` | scoring `+PLANNED_SCORE`, capacity privilege path |
| `plan_skip` | constraints `partition` |
| `stima_pomo` | scoring `has_est` (reason only), capacity `estimate` (duration) |
| `actual_pomo` | domain calibration ratios (via `factor_for`), `observe` source |
| `created`, `completed_at` | scoring `stale_days` only |
| `pomodoros`, `actual_minutes` | feedback evidence only (`sessions`, `actual_minutes`) |

Application/storage-only (never read by planner): `title`, `notes`, `tags`, `parent_id`, `recurrence`, `source`/`external_id`, `pomodoro_log`.

Additionally planner imports from `models`: `Priority` enum (scoring) and `_due_date_part` helper (scoring, capacity).

### 5.2 Recommendation (Phase 1): narrow frozen `TaskView` projection + adapter, NOT a full `Task` model

Introduce in `src/planner/models.py` (prefer `models.py` over a new module for ~30 lines — no new package surface):

- a frozen dataclass, `TaskView`, with exactly the fields in §5.1 (plain types: `id: int`, `state: str`, `due: str`, `priority: str`, `project: str`, `planned_for: str`, `plan_skip: str`, `estimate_pomo: int`, `actual_pomo: int`, `created: str`, `completed_at: str`, `pomodoros: int`, `actual_minutes: int`), plus `todo_to_task(todo) -> TaskView` (tolerant: `getattr`-based, never raises — mirrors the existing `getattr(todo, "plan_skip", "")` style; normalizes `Priority` enum → `"alta"/"media"/"bassa"` string and `due` → date-part string at the edge).
- Core functions (`score`, `score_all`, `stale_days`, `is_eligible`, `is_skipped`, `partition`, `estimate`, `allocate`, `calibration.factor_for` internal path, `feedback`, `decisions._evidence`, `replan` current-set scan) accept `TaskView` (internally); public `Planner.__init__` / `replan()` / `feedback()` / `decide()` keep accepting `TodoItem` lists and normalize once via the adapter (compat path, zero caller changes).
- `rank_key` and `_due_date_part` usage move to plain-string helpers inside planner (copy the 4-line date-part split; keep `PRIO_SCORES` keyed by normalized string via a tiny local map — do NOT import `Priority` in core anymore).

Why this and not alternatives:

- (A) *Keep `TodoItem`*: rejected as end-state — perpetuates Known conflict #3, blocks any future `plan(request)` contract, keeps storage vocabulary (`pomodoro_log`, `parent_id`, …) visible to the core.
- (B) *`typing.Protocol` / duck-typing only*: rejected as the mechanism — the code already duck-types in places (`constraints`, `replan`, `decisions._evidence` with try/except) but that hides the contract instead of declaring it; a frozen projection makes the required surface explicit and testable.
- (C) *Full `Task`/`Duration`/`Estimate`/`Deadline` value model now*: rejected for Phase 1 — speculative abstraction (§9.5.3, engine doc §17); nothing in the current algorithm needs it, and it risks a duplicate-model maintenance burden (see §16).
- Chosen path solves a concrete current coupling (public path typed on a 20-field storage class when ~13 scalar fields are used) with a reversible adapter; `TaskView` is deliberately named *View* (not `Task`) to signal projection status per §5.0 — Phase 2 decides the canonical model independently.

### 5.3 Conversion without behavior change

- `todo_to_task` is total and side-effect-free; unknown/malformed fields → safe defaults matching current tolerant behavior (`int(x or 0)` → 0, missing → `""`).
- Equivalence gate: fixture-matrix differential test (existing `test_planner_fixtures.py` scenarios + `test_planner.py` legacy equivalence) run against both `TodoItem` input and pre-converted `TaskView` input — outputs must be identical (`to_legacy()` equality + `DayPlan` equality).
- `PlanItem.todo_id` stays `int` (no rename — renames break `scheduled_for_today`, CLI, screens).

---

## 6. Explicit-time strategy

### 6.0 Lifecycle (binding for implementation)

### Phase 1

- All production callers must provide explicit `today` / `now`.
- Planner internals must prefer explicit values (resolution order: explicit `today` → explicit `now` → legacy fallback).
- Legacy `None` behavior **remains temporarily as a compatibility fallback** (repository evidence shows it cannot be removed without compat impact: `plan_day()` compat wrapper, tests, and ad-hoc/screenshot scripts omit `today`; see §6.1).
- Fallback locations are explicitly allowlisted and documented (exactly two: `service.py:40`, `replan.py:104`), covered by characterization tests, and no new `datetime.now()` / `date.today()` call sites may be introduced.

### Later phase

Definitive removal of the compatibility fallback happens in the later temporal/public-contract evolution phase (engine roadmap Phase 3 / Phase 7), once the public contract makes explicit time mandatory. That removal is out of scope here.

Phase-1 completion therefore means:

> **Production planner execution is explicit-time; remaining wall-clock fallbacks are compatibility-only, isolated, documented, and covered by characterization tests.**

It does NOT mean zero `datetime.now()` occurrences in `src/planner/` (see revised §18).

No timezone/DST work in Phase 1 (naive wall-time convention untouched).

### 6.1 Every source of current time (verified)

1. `src/planner/service.py:40` — `scoring.parse_day(self.today or "") or datetime.now().date()`. Trigger: `today` omitted/`""`/unparseable. Effect: whole `DayPlan.day` + all due-comparisons + `planned_for`/`plan_skip` matching shift silently. **Phase 1: retained as allowlisted compat fallback** (removal would break `plan_day()` compat and caller/test code that omits `today`).
2. `src/planner/replan.py:104` — `now if isinstance(now, datetime) else datetime.now()`. Trigger: `now=None` (callers may omit it; both production callers currently pass explicit values — screen from `self.now`, CLI from parsed `--now`/clock — at the caller layer, which is the correct layering). Effect: `_clip_future` window + `ReplanProposal.now`. **Phase 1: retained as allowlisted compat fallback.**
3. Outside planner (NOT in scope, documented only): `models._normalize_date` (`oggi`/`domani`), `storage` timestamps, CLI `today = datetime.now()` (correct: caller supplies time, planner receives it), tests using `datetime.now()` for fixture dates (fine — explicit values by the time they reach the planner).

Planner behavior **does** depend on wall-clock time today via (1) and (2) when inputs are omitted — the explicit-`now` principle (`planner-engine.md` §3 TARGET, Known conflict #2) is therefore satisfied in Phase 1 at the production-execution level, with full determinism deferred to the later phase that makes explicit time mandatory. No timezone/DST involvement: all naive wall-time by repo convention; Phase 1 must not touch that.

### 6.2 Recommendation

Three sub-steps, in order (each independently committable):

1. **Characterize**: add tests pinning the fallback behavior *before* changing it — `Planner(todos)` with frozen `datetime.now` (monkeypatch `src.planner.service.datetime`) produces the same `DayPlan` as `Planner(todos, today=<frozen date>)`; same for `replan(..., now=None)` vs explicit `now`. These tests document the compat fallback and guard it for as long as it lives.
2. **Inject**: add optional explicit time parameters without changing defaults —
   - `Planner(..., today: str | date | None = None, *, now: date | datetime | None = None)`: resolution order `today` (parsed) → `now` (date part) → allowlisted legacy `datetime.now()` fallback. `replan(..., now: datetime | date | None)` already exists: extend to accept `date` (midnight semantics, documented) and keep `None` = allowlisted legacy fallback.
   - Accept `date` objects for `today` in `scoring.parse_day` (currently `str`-only; extend totalistically: `date` → itself, `datetime` → `.date()`, garbage → `None` → fallback chain). This is the smallest change that lets callers pass real date objects toward a future `PlanningRequest.now`.
   - Migrate production callers to always pass explicit values (`screens/plan.py::scheduled_for_today`, `plan_decisions`, Buongiorno confirm path, CLI — CLI already does). After migration, the fallback is dead in production but alive for compat (exactly the §6.0 end-state).
3. **Allowlist (not remove)**: add an arch test asserting **no new** `datetime.now()` / `date.today()` call sites appear in `src/planner/` beyond the two documented legacy lines (with comments pointing at the later removal phase). Do NOT make `today` required in Phase 1 — that breaks `plan_day()` compat and every test/screenshot script that omits it; required-`now` belongs to the later public-contract phase.

Determinism tests to add: same-input-same-output across repeated `propose()`/`schedule()`/`replan()` calls (already covered by fixtures — strengthen with a 200-task randomized seeded determinism test: shuffle input order, assert `to_legacy()` stable given the documented ordering keys); explicit-`now` equivalence (fallback == explicit under frozen clock); cross-midnight regression (`today` explicit while wall-clock differs — planner must follow `today`, never the clock).

---

## 7. Domain dependency strategy

| # | Dependency | Classification | Phase 1 treatment |
|---|---|---|---|
| D1 | `capacity → domain.calibrated_estimate` + `CAL_CLAMP_MIN/MAX` (`capacity.py:15,48`) | **Genuinely domain-level** (estimation math; single source of truth by design; `domain` is pure, no I/O — conceptual coupling, not effect) | **Keep, wrap**: keep delegation (no second algorithm). Isolate to one seam: `capacity.estimate` + `normalize_factor` remain the only touchpoints; add a comment + arch-note marking them deliberate until Phase 5 redesigns estimation (per engine doc §16: "calibration source of truth stays in `domain` until Phase 5"). No move, no copy. |
| D2 | `calibration.factor_for → domain.calibration_factor` (`calibration.py:52-53`) | **Application/service-level** (history-derived auto-calibration; callers can and should inject) | **Keep as compat path, make injection the primary path**: `Planner` already accepts explicit `factor`. Phase 1 adds the optional `factor` seam to `replan()` **via the 4a→4b→4c sequence (§10.1)** — default `None` preserves current behavior exactly; no caller is migrated to explicit factor in Phase 1 (see evidence below). Document `factor=None` = "auto (compat)". |
| D3 | `calibration.calibration_summary → execution_stats/execution_calibration_factor/execution_confidence/last_observation_at` (`calibration.py:56-66`) | **Compatibility/reporting-level, outside the core** (history aggregation for UI display; M2 decision: summary derived on-demand, never persisted) | **Defer-or-demote**: do NOT move into the core. Phase 1: mark as non-core integration helper (docstring + keep re-export for UI compat); candidate for relocation to `domain` or an app-side helper in Phase 2. Zero behavior change. |
| D4 | `decisions → domain.execution_confidence` (`decisions.py:27,84`) | **Accidental coupling** (3-level threshold map `LOW<10/MED<30/HIGH`; decisions already receives `sample_count` from the caller — the import exists only to translate int→label) | **Wrap with injection**: `decide(..., sample_count=None, confidence=None)` — if `confidence` (string) passed explicitly it wins; else derive via an injected-or-default resolver. Default resolver stays `domain.execution_confidence` in Phase 1 (behavior identical), but the import moves behind a module-level `_confidence_resolver` seam (settable in tests) OR the 6-line threshold is duplicated with a lock-step comment (like `POMO_MINUTES`/`POMO_HOURS` precedent in `domain.py:367-371`). Prefer the seam over duplication (thresholds already changed once — M2; two copies drift). |
| D5 | `scoring/capacity → models.Priority/_due_date_part` | **Compatibility-level** (enum + 4-line string helper from the storage model) | **Remove via §5 adapter**: normalize at `todo_to_task` edge (`priority` → plain `"alta"/…"` string, `due` → date-part string); planner-internal `PRIO_SCORES` keyed by string; local `_date_part` helper. `models.py` untouched. |
| D6 | `domain.apply_replan` (referenced in `replan.py` docstring only; called by `screens/plan.py:1270`, `cli.py:126`) | **Correctly separated** (commit path, application-owned) | **Keep**: no import from planner to `domain.apply_replan` today — verify with a new arch assertion (see §13). The plan must not move persistence/effects into the planner. |

Rule applied throughout: avoid gratuitous relocation — only D4/D5 change code shape in Phase 1, and only at seams; D1/D2/D3 are documented-as-deliberate. Consistent with §5.0: none of these treatments adds domain semantics to `TaskView`.

Evidence grounding D2's caution: **no production caller passes explicit `factor=` today** — `Planner(` call sites (`screens/plan.py:224`, `:1377`, `screens/views.py:1192`) all omit `factor` (auto path); the only `factor=` occurrence in production code is `screens/plan.py:241`, which builds the app-side `DayPlan` re-wrap from `plan.factor` (read-out, not injection). Hence the replan seam is behavior-neutral while callers keep passing `None` — and the plan treats any future caller migration as a separate, classified decision (§10.1, step 4c), not part of this refactor.

---

## 8. Model/contract strategy

| Type | Owner after Phase 1 | Rationale |
|---|---|---|
| `TodoItem`, `Priority`, `TaskExecution`, storage/config/day_window dicts | **Application-owned** (unchanged) | Persistence/UI vocabulary; planner must not import them in core paths after Phase 1 (adapter edge only). |
| `TaskView` (new, frozen) + `todo_to_task()` | **Planner-owned projection** (new; status per §5.0) | Minimal anti-corruption projection solving Known conflict #3 without speculative modeling. Lives in `src/planner/models.py`. Not the future `Task`; Phase 2 decides the canonical model independently. |
| `DayPlan`, `PlanItem`, `ScheduledDayPlan`, `ScheduledItem`, `TimeWindow`, `FixedEvent`, `ExecutionFeedback`, `PlanningDecision`, `ReplanProposal`/`ReplanMove` | **Planner-owned** (already; unchanged fields) | Frozen, pure, tested contracts. No field renames/additions in Phase 1 (renames ripple to screens/CLI/tests for zero architectural gain). |
| `PlannerInput` (new, **internal only**, e.g. `_PlannerInput` or a private normalization result) | **Planner-internal** | Smallest viable step toward `PlanningRequest`: resolved `day: date` + `tuple[TaskView]` (eligible incl. skipped-flagged) + `capacity_pomo` + `factor` + `today_s`. NOT exported from `__init__`, NOT part of any stability promise. Proves the "single input shape" idea without freezing the wrong contract. Built from `TaskView`s, never directly from `TodoItem`s. |
| `PlanningRequest` / `PlanningResult` (names) | **Phase 2+** (not implemented) | Engine doc §6 TARGET. Phase 1 maps current inputs/outputs onto the concept (§5 of this plan) and leaves the names unused so Phase 2 can define them from a stable model. |
| `planner.plan(request)` / `planner.replan(request)` | **Phase 7** (not implemented, not stubbed) | No stubs, no `NotImplementedError` placeholders — stubs freeze signatures prematurely and rot. |
| `calibration_summary` dict | **Integration helper** (demoted, see D3) | Stays importable, documented as non-core. |
| Reason keys (`explain.*`), story keys (`narrative.*`) | **Frozen shared vocabulary** (unchanged) | UI + i18n depend on literals; `explain.py` stays the single source of truth. |

---

## 9. Planning/scheduling boundary

- **Definitions (kept)**: *planning* = which tasks enter the day and why (eligibility → merit → capacity → `DayPlan` with reasons); *scheduling* = where placed in time (first-fit of `plan.planned` into explicit availability avoiding busy → `ScheduledDayPlan`). Evidence: `service.py` docstring (pipeline), `scheduler.py` docstring ("niente secondo scoring, niente ricalcolo delle stime"), `test_planner_contract.py::test_schedule_thin_wrapper_e_invarianti` + `test_pipeline_usa_tutti_gli_stadi`.
- **Soundness verdict**: the separation is architecturally sound and must remain. Data crossing the boundary: `tuple[PlanItem]` (id/score/reasons/estimate/mandatory — never whole todos) + `availability`/`busy` as `TimeWindow`s. Scheduling never re-scores, never invents hours, never touches cut/skipped (mandatory-without-slot = structural `unscheduled`, reason-free by design).
- **Is scheduling part of the core?** Yes — pure temporal placement over the planner's own models with no app knowledge is core engine behavior (engine doc §§4, 9 place scheduling inside the core; availability is explicit input, not app state).
- **Phase 1 change**: none to the boundary shape. Only consequences of §§5–6: scheduler continues to consume `PlanItem.estimate_pomo` (via `TaskView`-derived items — same ints), and `Planner.schedule` gains input tolerance parity (accept `date`-derived day bounds already do; no signature change). Add one invariant test: scheduler output depends only on (`plan`, `availability`, `busy`) — same triple, same slots, regardless of wall-clock (freeze clock, vary wall-clock, assert equal).

---

## 10. Replanning boundary

- **Current separation (verified, appropriate)**: `replan()` (`replan.py`, pure) reuses `propose()` + `schedule()` with availability clipped to `[now, end]` (`_clip_future`), derives kept/moved/dropped/added by diffing against confirmed `planned_for` + optional `current` slots, reasons from `decide()`/`primary_reason()`; commit is `domain.apply_replan` (mutates `planned_for`/`plan_skip` on passed todos only) + `store.commit()` by the caller (`screens/plan.py:1270`, `cli.py::_cli_replan --apply`). CLI preview is read-only by default (hash-verified in tests).
- **Phase 1 changes**, strictly sequenced per §10.1:
  1. `replan()` accepts `TaskView` or `TodoItem` (via the §5 adapter; `current_ids` scan and `decide()` evidence use the normalized projection).
  2. Optional `factor` seam introduced **only** via steps 4a→4b→4c (characterize → seam → classify); default `None` preserves current behavior exactly; no caller migrated to explicit factor in Phase 1.
  3. `now` accepts `date` as well as `datetime` (midnight semantics, documented); `None` keeps the allowlisted legacy fallback per §6.
- **Must not**: move `apply_replan` into planner, persist slots, auto-commit, or add rescheduling heuristics. Principle preserved: *planner proposes; application/domain integration commits.* New arch test pins the direction: `src/planner/*.py` must not import `apply_replan`, `store`, `commit`, `save_` (see §13).

### 10.1 Replan factor: characterization → seam → classification (binding sequence)

Repository evidence (verified): `replan()` internally constructs `Planner(todos, today=today, hours=hours)` **without** `factor` (`replan.py:105`), so the internal path always auto-calibrates. Production callers of `replan()` are exactly two — `ReplanPreviewScreen._proposal` (`screens/plan.py:1170-1178`) and CLI `_cli_replan` (`cli.py:91`) — and **neither passes (nor holds) an explicit factor**: all `Planner(` call sites omit `factor=` (auto path); the screen's `scheduled_for_today` likewise proposes with auto factor, so today's replan preview and the day-plan it diffs against share the same auto factor computed over the same todo list. A calibrated factor is therefore *computable* at each caller (same `factor_for(todos)` call) but *not currently available as a value* at either call site (nothing retains `plan.factor` across the `_proposal` boundary).

Because threading `factor` may change observable planning behavior (capacity selection shifts under explicit factors), it is **not** treated as a behavior-neutral refactor step. Binding sequence:

- **Step 4a — Characterize current replan factor behavior (tests first, no production change)**: add a characterization test proving that today `replan(todos, ...)` ≡ `Planner(todos, today, hours).propose()`-with-auto-factor on the fixture matrix (i.e. the internal auto factor equals the factor any caller would compute via `calibration.factor_for` over the same list); record the two production callers and the finding that neither holds an explicit factor; record that no caller expects the factor to be ignored (nothing passes one to ignore).
- **Step 4b — Introduce the factor seam (compat default)**: add optional `replan(..., factor=None)` threaded to `Planner(..., factor=factor)`; `None` reproduces the characterized behavior exactly (proven by re-running the 4a test unmodified plus a new explicit-factor test showing the threaded path equals a direct `Planner(factor=f)` propose-then-schedule construction).
- **Step 4c — Classify the behavioral change (explicit review verdict)**: the implementation/review process records one of: (i) **pure refactoring** — if 4a proves auto≡auto and no caller passes explicit factor (the expected outcome given current evidence: threading with default `None` changes no observable output, and the new explicit path is opt-in-only, unused in Phase 1); (ii) **bug fix** — if 4a reveals the internal auto factor can diverge from the caller's context (e.g. caller filters todos before proposing but replan sees the full list, or vice versa); (iii) **deliberate behavior correction** — if reviewers decide a caller *should* pass its retained factor. Cases (ii)/(iii) require a separate, explicitly labeled commit and changelog/AGENTS.md evaluation per repo convention; case (i) stays inside the refactor. **No caller is migrated to pass explicit factor in Phase 1 regardless of outcome** — that migration is a future decision with its own behavioral review.

---

## 11. Explainability boundary

- **Classification (verified)**: `decisions.py` = **planner-domain concept** (projection of `DayPlan` sections → decision states + structured evidence + `primary_reason`; no UI text, no scoring rerun — D4 aside, pure). `narrative.py` = **presentation-adjacent but correctly placed** (deterministic key-selection over decision+reasons+evidence; returns `(key, params)` for `T()` in views; never imports `lang/screens/app` — purity comment at `narrative.py:14`; covered by `test_narrative.py` without Textual).
- **Minimal Phase 1 change**: none to selection rules or keys. Only D4 (confidence injection, §7) touches `decisions.py`, and it preserves outputs exactly. Optionally (only if free): document in `decisions.py` docstring which evidence fields are stable (`due/priority/overdue/score/rank/rank_of/estimate_pomo/estimate_minutes/mandatory/capacity_pomo/planned_pomo` + `slot_start/slot_end` after refine) as the proto-diagnostic surface for Phase 6 — documentation only, no new fields (new fields would ripple to Why-card tests for no Phase-1 gain; and per §5.0, no new domain semantics ride along on evidence types either).
- **Not in Phase 1**: structured `PlanningDiagnostic`, rejected-alternative records, plan-level diagnostics aggregation, any rewrite of story templates.

---

## 12. Feedback/calibration boundary

- **Feedback (`feedback.py`)**: pure derivation `scheduled + todos → tuple[ExecutionFeedback]`, same order as `plan.planned`. **Stays inside the core** as the observation mechanism (it reads only planner models + the §5 projection; after Phase 1 it takes `TaskView`s, no `TodoItem`). Deterministic: yes, fully (no clock, no history, no I/O). No calibration, no rescheduling inside — verified, keep.
- **Calibration math** (median, min-samples=5, clamp 0.5–3.0): **stays in `domain`** (D1/D2). It depends on persisted history (completed todos / executions file) and is shared with Stats/Detail display paths (`predicted_minutes`, `calibration_summary` consumers in screens) — moving it now would fork the source of truth. `planner/calibration.py` remains the thin boundary (`observe`/`observe_all` pure pair-derivation + `factor_for` delegation).
- **What stays outside the pure core**: history access (loading todos/executions), `calibration_summary` aggregation (D3, UI-facing), any auto-update of estimates (never — `plan_calibrated` is reason-only by design), actual-time collection (`ActualScreen`, pomodoro crediting).
- **No algorithm redesign** in Phase 1 (per task brief): thresholds, `POMO_HOURS`/`POMO_MINUTES` lock-step, `or 1` missing-estimate fallback (convention documented in `plan.py`/`domain.calibrated_estimate` docstrings) all frozen.

---

## 13. Test strategy

### 13.1 Existing protection (retain unchanged unless noted)

| Area | Files |
|---|---|
| Legacy equivalence (40+ scenarios, zero-divergence) | `test_planner.py`, `test_planner_fixtures.py` (10 frozen scenarios), `test_property_planner.py` |
| Contract/pipeline/invariants | `test_planner_contract.py`, `test_planner_dayplan.py`, `test_planner_invariants.py` |
| Stages | `test_planner_scoring.py`, `test_planner_constraints.py`, `test_planner_capacity.py`, `test_planner_explain.py` |
| Scheduling determinism | `test_scheduler.py`, `test_phase7_events.py`, `test_plan_slots.py` |
| Decisions/narrative/Why | `test_planner_decisions.py`, `test_narrative.py`, `test_detail_why.py` |
| Replan (+CLI/UI) | `test_replan.py`, `test_replan_ui.py`, `test_replan_cli.py` |
| Feedback/calibration/estimation | `test_feedback.py`, `test_calibration.py`, `test_task_execution.py`, `test_execution_stats.py`, `test_plan.py` (factor/cut cases) |
| Architecture guards | `test_arch.py` (6 tests), `test_domain.py::test_arch_purezza_no_import_app_ui` |
| Perf baseline (anti-regression tripwire) | `test_planner_perf.py` (~0.3/0.6/2.9/5.4ms @ 50/100/500/1000 tasks, wide CI thresholds) |
| UI consumers | `test_plan_ui.py`, `test_plan_operate.py`, `test_day_window.py`, `test_execution.py`, `test_ui_regression.py` |

### 13.2 Test matrix for Phase 1

| # | Test | Type | Disposition |
|---|---|---|---|
| T1 | Fixture-matrix differential: `TodoItem` input vs pre-converted `TaskView` input → identical `DayPlan` (`==`) and `to_legacy()` across ALL `test_planner_fixtures.py` + `test_planner.py` scenarios | characterization (new, **write first**, before §5 code) | Added |
| T2 | `todo_to_task` totality: malformed todos (id None, garbage dates, bad types, missing attrs) → safe defaults, never raises; round-trip spot checks; **projection discipline**: output contains only the §5.1 field set (assert exact key/field list — guards against future-semantics creep per §5.0) | unit (new) | Added |
| T3 | `datetime.now` fallback characterization: frozen clock — `Planner(todos)` == `Planner(todos, today=frozen)`; `replan(now=None)` == `replan(now=frozen)`. **Kept permanently** as the compat-fallback contract (not a TODO to delete in Phase 1) | characterization (new, **write first**, retained) | Added |
| T4 | Explicit-`now` precedence: `today` beats `now` beats fallback; `date`/`datetime`/garbage-string handling in `parse_day` extension; production-caller audit test (all production `Planner(`/`replan(` call sites pass explicit values — allowlist asserted, fallback paths exercised only by compat tests) | unit (new) | Added |
| T5 | Determinism: seeded 200-task shuffle → stable `to_legacy()`; scheduler wall-clock independence (vary frozen clock, same triple → same slots); replan determinism with explicit `now` | strengthened (new test, existing files untouched) | Added |
| T6 | D4 confidence injection: `decide(..., confidence="HIGH")` wins; default path delegates (mock resolver) → identical to today; invalid `sample_count` → `None` (existing behavior) | unit (new) | Added |
| T7a | **(Step 4a)** Replan factor characterization: `replan(todos, ...)` output ≡ internal-auto-factor construction on the fixture matrix; caller inventory recorded (2 production callers, neither holds explicit factor); no caller expects factor-ignored semantics | characterization (new, **before** any replan production change) | Added |
| T7b | **(Step 4b)** Factor seam: default `None` reproduces T7a exactly (T7a re-run unmodified); explicit `factor=f` equals direct `Planner(factor=f)` propose-then-schedule construction | unit (new, after seam) | Added |
| T7c | **(Step 4c)** Classification record: review verdict (pure refactoring / bug fix / deliberate correction) captured in the commit message; if (ii)/(iii), separate labeled commit + convention-gated changelog/AGENTS.md evaluation | process gate | Added |
| T8 | Arch guards extended: (a) no `TodoItem`/`Priority`/`_due_date_part` imports in `src/planner/{scoring,capacity,constraints,decisions,feedback}.py` post-migration (adapter module exempted); (b) no `datetime.now()`/`date.today()` in `src/planner/` **beyond the two documented allowlisted fallback lines** (allowlist by file:line + comment reference, not a blanket exemption); (c) no `apply_replan`/`store`/`commit`/`save_` imports in `src/planner/`; (d) `__init__` export list unchanged except additive `TaskView`/`todo_to_task` (compat) | architecture (extend `test_arch.py` + purity test) | Strengthened |
| T9 | Compat: `plan_day()` output unchanged on full matrix; `DayPlan`/`ScheduledDayPlan`/`ReplanProposal` field layout unchanged (constructor/kwarg smoke); `__all__` stable per T8(d) | regression (new thin test) | Added |
| T10 | Perf: `test_planner_perf.py` thresholds still pass (adapter overhead must be noise-level) | regression | Retained unchanged |
| T11 | UI consumer suite (`test_plan_ui`, `test_plan_operate`, `test_day_window`, `test_detail_why`, `test_replan_ui/cli`, `test_execution`) | regression | Retained unchanged (must pass unmodified — proves caller transparency) |

Convert T1/T3/T7a into permanent characterization tests (kept after migration as the equivalence proof; T3/T7a specifically guard the compat fallback and the auto-factor behavior for as long as they live). Do not weaken any existing guard; if a guard blocks the plan (e.g. purity test on a new adapter import of `TodoItem` for conversion), exempt **only** the adapter module by path with a comment, never broaden the exemption.

---

## 14. Migration sequence

Ordered, each independently reviewable and testable (target: one commit per step; each step = code + tests green + `ruff check` + `ruff format --check` + `mypy src/` + full `pytest`):

1. **Step 0 — Characterization first**: add T1 (adapter-agnostic: dual-input harness with a temporary inline converter in the test), T3, T7a-skeleton, T9-skeleton. No production change. Proves the "before" picture (including the replan auto-factor baseline for §10.1).
2. **Step 1 — `TaskView` projection + `todo_to_task` (additive only)**: new frozen projection type + converter in `src/planner/models.py`, documented per §5.0 (docstring states projection/compat status and the no-future-semantics rule); T2 (incl. exact-field-set assertion). No consumer yet — zero behavior change by construction.
3. **Step 2 — Core consumes the projection (adapter at edges)**: `scoring`/`constraints`/`capacity`/`feedback`/`decisions._evidence`/`replan` scan operate on `TaskView`; public signatures normalize once via `todo_to_task`; `Priority`/`_due_date_part` imports removed from core (local string helpers). Gate: T1 differential green + full suite green. (Largest step; split per-module commits if preferred: scoring → constraints → capacity → feedback/decisions/replan.) No new `TaskView` fields may be added in this step (enforced by T2's exact-field assertion).
4. **Step 3 — Explicit time (inject, keep fallback)**: `parse_day` accepts `date`/`datetime`; `Planner(..., now=...)` added with explicit-first resolution (`today` → `now` → allowlisted legacy fallback); `replan(now=)` accepts `date`; T4/T5. Production callers migrated to explicit values in the same step (screens/CLI diffs are one-line pass-throughs — caller-side `datetime.now()` remains correct layering). Fallback lines stay, commented as allowlisted compat (removal explicitly deferred).
5. **Step 4a — Replan factor characterization**: T7a green on unmodified production code; caller inventory + auto≡auto finding recorded (in test comments/commit message). No production change.
6. **Step 4b — Factor seam (compat default)**: optional `replan(..., factor=None)` threaded to `Planner(..., factor=factor)`; T7b. Default path reproduces T7a exactly. No caller passes explicit factor (no caller migration in Phase 1).
7. **Step 4c — Classification verdict**: reviewer records (i)/(ii)/(iii) per §10.1 in the commit message. If (ii)/(iii): separate labeled commit; changelog/AGENTS.md evaluated against repo convention (conditional, see step 9). If (i) (expected): the seam lands as refactor + opt-in capability.
8. **Step 5 — Internal `PlannerInput` normalization**: private resolution (`day`, `today_s`, `capacity_pomo`, `factor`, normalized projections) factored out of `Planner.propose` body; `propose()` output identical (T1/T9 gate). Not exported. Built from `TaskView`s only. This is the structural enabler for a future `PlanningRequest` — deliberately private.
9. **Step 6 — Guardrails + docs**: extend `test_arch.py`/purity test (T8 with the two-line time-fallback allowlist + adapter-only `TodoItem` exemption); docstring updates (`service.py` factor/`now`/fallback-allowlist semantics, `calibration.py` non-core note for `calibration_summary`, `decisions.py` evidence-stability note, `models.py` `TaskView` projection status). AGENTS.md sprint-log entry and `docs/planner-engine.md` Phase-1 status line **only if the repository's documented contribution/sprint-log convention requires recording this milestone** (conditional); CHANGELOG likewise conditional (invisible refactor → default untouched). ADR-001 untouched.
10. **Step 7 — Perf + full gate**: `test_planner_perf.py`, full `pytest` + `ruff check` + `ruff format --check` + `mypy src/` on clean tree; reviewer subagent (`@reviewer` per AGENTS.md §4) before any release commit. No version bump (invisible change — precedent: Phases 1–10, M2).

Rollback story: Steps 1–2 are purely additive + edge-normalization (revert = delete adapter calls); Steps 3–4b keep legacy defaults (revert = drop optional params); Step 4c's verdict determines whether its commit is revert-safe (i) or needs a paired revert (ii/iii). No data migration, no config change, no storage format change at any step.

---

## 15. Compatibility strategy

- **Callers keep working**: `Planner(todos, today=..., hours=..., factor=...)`, `Planner.schedule(plan, avail, busy)`, `replan(...)`, `feedback(...)`, `decide(...)`, `plan_day(...)`, `to_legacy()` — all signatures backward compatible (new params optional-only, defaults reproduce legacy behavior). `screens/plan.py::scheduled_for_today`, `views.py::plan_decisions`, CLI replan need at most one-line explicit-time pass-throughs; **no caller passes explicit `factor` in Phase 1** (§10.1). UI test suite must pass unmodified (§13 T11) as the proof.
- **Types**: `TaskView` is additive and projection-scoped; `TodoItem` input remains accepted indefinitely (adapter is the permanent compat path, not a temporary shim — same pattern as `plan.py` wrapper, which stays tests-only). `TaskView` must never leak into storage, config, or UI state — it exists only between `todo_to_task()` and the core.
- **Time**: omitted `today`/`now` keep today's wall-clock behavior via the two allowlisted fallbacks (T3 pins it); explicit values take precedence. Ad-hoc scripts and screenshot harnesses that omit `today` continue to work unchanged.
- **Exports**: `src/planner/__init__.py::__all__` gains only `TaskView`/`todo_to_task` (pure addition); never remove `factor_for`/`calibration_summary` while screens import them.
- **Reason keys / i18n**: frozen (`explain.py` + `STRINGS` it/en parity untouched). `DayPlan` field layout frozen.
- **Debt acknowledged, not fixed here**: CLI's lazy import of `screens.plan.day_window_parts`/`scheduled_for_today` (app-layer parsing inside CLI path) stays; `day_window` config shape stays; `scheduled_for_today`'s confirmed-set re-wrap stays app-side.

---

## 16. Risks

| Risk | Likelihood / impact | Mitigation in this plan |
|---|---|---|
| Hidden behavior change (ordering, rounding, fallback semantics) | Medium / high | Fixture-matrix differential (T1) + legacy equivalence suite retained; `to_legacy()` equality as the hard gate; no weight/capacity/scheduler edits permitted in Phase-1 diffs (reviewer checklist item). |
| Duplicate models (`TaskView` vs `TodoItem` drift; `TaskView` mistaken for canonical `Task`) | Medium / medium | §5.0 projection discipline + T2 exact-field assertion + *View* naming + docs; arch test pins the field list; Phase-2 canonical decision explicitly unconstrained. |
| Projection scope creep (future-semantics added "just in case") | Medium / low | §5.0 implementation rule (concrete current-algorithm justification required per field); T2 exact-field assertion fails closed on additions. |
| Compatibility complexity (optional `now`/`factor`/`confidence` params accumulate) | Low / medium | All optional, all defaulting to current behavior; T9 compat test; no required-param change until the later public-contract phase. |
| Over-abstraction (private input shape → proto-framework) | Medium / medium | `PlannerInput` stays private, minimal (5 fields), no methods, no validation framework; explicit non-goal (§17) + reviewer gate. |
| Accidental coupling (new adapter imports `TodoItem` → purity test trips) | High (certain) / low | Pre-declared narrow exemption for the adapter module only; T8 codifies it. |
| Premature public API stabilization (`TaskView` mistaken for the future `Task`) | Medium / medium | Naming + §5.0 + docs + §8 ownership table; `PlanningRequest` names reserved-unimplemented; no versioning promise. |
| Replan factor seam changes observable behavior silently | Low (evidence: auto≡auto, no explicit-factor caller) / high if wrong | **Steps 4a→4b→4c**: characterization before seam, default-`None` reproduction proof, explicit classification verdict; (ii)/(iii) outcomes get separate labeled commits, never hidden in refactor. |
| Fallback lifecyle ambiguity ("are we done if fallbacks remain?") | Medium / low | §6.0 lifecycle + revised §18: done = production explicit-time + fallbacks isolated/documented/tested; removal owned by a later phase. |
| Priority normalization subtlety (`Priority` enum vs raw strings from CSV/import paths) | Low / medium | Converter maps enum→value→lower + accepts raw strings case-insensitively; T2 covers garbage; `PRIO_SCORES` lookup falls back to MEDIUM weight exactly as today (`.get(todo.priority, MEDIUM)` semantics preserved via normalized key). |
| `due` with `HH:MM` suffix / odd formats | Low / medium | Date-part split happens once in the adapter (same `_due_date_part` semantics, copied); decisions `overdue` flag uses `due[:10] < day_s` — identical expression on the normalized string. |
| Perf regression perception | Low / low | Adapter is one linear pass of attribute reads; T10 tripwire with wide thresholds. |

---

## 17. Explicit non-goals

Phase 1 must NOT implement:

- no REST; no MCP; no external consumer integration; no independent package (ADR-001 stays valid — re-evaluation is Phase 8 only);
- no timezone/DST engine (naive wall-time convention untouched);
- no removal of the legacy `today`/`now` compat fallbacks (deferred to the later temporal/public-contract phase);
- no complete constraint framework (hard/soft stay implicit-as-today; no `Constraint`/`Preference` types);
- no full diagnostics engine (no `PlanningDiagnostic`, no new evidence fields, no rejected-alternative records);
- no canonical `Task` domain model and no future-semantics growth of `TaskView` (§5.0 rule);
- no `PlanningRequest` / `PlanningResult` public types; no `planner.plan(request)` / `planner.replan(request)` (not even stubs);
- no calibration algorithm change, no estimate auto-rewrite, no rescheduling heuristics; no caller migration to explicit replan factor (deferred by §10.1);
- no large planner rewrite, no module reorganization for aesthetics (new code lives in existing files except the one adapter home);
- no persistence/application side effects in the planner (`apply_replan`, store, config, Outlook remain outside);
- no version bump / release mechanics beyond repo convention (invisible change).

---

## 18. Definition of done

Phase 1 is complete iff **all** hold (objectively checkable):

1. **Production planner execution is explicit-time**: every production `Planner(` / `replan(` call site passes explicit `today`/`now` (asserted by T4-audit test); planner internals resolve explicit-first (`today` → `now` → fallback). The two legacy wall-clock fallbacks (`service.py:40`, `replan.py:104`) **remain** as allowlisted, commented, characterization-tested compat paths (asserted by T3 + T8-allowlist test) — their continued existence does not block completion; their removal belongs to the later temporal/public-contract phase.
2. No module in `src/planner/` except the designated adapter imports `TodoItem`, `Priority`, or `models` helpers (asserted by T8-arch test); public `Planner`/`replan`/`feedback`/`decide` accept both `TodoItem` and `TaskView` inputs with identical outputs (T1). `TaskView` carries exactly the §5.1 field set (T2 exact-field assertion) and is documented as a projection per §5.0.
3. `domain` imports from planner are limited to the documented seams: `capacity→{calibrated_estimate, CAL_CLAMP_*}`, `calibration→{calibration_factor, execution_* (summary only)}`, `decisions→confidence resolver (default delegates)` (asserted by T8-arch test + §7 table in code comments).
4. `replan()` accepts optional `factor` (default `None` reproduces characterized behavior — T7a re-run green) and `now` accepts `date`; `decide()` accepts optional `confidence`; `parse_day` accepts `date`/`datetime` (T4/T6/T7b green). The §10.1 classification verdict is recorded: (i) refactor, or (ii)/(iii) in a separate labeled commit. No caller passes explicit replan factor in Phase 1.
5. Full gate green: `pytest` (incl. all retained suites unmodified), `ruff check`, `ruff format --check`, `mypy src/`; `test_planner_perf.py` within thresholds; `@reviewer` sign-off recorded.
6. AGENTS.md / CHANGELOG / `docs/planner-engine.md` status updates **only if the repository's documented contribution/sprint-log convention requires recording this milestone** (conditional; invisible refactor → default is docs-untouched except code comments/docstrings); ADR-001 byte-identical.
7. No Phase 2–8 artifact present: no `PlanningRequest`/`PlanningResult`/`plan(request)` names in `src/`, no canonical `Task` model, no new dependencies in `pyproject.toml`/`requirements.txt`, no timezone code, no package scaffolding, no fallback removal.

---

## 19. Recommended implementation boundaries

Favor incremental, reversible commits (one step of §14 per commit; squash nothing until green):

- **PR/commit A — characterization**: Step 0 tests only (T1-harness, T3, T7a-skeleton, T9-skeleton). Review: "do these tests fail if behavior changes?" Easy revert.
- **PR/commit B — `TaskView` projection, additive**: Step 1 (new projection type + converter + T2 incl. exact-field assertion, §5.0 docstring). Review: field list vs §5.1 table; projection language present. Zero production impact.
- **PR/commit C — core migration** (possibly C1..C3 per module): Step 2. Review per module with T1 differential output attached. Biggest review surface — keep diffs mechanical; reject any `TaskView` field addition here (T2 guards).
- **PR/commit D — explicit time**: Step 3 (parse_day + `now`/`today` params + caller one-liners + T4/T5; fallbacks retained with allowlist comments). Review: fallback chain + caller coverage checklist (every production call site explicit — evidence: screens/plan.py:224/:1170, views.py:1192, cli.py:91).
- **PR/commit E1 — factor characterization**: Step 4a (T7a, no production change). Review: auto≡auto finding + 2-caller inventory.
- **PR/commit E2 — factor seam**: Step 4b (optional param + threading + T7b; T7a re-run). Review: default-path identity proof.
- **PR/commit E3 — classification verdict** (only if (ii)/(iii); if (i), fold the one-line verdict into E2's message): Step 4c. Review: behavioral classification + convention-gated docs decision.
- **PR/commit F — internal normalization + guards + docs**: Steps 5–6 (private input shape from projections only, T8 incl. time-fallback allowlist, docstrings, conditional AGENTS.md/engine-doc lines). Review: "is anything public that shouldn't be?"
- **Gate G**: Step 7 full verification + reviewer sign-off. No release commit needed (no bump per repo precedent for invisible changes).

Each commit message in English, small scope, referencing this plan's step (e.g. `refactor(planner): phase1 step C1 — scoring consumes TaskView projection, legacy equivalence green`).

---

## Appendix — evidence index (verification checklist per task brief)

1. **Repo state verified**: `src/planner/` (12 modules) read in full; `models.py`, `domain.py` (defs listed), `plan.py`, `screens/plan.py` (builder `scheduled_for_today:190`, replan call `1170-1178`, `Planner(` sites `:224`/`:1377`, `factor=` read-out `:241`), `screens/views.py` (`plan_decisions:1179`, `Planner(` `:1192`), `cli.py::_cli_replan` (replan call `:91`, commit `:126`), `integrations/outlook.py` (`FixedEvent` import — planner model reused as pure data, correct direction).
2. **APIs verified**: signatures quoted from source (§3 table with file:line).
3. **TodoItem/domain deps verified**: field-use table (§5.1) from grep + line reads; domain seam table (§7) with exact import lines (D1 `capacity.py:15`, D2 `calibration.py:52`, D3 `calibration.py:56-66`, D4 `decisions.py:27`, D5 `scoring.py:11`/`capacity.py:16`).
4. **Arch tests verified**: `test_arch.py` (6 tests quoted), `test_domain.py:199` purity guard quoted.
5. **ADR-001**: read (10 lines); plan changes nothing in it — packaging re-evaluation stays Phase 8.
6. **No future capability described as implemented**: every forward-looking item labeled `PHASE 1 TARGET` / `Phase 2+` / `FUTURE` / `Later phase`; CURRENT/TARGET/FUTURE markings mirror `docs/planner-engine.md` convention.
7. **Time sources**: exactly two in planner (`service.py:40`, `replan.py:104`) — confirmed by repo-wide `datetime.now()` scan; all other hits are callers/tests/storage (out of scope, listed in §6.1). Both retained as allowlisted compat per §6.0 (removal deferred, not required for completion).
8. **Replan factor evidence**: internal `Planner(todos, today, hours)` without factor (`replan.py:105`); exactly two production `replan(` callers (screens/plan.py:1170, cli.py:91), neither holding explicit factor; all production `Planner(` sites omit `factor=` (screens/plan.py:224/:1377, views.py:1192). Basis for the 4a→4b→4c sequence and the expected (i)-classification.

---

## Refinements applied (vs baseline plan)

1. **TaskView explicitly treated as a projection/compatibility model**: added binding §5.0 (projection pipeline diagram, anti-corruption status, no-future-semantics implementation rule, Phase-2 independence) and propagated the language through §§4, 5.2, 7, 8, 10, 13 (T2 exact-field assertion), 14 (steps 1–2, 5), 15 (non-leak rule), 16 (creep + mistaken-identity risks), 17–18.
2. **Explicit-time lifecycle clarified**: added binding §6.0 (Phase-1 explicit-production + isolated compat fallback vs later-phase removal); reworked §6.1–6.2 (fallbacks retained-allowlisted, not removed), §13 (T3/T8-allowlist as permanent compat contracts, T4 caller audit), §14 (step 3 keeps fallbacks; step 6 allowlists them), §18 item 1 redefined as production-explicit-time, §17 (fallback removal listed as non-goal).
3. **Replan factor separated into characterization → seam → behavioral classification**: added binding §10.1 (4a characterize / 4b seam / 4c classify with (i)/(ii)/(iii) verdict rule and no-caller-migration constraint) grounded in caller evidence (2 replan callers, zero explicit-factor sites); split tests T7→T7a/T7b/T7c; inserted steps 4a/4b/4c (commits E1/E2/E3) into §14/§19; updated §§7 (D2), 10, 15, 16 (silent-change risk), 18 item 4.
4. **AGENTS.md / CHANGELOG updates remain conditional on repository convention**: §14 step 6/9, §18 item 6, and §10.1-4c state the conditional explicitly (invisible refactor → default untouched); no automatic modification required for completion.

> No repository files were modified (plan-phase work; implementation starts at Step 0).
