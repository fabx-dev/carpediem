# CarpeDiem Planner Engine — Evolutionary Project

> Status: architectural declaration (2026-09-30). This document states the
> future direction of the Planner Engine. It changes no code, no API, no
> behavior. Every capability below is explicitly labelled:
> `CURRENT` = implemented and tested, `TARGET` = intended evolution,
> `FUTURE` = possible only after the target is stable.
> Related: `docs/adr-001-planner-boundary.md` (unchanged, still valid),
> `AGENTS.md` §9 (roadmap Phases 0–10, already done).

## 1. Vision

**`CURRENT`**: CarpeDiem already owns a working planner, integrated in the
application as an explicit boundary (`src/planner/`), consumed by the TUI.

**`TARGET`**: the planner progressively becomes the computational core of
CarpeDiem — an advanced temporal planning engine that is deterministic,
explainable, testable, and potentially reusable by external applications.

```text
                         ┌────────────────────┐
                         │   CarpeDiem TUI    │
                         └─────────┬──────────┘
                                   │
                         ┌─────────▼──────────┐
                         │ Application Layer  │
                         └─────────┬──────────┘
                                   │
                                   ▼
              ╔════════════════════════════════════╗
              ║       CARPEDIEM PLANNER ENGINE     ║
              ║                                    ║
              ║  Temporal Planning                 ║
              ║  Constraints                       ║
              ║  Scheduling                        ║
              ║  Scoring                           ║
              ║  Capacity                          ║
              ║  Replanning                        ║
              ║  Estimation                        ║
              ║  Calibration                       ║
              ║  Explainability                    ║
              ╚══════════════════╤═════════════════╝
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                 Python        CLI/API     External
                   API                      clients
```

The fundamental principle:

> **CarpeDiem must not be the planner. CarpeDiem must be an application
> that uses the Planner Engine.**

This project must NOT be read as a mere code extraction from `app.py`:
the extraction already happened (`src/planner/` exists, `app.py` is a
consumer/orchestrator of I/O, never the planning algorithm). What follows
is the evolution of that boundary into a true domain core.

## 2. Current State

**`CURRENT`** (verified against the code, 2026-09-30):

- Location: `src/planner/` — `service.py` (`Planner.propose()` /
  `Planner.schedule()`), `scoring.py`, `constraints.py`, `capacity.py`,
  `explain.py`, `scheduler.py`, `decisions.py`, `narrative.py`,
  `replan.py`, `feedback.py`, `calibration.py`, `models.py` (`DayPlan`,
  `PlanItem`, `ScheduledDayPlan`, `ScheduledItem`, `TimeWindow`,
  `FixedEvent`, `ExecutionFeedback`). Public re-exports in `__init__.py`.
- `src/plan.py` is a compatibility wrapper (`propose().to_legacy()`); it
  has no production consumer left (tests only).
- Consumers: `PlanProposalScreen` (morning briefing, the only full path
  Planner → DayPlan → Scheduler), `DailyPlanScreen`, `DetailScreen`
  (Why card), `ReplanPreviewScreen` (`G`), `WeekReviewScreen` (`W`),
  CLI `carpediem replan`. Guardrails in `tests/test_arch.py` forbid the
  UI from duplicating merit/capacity/scheduling or using the legacy
  `plan_day()` / `src.plan` path.
- Properties already achieved: deterministic pipeline (same inputs →
  same result, greedy first-fit in `scheduler.py`); pure modules (no
  I/O, no UI, no Textual, no storage, no network in `src/planner/`);
  explicit result model (`DayPlan` with `planned`/`cut`/`skipped` +
  capacity, `ScheduledDayPlan` with `scheduled`/`unscheduled`);
  read-only replanning (`ReplanProposal` with kept/moved/dropped/added,
  commit separated in `domain.apply_replan`); base explainability
  (`decisions.decide()` / `primary_reason()` + `narrative.explain_decision()`
  with `why_story_*` i18n keys, `(key, params)` reasons); calibration
  boundary (`calibration.py` → `domain.calibration_factor`, clamp
  0.5–3.0, minimum 5 samples); `FixedEvent` + `events_to_busy()` as a
  pure temporal constraint projection.

