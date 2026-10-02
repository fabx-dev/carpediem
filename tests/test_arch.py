"""Guardrail Fase 9: la UI e' consumer del Planner, mai secondo planner.

Non vieta ordinamenti/filtri di presentazione (legittimi in review/agenda):
vieta la duplicazione di merito/capacita'/scheduling e il percorso legacy.
Nessun vincolo su QUALI screen possano usare il Planner: oggi PlanProposalScreen
e' il consumer ufficiale (Fasi 6.5/7), domani altre screen potranno esserlo —
purché attraverso il boundary src/planner, non reimplementandolo.
"""

import pathlib
import re

UI_FILES = sorted(pathlib.Path("src/screens").glob("*.py")) + [
    pathlib.Path("src/app.py")
]

# Costanti di merito/capacita': se una screen le usa, sta ricalcolando il merito.
WEIGHT_CONSTANTS = (
    "OVERDUE_SCORE",
    "DUE_TODAY_SCORE",
    "DUE_TOMORROW_SCORE",
    "PRIO_SCORES",
    "STALE_SCORE",
    "STALE_DAYS",
    "PLANNED_SCORE",
    "POMO_HOURS",
    "DEFAULT_ESTIMATE",
)

# Reimplementazione del boundary: definizioni locali di propose/schedule/Planner.
REIMPLEMENTATION = (
    "def propose(",
    "def schedule(",
    "class Planner",
    "def plan_day(",
    "def replan(",
)

# M2/M3/M4: le screen non fanno I/O execution ne' costruiscono/persistono
# record (solo l'app orchestra via recorder). Gli helper di LETTURA del
# dominio sono presentazione dati e quindi ammessi nella UI (precedente
# StatsScreen con calibration_factor): siano primitivi (predicted_minutes,
# resolve_actual_minutes) o aggregati di sola lettura (execution_summary,
# execution_stats, calibration_summary — quest'ultimo in domain da Phase 2),
# purche' senza I/O ne' mutazioni.
SCREEN_FORBIDDEN = (
    "make_execution",
    "append_execution",
    "load_executions",
)
# app.py orchestra I/O e recorder, ma non ricalcola analytics aggregate.
APP_FORBIDDEN = (
    "execution_stats",
    "execution_confidence",
    "execution_summary",
    "calibration_summary",
)

FAIL_MSG = "La UI e' consumer del Planner (Fase 9): niente merito/capacita'/scheduling duplicati; usa src/planner, non plan_day()."
FAIL_EXEC_MSG = "M2: la UI consuma execution/stats/calibration pronte, non le costruisce (dominio/planner la fonte)."


def _sources():
    return [(p, p.read_text(encoding="utf-8")) for p in UI_FILES]


def _screen_sources():
    return [(p, s) for p, s in _sources() if "screens" in p.parts]


def test_no_costanti_merito_nella_ui():
    for path, src in _sources():
        for const in WEIGHT_CONSTANTS:
            assert const not in src, f"{path}: costante {const} nella UI. {FAIL_MSG}"


def test_no_reimplementazione_planner_nelle_screen():
    for path, src in _sources():
        for pat in REIMPLEMENTATION:
            assert pat not in src, f"{path}: '{pat}' duplica il boundary. {FAIL_MSG}"


# "src.plan" ma non "src.planner"; "plan_day(" come chiamata, non come
# suffisso di un identificatore (es. action_plan_day e' wiring, non planning).
_LEGACY_PLAN = re.compile(r"src\.plan(?!ner)")
_PLAN_DAY_CALL = re.compile(r"(?<![\w])plan_day\(")


def test_no_plan_day_legacy_nella_produzione_ui():
    for path, src in _sources():
        assert not _PLAN_DAY_CALL.search(src), (
            f"{path}: usa il Planner, non plan_day(). {FAIL_MSG}"
        )
        assert not _LEGACY_PLAN.search(src), (
            f"{path}: legacy src/plan vietato dalla Fase 9. {FAIL_MSG}"
        )


def test_no_execution_logic_nelle_screen():
    for path, src in _screen_sources():
        for name in SCREEN_FORBIDDEN:
            assert name not in src, f"{path}: '{name}' nella screen. {FAIL_EXEC_MSG}"


def test_no_execution_stats_in_app():
    src = pathlib.Path("src/app.py").read_text(encoding="utf-8")
    for name in APP_FORBIDDEN:
        assert name not in src, f"src/app.py: '{name}' nell'app. {FAIL_EXEC_MSG}"


# M3 Why nel Detail: views.py consuma solo il boundary (Planner + decide),
# mai gli stadi interni (scoring/constraints/capacity/explain) ne' le regole.
# Buongiorno (plan.py) resta l'unica screen che legge i motivi reason.
_M3_VIEWS_BANNED = (
    "planner.scoring",
    "planner.constraints",
    "planner.capacity",
    "planner.explain",
)


def test_no_stadi_planner_in_views():
    src = pathlib.Path("src/screens/views.py").read_text(encoding="utf-8")
    for name in _M3_VIEWS_BANNED:
        assert name not in src, (
            f"src/screens/views.py: '{name}' nel Detail. "
            "Il Why consuma PlanningDecision dal boundary, non gli stadi."
        )


# Phase 1 (Step 6, T8): il core non importa il modello storage (solo
# l'adapter planner/models.py lo conosce per conversione); i fallback
# wall-clock sono allowlisted riga per riga; niente commit/persistenza
# nel planner (propone, non scrive). Le menzioni in docstring/commenti
# sono documentazione del boundary, non dipendenze: si controllano solo
# le righe di import.
_PLANNER_CORE = (
    "scoring",
    "capacity",
    "constraints",
    "decisions",
    "feedback",
)

_PLANNER_NO_STORAGE_TOKENS = (
    "TodoItem",
    "Priority",
    "_due_date_part",
    "src.models",
)

_PLANNER_NO_COMMIT_TOKENS = (
    "apply_replan",
    "store",
    "commit",
    "save_",
    "load_",
)


def _planner_lines(name):
    return (
        pathlib.Path(f"src/planner/{name}.py").read_text(encoding="utf-8").splitlines()
    )


def _import_lines(name):
    return [
        ln.strip()
        for ln in _planner_lines(name)
        if ln.strip().startswith(("from ", "import "))
    ]


def test_phase1_core_senza_modello_storage():
    for name in _PLANNER_CORE:
        for line in _import_lines(name):
            for token in _PLANNER_NO_STORAGE_TOKENS:
                assert token not in line, (
                    f"src/planner/{name}.py: '{token}' negli import del core. "
                    "Usa TaskView/projection."
                )