**`TARGET`** (not yet): contractual input/output, explicit temporal model,
explicit constraint framework, structured diagnostics, stable public API
(see §§6–13, 16).

**`FUTURE`** (not yet): external consumers, independent package (see
§§14–15).

## 3. Architectural Principles

**`CURRENT`** (already enforced): behavior preservation first; small
steps (`small refactor → tests → verify → next refactor`); determinism;
explainability of every significant decision (reason keys, never opaque);
user control (Planner proposes → user reviews → user confirms/modifies);
UI independence (planning logic never depends on Textual); separation
Domain → Application services → Infrastructure/UI (see `AGENTS.md` §9.5).

**`TARGET`**: two additions become binding for every future planner change:

- **Determinism with explicit `now`**: given the same input, context,
  configuration and `now`, the planner produces the same result. The
  current time must be supplied explicitly, never read implicitly from
  the operating system (see Known conflict #2).
- **Side-effect free core**: `input → planner → result`. The core must
  not depend directly on UI, TUI, CLI, filesystem, storage, database,
  Outlook, network, persistence, or application global state.

Evolution priority stays:

```text
clarity
→ correctness
→ determinism
→ testability
→ extensibility
```

never:

```text
abstraction
→ abstraction
→ abstraction
```

## 4. Planner Domain

**`CURRENT`**: the domain vocabulary exists but is planner-shaped, not
request-shaped: `PlanItem`, `DayPlan`, `TimeWindow`, `FixedEvent`,
`ScheduledItem`, `ScheduledDayPlan`, `ExecutionFeedback`,
`PlanningDecision`, `ReplanProposal`/`ReplanMove` (all frozen dataclasses,
pure, no I/O/UI/i18n).

**`TARGET`**: progressively define the engine's own domain model. Concepts
under evaluation:

```text
Task
Duration
Estimate
Deadline
Priority
CalendarEvent
Availability
TimeWindow
Constraint
Preference
Plan
PlanItem
PlanningRequest
PlanningResult
PlanningDiagnostic
```

This list is conceptual. Do NOT create all these classes now. Future
modelling must start from the real existing domain (the frozen models
above plus `TodoItem` semantics) and never from a theoretically imposed
model. In particular the engine needs its own `Task` view before any
public contract (see Known conflict #3).

## 5. Target Architecture

**`CURRENT`**: the application already consumes the boundary
(`PlanProposalScreen → Planner → DayPlan → Scheduler →
ScheduledDayPlan → UI`), and `tests/test_arch.py` forbids any second
planner in the UI.

**`TARGET`**: the Planner Engine as a domain core with contractual
input/output, consumed by CarpeDiem as its first client:

```text
                 Planner Engine
                 (domain core)
                        ↓
              PlanningRequest → PlanningResult
                        ↓
       ┌────────────────┼────────────────┐
       ↓                ↓                ↓
 PlanProposal        Agenda         Calendar / Day / Week
 (confirm)        (read-only)         (read-only views)
```

The engine must never be designed around the CarpeDiem UI. It is designed
around the general problem:

> **given a set of activities, constraints, availability and temporal
> context, build a valid and useful plan — respecting constraints,
> optimizing preferences, and explaining decisions.**

CarpeDiem is the first consumer. It must never become a conceptual
dependency of the planner.

## 6. Planning Request / Result

**`CURRENT`**: no unified request/result objects. `Planner` takes
`todos` + `today` + `hours` + `factor` separately; `schedule()` takes
`plan` + `availability` + `busy` separately. The `DayPlan` /
`ScheduledDayPlan` pair already covers the "what" (planned/cut/skipped,
scheduled/unscheduled) but not conflicts or diagnostics.

**`TARGET`**: one explicit context in, one rich result out.
Conceptually:

```text
PlanningRequest
├── tasks
├── calendar
├── availability
├── constraints
├── preferences
├── timezone
└── now
```

The planner receives everything it needs explicitly and never fetches
information from the outside on its own.

```text
PlanningResult
├── plan
├── scheduled
├── unscheduled
├── conflicts
├── diagnostics
└── explanations
```

This structure must let both CarpeDiem and any future external consumer
understand the planning outcome — including what was left out and why.

**`FUTURE`**: stabilize and version these two contracts (§16, Phase 7).

## 7. Planning Pipeline

**`CURRENT`**: the real pipeline is eligibility → merit → selection →
DayPlan → schedule → decisions (see `service.py` docstring and
`decisions.py` docstring). There is no separate normalize/validate/explain
stage with contractual output.

**`TARGET`**: tend toward this conceptual pipeline (architectural guide,
NOT a request to immediately implement a framework of classes):

```text
Input
  ↓
Normalize
  ↓
Validate
  ↓
Eligibility
  ↓
Estimate
  ↓
Score
  ↓
Capacity
  ↓
Schedule
  ↓
Validate Plan
  ↓
Explain / Diagnostics
  ↓
PlanningResult
```

Each stage must stay independently testable without the UI, and no stage
may silently compensate for another (e.g. scheduling must never re-score,
capacity must never invent availability).

## 8. Replanning

**`CURRENT`**: replanning is already a first-class read-only capability
(`src/planner/replan.py`, M4): it reuses `propose()` + `schedule()` with
availability clipped to `[now, end]`, derives kept/moved/dropped/added by
comparing with the current plan, and never writes — the commit is
`domain.apply_replan` plus the store, decided by the application/CLI.

**`TARGET`**: keep this exact separation and generalize it conceptually:

```text
current plan
+
actual progress
+
new constraints
        ↓
      REPLAN
        ↓
new proposal
```

The planner produces a new proposal. Persistence and the application
decide afterwards whether to apply it. The Planner Engine must never
modify persistent state directly.

## 9. Temporal Model

**`CURRENT`**: naive wall-time datetimes (repository convention, no
aware datetimes — changing that would break stored data); `TimeWindow`
`[start, end)`; day clipping in the scheduler; `FixedEvent` as external
time constraint; `day_window` persisted in config by the application (not
by the planner); no timezone/DST support.

**`TARGET`**: an explicit, robust temporal model progressively covering:

- timezone;
- DST;
- date boundaries;
- fixed events;
- availability;
- working windows;
- deadlines;
- durations;
- current time;
- partial completion;
- replanning.

Time handling must stop being a collection of datetimes and scattered
conditions. The units question is already settled (abstract pomodoros for
estimates, `POMO_HOURS` as the single estimate→minutes conversion,
wall-clock minutes only at the scheduler edge) and must stay settled.

**`FUTURE`**: timezone-aware planning only when a real consumer requires
it — never preemptively (see §17).

## 10. Constraint Model

**`CURRENT`**: hard constraints exist in practice (eligibility excludes
non-active/`None`-id items; busy is a hard constraint in the scheduler —
never overlap, never invented hours; mandatory items are never cut) but
they are implicit in `constraints.py` / `scheduler.py`, not declared as
a model.

**`TARGET`**: progressively distinguish:

```text
Hard constraints
    ↓
must be respected

Soft constraints
    ↓
influence decisions / scoring
```

The system must evolve toward additional constraints without rewriting
the scheduler. Do NOT implement a generic constraint framework until the
actual code requires one.

## 11. Scoring

**`CURRENT`**: weights and heuristics live in `scoring.py` (frozen by the
Phase 2 equivalence check: 40+ scenarios, zero divergence vs legacy);
`capacity.allocate()` privileges mandatory and already-planned items;
`explain.py` freezes the reason keys consumed by the UI.

**`TARGET`**: keep conceptually separated, permanently:

```text
Eligibility
    ↓
Can this task be scheduled?

Scoring
    ↓
How desirable is this task?

Scheduling
    ↓
Where should it be placed?
```

This separation allows future scoring evolution without compromising the
temporal model or the scheduler. Scoring changes always require the
differential equivalence procedure (legacy-vs-new over the fixture
matrix, see `tests/test_planner_fixtures.py`) before merging.

## 12. Explainability

**`CURRENT`**: decision reading (`decide()`: planned→SCHEDULED,
cut→NOT_SCHEDULED, skipped→DEFERRED; `refine_with_schedule()` adds slots,
only slot-less mandatory→CONSTRAINED); `primary_reason()` (CUT/SKIPPED
flags first, then first reason, never invented text); structured evidence
(due/priority/overdue/score/rank/estimate/mandatory/capacity, never UI
text); natural-language stories (`narrative.explain_decision()`,
`why_story_*` keys, it/en); confidence only with calibrated estimates
(M2 levels on external sample counts, never computed inside
`decisions.py`); Why card in `DetailScreen`.

**`TARGET`**: make decisions observable through:

```text
decision
reason
constraint
alternative
diagnostic
```

Explainability is a core capability, not a UI responsibility: the core
produces decision + evidence + reasons, the UI renders them. Rejected
alternatives (calendar conflict, insufficient capacity) and plan-level
diagnostics belong to `PlanningResult`, not to screen code.

## 13. Public API Vision

**`CURRENT`**: internal boundary API — `Planner(todos, today, hours,
factor).propose() → DayPlan`, `Planner.schedule(plan, availability,
busy) → ScheduledDayPlan`, `replan(...) → ReplanProposal`,
`feedback(...) → tuple[ExecutionFeedback, ...]`. No stability promise,
no versioning, `TodoItem`-typed.

**`TARGET`**: a small, stable public API, conceptually:

```python
planner.plan(request)
planner.replan(request)
```

Internal APIs such as:

```text
calculate_score()
find_slot()
calculate_capacity()
_reschedule_task()
```

must never automatically become public. The principle is:

```text
Request
   ↓
Planner
   ↓
Result
```

Implementation detail stays internal; `PlanningRequest`,
`PlanningResult` and `Planner` are the only stable surface (§16, Phase 7).

## 14. External Consumers

**`FUTURE`** (explicitly not now): design so the engine *could* serve:

```text
CarpeDiem
External applications
Scripts
AI agents
CLI clients
API clients
```

Possible future adapters:

```text
Python API
CLI
REST/API
MCP
```

Do NOT implement REST, MCP, microservices, servers or any other external
interface now. A solid, independent Python core comes first; adapters
follow only when the core contract is stable (§16, Phase 8).

## 15. Future Packaging

**`CURRENT`**: `src/planner/` is an in-repo boundary by explicit decision
(`docs/adr-001-planner-boundary.md`: no separate package — no external
consumer justifies versioning/CI costs today). That decision is unchanged
and remains valid in its current context.

**`FUTURE`**: keep open the possibility that the planner becomes an
independent package, conceptually:

```text
carpediem-planner
```

with CarpeDiem as one of its consumers. This does NOT mean extracting
the package now. Priority is a correct architectural boundary, and the
packaging question is re-evaluated only in Phase 8, with real external
consumers and a sufficiently stable public contract.

## 16. Evolution Roadmap

Phases are sequential. A phase moves to done only with real implementation
plus passing tests (same rule as `AGENTS.md` §9.11 note). Phase numbering
here is the *engine* roadmap; it does not rename or reopen the completed
§9 Phases 0–10.

### Phase 1 — Planner Domain Consolidation

**`CURRENT` starting point**: `src/planner/` is already the application
boundary (NOT inside `app.py`); largely pure and deterministic; UI,
storage and network are already outside the core.

Consolidate the existing boundary into a true domain core by
progressively removing the residual couplings (small reversible commits,
equivalence tests each step):

- own `Task` view (stop typing the public path on `TodoItem`);
- explicit `now` (remove the `datetime.now()` fallback);
- conceptual dependencies toward `domain` made explicit at the boundary
  (calibration source of truth stays in `domain` until Phase 5 redesigns
  estimation);
- `PlanningRequest` / `PlanningResult` introduced as the single
  input/output shape (backed by the existing frozen models first).

Done when: the planner is constructible and testable as
`result = planner.plan(request)` with no app, UI, storage or integration
setup; residual couplings listed here are gone or explicitly re-declared
as deliberate.

### Phase 2 — Domain Core

**`TARGET`**: consolidate domain models, `PlanningRequest`,
`PlanningResult`, the `Planner` facade, and dependency boundaries.
Goal: the planner stands alone as a domain core.

### Phase 3 — Temporal Engine

**`TARGET`**: strengthen timezone policy, DST, availability, deadlines,
duration, partial completion, temporal reasoning (§9).

### Phase 4 — Constraint Engine

**`TARGET`**: progressively formalize hard vs soft constraints and keep
the system extensible without scheduler rewrites (§10).

### Phase 5 — Advanced Planning

**`TARGET`**: evolve scoring, scheduling, estimation, calibration,
replanning. This is the phase where the planner may become significantly
more sophisticated (§§8, 11).

### Phase 6 — Explainability

**`TARGET`**: decisions observable as decision / reason / constraint /
alternative / diagnostic (§12).

### Phase 7 — Public Planner API

**`CURRENT`** (2026-10-02): `PlanningRequest`, `PlanningResult`, `plan()`
stabilized as contract v1 (`PLANNER_CONTRACT_VERSION = 1`,
`docs/planner-api.md`, freeze test `tests/test_planner_api.py`);
compatibility and versioning defined (§13).

### Phase 8 — External Consumers

**`FUTURE`**: only on a stable core — independent package, CLI, REST/API,
MCP, integrations, other consumers (§§14–15). ADR-001 is re-evaluated
here, not before.

## 17. Non-goals

The evolutionary project does NOT authorize:

- enterprise architecture;
- dependency injection frameworks;
- microservices;
- databases;
- mandatory REST;
- premature abstractions;
- dozens of unused interfaces;
- classes created solely to "do architecture".

Complexity is introduced only when the domain requires it. In particular:
no timezone/DST support before a real consumer needs it; no generic
constraint framework before the code requires it; no external adapters
before the Python core is stable; no package extraction before Phase 8.

## 18. Architectural Rules

Every future phase must:

1. preserve already-validated behavior (equivalence fixtures first);
2. add tests before increasing complexity;
3. keep the core independent of adapters;
4. keep internal and external APIs clearly separated;
5. avoid giant refactors (small reversible commits);
6. answer the ten Planner questions (`AGENTS.md` §9.7: input, output,
   hard/soft constraints, scoring function, determinism, explainability,
   UI-free testability, capacity interaction, actual-time/calibration
   interaction) — if it cannot answer them clearly, stop and clarify the
   design before implementing.

## 19. Definition of Success

The project succeeds when all of the following hold:

- `result = planner.plan(request)` runs with no UI, storage, or
  integration setup, deterministically (explicit `now`).
- Every scheduled/unscheduled/conflicting item carries a machine-readable
  reason traceable to a constraint, a capacity limit, or a score rank.
- CarpeDiem (TUI + CLI) consumes only the public `Request → Result`
  surface; `tests/test_arch.py`-style guardrails still pass, extended to
  the new contracts.
- Each roadmap phase landed as small reversible commits with equivalence
  coverage and no production regression.
- External reuse is *possible* (clean boundary, versioned contract)
  whether or not extraction has happened — extraction itself remains a
  Phase 8 decision, not a success precondition.

## Appendix — Known Conflicts (vision vs current architecture)

Reported here deliberately, NOT silently fixed. Each is owned by the
roadmap phase noted.

1. **"Extract the planner from `src/app.py`" vs reality.** The planner
   does not live in `app.py`: it was extracted into `src/planner/`
   (Phases 1–10) and `app.py` is a consumer/orchestrator. Hence Phase 1
   above is "Domain Consolidation", not "Extraction". (Owned by Phase 1.)
2. **Implicit `now` vs explicit-`now` principle.** `service.py`
   falls back to `datetime.now()` when `today` is omitted, violating the
   determinism principle in §3. Declared here; fixed in Phase 1/3, not
   before. (Owned by Phases 1, 3.)
3. **Residual couplings vs side-effect-free core.** The public path is
   typed on `models.TodoItem`, and `calibration.py` / `decisions.py` /
   `capacity.py` conceptually depend on `domain` (calibration math,
   confidence levels, calibrated estimates). `domain` is pure (no I/O),
   so this is a conceptual coupling, not an effect — but the engine
   needs its own `Task` view before any public contract. (Owned by
   Phases 1, 2.)
4. **ADR-001 vs Phase 8 packaging.** `adr-001-planner-boundary.md`
   (audit 2026-09-18) decided against a separate package: no external
   consumer justifies the cost today. That decision stays valid in its
   context and is NOT modified by this document. The independent-package
   possibility is re-evaluated only in Phase 8, with real external
   consumers and a stable public contract. (Owned by Phase 8.)