def test_phase1_planner_senza_commit_o_persistenza():
    for path in sorted(pathlib.Path("src/planner").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(("from ", "import ")):
                for token in _PLANNER_NO_COMMIT_TOKENS:
                    assert token not in s, (
                        f"{path}: '{token}' negli import del planner. "
                        "Il planner propone, l'applicazione committa."
                    )


def test_phase2_estimation_math_solo_in_capacity():
    """D1: la matematica estimation di domain entra nel planner da un solo
    seam (capacity.estimate/normalize_factor), documentato e sotto contratto
    (tests/test_phase2_estimation.py). Trasloco vietato fino a Phase 5."""
    for path in sorted(pathlib.Path("src/planner").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(("from ", "import ")) and (
                "calibrated_estimate" in s or "CAL_CLAMP" in s
            ):
                assert path.name == "capacity.py", (
                    f"{path}: matematica estimation fuori dal seam capacity. "
                    "Vedi docs/planner-phase2-plan.md §7 D1."
                )


def test_phase2_niente_stadi_interni_fuori_boundary():
    """G1: app/screens/CLI consumano il boundary (Planner/plan/decide/
    replan/feedback/models/narrative), mai gli stadi decisionali. Fa
    eccezione capacity.total (pura conversione ore->pomo nell'adapter,
    nessuna decisione): allocate/estimate restano vietati qui."""
    files = sorted(pathlib.Path("src/screens").glob("*.py")) + [
        pathlib.Path("src/app.py"),
        pathlib.Path("src/cli.py"),
    ]
    banned = (
        "planner.scoring",
        "planner.constraints",
        "capacity.allocate",
        "capacity.estimate",
    )
    for path in files:
        src = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in src, (
                f"{path}: '{token}' fuori dal boundary. "
                "Decisioni solo in src/planner, la UI consuma il risultato."
            )


def test_phase6_diagnose_unica_costruttrice():
    """G5: alternative/diagnostics nascono solo in diagnostics.diagnose().
    Ammessi: il modulo stesso + il test di forma D1 (costruzioni fittizie
    per frozen/field-shape, mai logica)."""
    allowed = {
        "src/planner/diagnostics.py",
        "tests/test_phase6_types.py",
    }
    exempt = {"tests/test_arch.py"}  # questo guard cita i nomi nel suo codice
    for path in sorted(pathlib.Path("src").rglob("*.py")) + sorted(
        pathlib.Path("tests").glob("test_*.py")
    ):
        # as_posix: su Windows str(path) usa backslash (lezione CI P6).
        posix = path.as_posix()
        if posix in exempt:
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "PlanAlternative(" in src or "PlanDiagnostic(" in src:
            assert posix in allowed, (
                f"{path}: costruisce alternative/diagnostics fuori da diagnose(). "
                "Unico costruttore consentito (docs/planner-phase6-plan.md §5)."
            )


def test_phase5_planner_senza_domain():
    """G4: direzione unica app -> core. Niente in src/planner/ importa
    src.domain (dal P5-1 la matematica vive in planner.estimation e domain
    delega). Docstring/commenti possono nominarlo (documentano il passato)."""
    for path in sorted(pathlib.Path("src/planner").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith(("from ", "import ")) and "src.domain" in s:
                raise AssertionError(
                    f"{path}: import da src.domain. "
                    "Il core non dipende dall'app (docs/planner-phase5-plan.md §3)."
                )


def test_phase4_constraint_sites_allowlisted():
    """G3: decisioni su stato solo nei siti dichiarati (marker
    `# constraint-site`): nuove esclusioni silenziose sparse vietate.
    Righe docstring/elenco (che iniziano per - # " ' *) documentano,
    non decidono. Window ±6: i blocchi di derivazione (models.py) tengono
    un marker solo in testa — guard euristico come T8, dichiarato qui.
    Limiti noti (non bloccanti): scope solo src/planner/ (un sito in
    app/domain/screens passa); vede solo letterali quotati (filtri su
    booleani .done/.paused o costanti evadono senza marker)."""
    import re

    pat = re.compile(r"""["'](?:attivo|completato|in_sospeso)["']""")
    checked = 0
    for path in sorted(pathlib.Path("src/planner").glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            s = line.strip()
            if not pat.search(s) or (s[:1] in "-#\"'*>" or s.startswith("```")):
                continue
            checked += 1
            window = lines[max(0, i - 6) : i + 1]
            assert any("constraint-site" in w for w in window), (
                f"{path}:{i + 1}: decisione su stato senza marker. "
                "Siti nuovi vietati: le esclusioni vivono in constraints.py "
                "(docs/planner-phase4-plan.md §3 C-Guard)."
            )
    assert checked >= 5, f"siti attesi >= 5, trovati: {checked}"


def test_phase3_core_senza_aware():
    """G2: il core resta naive (convenzione storage): niente aritmetica di
    zona in src/planner/ — conversioni solo ai bordi (Outlook edge)."""
    for path in sorted(pathlib.Path("src/planner").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        for token in ("tzinfo", "astimezone", "ZoneInfo", "utcoffset"):
            assert token not in src, (
                f"{path}: '{token}' nel core. "
                "Wall-time naive per convenzione (policy in scheduler.py)."
            )


def test_phase1_wall_clock_solo_allowlisted():
    found = []
    for path in sorted(pathlib.Path("src/planner").glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "datetime.now()" in line or "date.today()" in line:
                window = lines[max(0, i - 3) : i + 1]
                assert any("allowlist" in w for w in window), (
                    f"{path}:{i + 1}: wall-clock senza marker allowlist. "
                    "Phase 1: produzione esplicita, fallback solo compat "
                    "documentato (docs/planner-phase1-plan.md §6.0)."
                )
                found.append((str(path), i + 1))
    assert len(found) == 2, f"fallback attesi: 2, trovati: {found}"
