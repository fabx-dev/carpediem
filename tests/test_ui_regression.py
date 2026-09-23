"""UI regression suite permanente per la TUI CarpeDiem.

Quality gate da eseguire a ogni modifica di qualunque interfaccia:

    pytest tests/test_ui_regression.py -q     # solo questa suite
    pytest -q                                 # suite completa

Come aggiungere una nuova schermata (§15 del brief):
  1. aggiungi uno ``Scenario`` a ``UI_SCENARIOS`` qui sotto (pochi campi:
     ``name`` + ``open`` bastano per partire);
  2. ``screen`` = nome della classe: il meta-test ``test_registry_copre_*``
     FALLISCE se una screen esportata da ``src.screens`` non ha scenari,
     quindi nessuna nuova interfaccia puo' sfuggire al perimetro;
  3. dichiara i widget critici (``critical``), i testi critici
     (``critical_texts``, verificati sul render: intercetta troncamenti)
     e i dati di dominio da verificare (``expect_texts``);
  4. tutte le screen girano alle 4 taglie (120x40, 100x30, 80x24, 70x20);
     un'esenzione va motivata in ``skip_sizes``;
  5. se lo scenario copre uno stato di errore, usalo per verificare che
     messaggio, focus e layout sopravvivano (es. ``buongiorno-orario-invalido``).

Il framework generico sta in ``tests/ui_framework.py`` (audit di layout,
viewport, scroll, dimensioni minime per tipo, render-test). I problemi UI
emersi NON vanno fixati qui: si documentano in ``notes`` o nel report.
"""

from datetime import datetime
from pathlib import Path

import pytest
from textual.screen import ModalScreen

import src.storage as storage
from tests.conftest import make_app, make_todo, run
from tests.ui_framework import SIZES, Scenario, run_scenario


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _basic_todos(n=12, **kw):
    return [make_todo(f"Task {i}", todo_id=i, **kw) for i in range(1, n + 1)]


def _due_today_todos(n=8):
    return _basic_todos(n, due=f"{_today()} 10:00")


def _high_priority_todos(n=8):
    from src.models import Priority

    return _basic_todos(n, priority=Priority.HIGH)


def _completed_todos(n=10):
    return [
        make_todo(f"Vecchio {i}", todo_id=i, completed_at=f"{_today()} 10:00")
        for i in range(1, n + 1)
    ]


def _planned_todos(n=5):
    return [
        make_todo(f"Pianificato {i}", todo_id=i, planned_for=_today())
        for i in range(1, n + 1)
    ]


# --- opener con import lazy (i moduli screen vengono ricaricati da conftest) ---


def _open_menu(app, pilot):
    app.action_open_menu()


def _open_new_todo(app, pilot):
    app.action_new_todo()


def _open_edit_todo(app, pilot):
    from src.screens.form import TodoFormScreen

    todo = app.todos[0]
    app.push_screen(TodoFormScreen(todo=todo, title="Modifica"))


def _open_calpick(app, pilot):
    from src.screens.form import CalendarPickScreen

    app.push_screen(CalendarPickScreen(initial=_today()))


def _open_state(app, pilot):
    from src.screens.form import StateChoiceScreen

    app.push_screen(StateChoiceScreen("Task A", "attivo"))


def _open_confirm(app, pilot):
    from src.screens.form import ConfirmScreen

    app.push_screen(ConfirmScreen("Confermi questa azione?"))


def _open_confirm_long(app, pilot):
    from src.screens.form import ConfirmScreen

    app.push_screen(ConfirmScreen("Messaggio di errore lungo " * 8))


def _open_theme(app, pilot):
    from src.screens.form import ThemeListScreen

    app.push_screen(ThemeListScreen([f"tema-{i}" for i in range(20)], "tema-0"))


def _open_radar_pick(app, pilot):
    from src.screens.form import RadarPickScreen

    app.push_screen(RadarPickScreen([(i, f"task-{i}", i) for i in range(1, 9)]))


def _open_actual(app, pilot):
    from src.screens.form import ActualScreen

    app.push_screen(ActualScreen("Task A", 3, 2))


def _open_nl_help(app, pilot):
    from src.screens.form import NLHelpScreen

    app.push_screen(NLHelpScreen())


def _open_detail(app, pilot):
    from src.screens.views import DetailScreen

    app.push_screen(DetailScreen(app.todos[0], app.todos))


def _open_pomodoro(app, pilot):
    from src.screens.views import PomodoroScreen

    state = {
        "empty": False,
        "task": "Task A",
        "clock": "12:34",
        "paused": False,
        "total_min": 25,
        "presets": (15, 25, 50),
        "is_break": False,
        "phase": "focus",
    }
    app.push_screen(
        PomodoroScreen(
            lambda: state,
            lambda: None,
            lambda: None,
            lambda: None,
            lambda minutes: None,
        )
    )


def _open_welcome(app, pilot):
    from src.screens.system import WelcomeScreen

    app.push_screen(WelcomeScreen())


def _open_lock(app, pilot):
    from src.screens.system import LockScreen

    app.push_screen(LockScreen())


def _open_security(app, pilot):
    from src.screens.system import SecurityScreen

    app.push_screen(SecurityScreen(True))


def _open_password(app, pilot):
    from src.screens.system import PasswordScreen

    app.push_screen(
        PasswordScreen("sec_pw_title_enable", ["sec_pw_new", "sec_pw_repeat"])
    )


def _open_tpl_create(app, pilot):
    from src.screens.views import TemplateCreateScreen

    app.push_screen(TemplateCreateScreen())


def _open_tpl_project(app, pilot):
    from src.screens.views import TemplateProjectScreen

    app.push_screen(TemplateProjectScreen([(f"prog-{i}", i) for i in range(8)]))


def _open_import_csv(app, pilot):
    from src.screens.views import ImportCsvScreen

    app.push_screen(ImportCsvScreen([Path(f"/tmp/csv-{i}.csv") for i in range(3)]))


def _open_restore(app, pilot):
    from src.screens.system import RestoreScreen

    app.push_screen(RestoreScreen([Path(f"/tmp/snap-{i}.zip") for i in range(3)]))


def _setup_templates(app):
    app.templates = {f"Tpl {i}": [{"title": "x"}] for i in range(20)}


def _setup_archive(app):
    # L'archivio vero (file), non lo store: la screen legge load_archive().
    # Prima passava per caso via tabella home in trasparenza nel render.
    storage.save_archive([t.to_dict() for t in _completed_todos(10)])


# --- interazioni minime (contratto UI di base, §6/§11 del brief) ---


async def _interact_type_title(pilot, app, screen):
    from textual.widgets import Input

    inp = screen.query_one("#title-input", Input)
    inp.focus()
    await pilot.pause()
    await pilot.press(*"Ciao")
    assert inp.value == "Ciao"


async def _interact_search(pilot, app, screen):
    from textual.widgets import Input

    inp = screen.query_one("#search-input", Input)
    inp.focus()
    await pilot.pause()
    await pilot.press(*"Task")
    assert inp.value == "Task"


async def _interact_goals(pilot, app, screen):
    from textual.widgets import Input

    await pilot.press("tab", "tab")
    assert isinstance(app.focused, Input)


async def _interact_slot_invalid(pilot, app, screen):
    """Stato di errore: orario availability non valido (§11)."""
    from textual.widgets import Input

    start = screen.query_one("#planp-start", Input)
    start.value = "zz"
    await pilot.pause()
    assert screen.slot_error == "planp_start_bad"
    assert not start.disabled  # l'utente puo' ancora correggere
    assert app.focused is not None


async def _interact_slot_valid(pilot, app, screen):
    """Dato dominio 09:00-18:00 -> slot renderizzati coerenti (§7)."""
    from textual.widgets import Input

    start = screen.query_one("#planp-start", Input)
    end = screen.query_one("#planp-end", Input)
    start.value = "09:00"
    end.value = "18:00"
    await pilot.pause()
    assert screen.slot_error is None
    assert screen.sched is not None


# --- registry ---


UI_SCENARIOS = [
    Scenario(
        name="home",
        open=lambda app, pilot: None,
        screen="",
        todos=_basic_todos,
        critical=("todo-table",),
        no_close=True,
        notes="vista principale: nessuna modale, niente chiusura (con dati: niente benvenuto)",
    ),
    Scenario(
        name="menu",
        open=_open_menu,
        screen="MenuScreen",
        critical=("menu-box", "menu-bar", "menu-drop", "menu-close"),
        critical_texts=("Menu",),
    ),
    Scenario(
        name="form-nuovo",
        open=_open_new_todo,
        screen="TodoFormScreen",
        critical=("form-container", "title-input", "save-btn", "cancel-btn"),
        critical_texts=("Salva",),
        interact=_interact_type_title,
    ),
    Scenario(
        name="form-modifica",
        open=_open_edit_todo,
        screen="TodoFormScreen",
        critical=("form-container", "title-input", "save-btn", "cancel-btn"),
        critical_texts=("Salva",),
        todos=lambda: _basic_todos(1),
    ),
    Scenario(
        name="calendario-picker",
        open=_open_calpick,
        screen="CalendarPickScreen",
        critical=("calpick-box", "calpick-title", "calpick-grid", "calpick-close"),
        expect_texts=(str(datetime.now().day),),
    ),
    Scenario(
        name="cambia-stato",
        open=_open_state,
        screen="StateChoiceScreen",
        critical=("state-box", "state-buttons", "state-legend"),
    ),
    Scenario(
        name="conferma",
        open=_open_confirm,
        screen="ConfirmScreen",
        critical=("confirm-box", "confirm-msg", "yes-btn", "no-btn"),
    ),
    Scenario(
        name="conferma-messaggio-lungo",
        open=_open_confirm_long,
        screen="ConfirmScreen",
        critical=("confirm-box", "confirm-msg", "yes-btn", "no-btn"),
        notes="stato di errore/limite: il messaggio lungo non deve collassare il dialog",
    ),
    Scenario(
        name="tema",
        open=_open_theme,
        screen="ThemeListScreen",
        critical=("theme-box", "theme-list", "theme-close"),
    ),
    Scenario(
        name="radar-pick",
        open=_open_radar_pick,
        screen="RadarPickScreen",
        critical=("pick-box", "pick-list", "pick-close"),
    ),
    Scenario(
        name="ricerca",
        open=lambda app, pilot: app.action_search_todos(),
        screen="SearchScreen",
        critical=("search-box", "search-input", "ok-btn"),
        interact=_interact_search,
    ),
    Scenario(
        name="tempo-effettivo",
        open=_open_actual,
        screen="ActualScreen",
        critical=("actual-box", "actual-input", "actual-save", "actual-info"),
    ),
    Scenario(
        name="nl-help",
        open=_open_nl_help,
        screen="NLHelpScreen",
        critical=("nlh-box", "nlh-title", "nlh-close"),
    ),
    Scenario(
        name="piano-giorno",
        open=lambda app, pilot: app.action_view_daily_plan(),
        screen="DailyPlanScreen",
        critical=("plan-box", "plan-title", "plan-close"),
        todos=_planned_todos,
        expect_texts=("Pianificato 1",),
    ),
    Scenario(
        name="buongiorno",
        open=lambda app, pilot: app.action_plan_day(),
        screen="PlanProposalScreen",
        critical=(
            "planp-box",
            "planp-title",
            "planp-scroll",
            "planp-confirm",
            "planp-close",
        ),
        critical_texts=("Salva",),
        top_containers=("planp-scroll",),
        todos=_high_priority_todos,
        notes="i widget sotto il fold (eventi, slot, lista) sono nel contenitore scrollabile",
    ),
    Scenario(
        name="buongiorno-slot",
        open=lambda app, pilot: app.action_plan_day(),
        screen="PlanProposalScreen",
        critical=("planp-box", "planp-title"),
        interact=_interact_slot_valid,
        post_texts=("09:00",),
        todos=_high_priority_todos,
        notes="dato dominio 09:00-18:00 deve finire coerente nella timeline",
    ),
    Scenario(
        name="buongiorno-orario-invalido",
        open=lambda app, pilot: app.action_plan_day(),
        screen="PlanProposalScreen",
        critical=("planp-box", "planp-title"),
        interact=_interact_slot_invalid,
        todos=_high_priority_todos,
        notes="stato di errore: hint visibile, input utilizzabile, layout stabile",
    ),
    Scenario(
        name="review",
        open=lambda app, pilot: app.action_open_review(),
        screen="ReviewScreen",
        critical=("rev-box", "rev-scroll", "rev-confirm", "rev-close"),
        top_containers=("rev-scroll",),
        todos=lambda: _basic_todos(8),
    ),
    Scenario(
        name="resoconto-sera",
        open=lambda app, pilot: app.action_briefing_evening(),
        screen="BriefingScreen",
        critical=("brief-box", "brief-hint", "brief-goto", "brief-close"),
        todos=lambda: _basic_todos(8),
    ),
    Scenario(
        name="agenda",
        open=lambda app, pilot: app.action_view_agenda(),
        screen="AgendaScreen",
        critical=("agenda-box", "agenda-list", "agenda-close"),
        todos=_due_today_todos,
        expect_texts=("Task 1",),
    ),
    Scenario(
        name="workflow",
        open=lambda app, pilot: app.action_view_workflow(),
        screen="WorkflowScreen",
        critical=("workflow-box", "workflow-list", "workflow-close"),
    ),
    Scenario(
        name="settimana",
        open=lambda app, pilot: app.action_view_week(),
        screen="WeekScreen",
        critical=(
            "week-box",
            "week-nav",
            "prev-btn",
            "next-btn",
            "week-list",
            "week-close",
        ),
        todos=_due_today_todos,
    ),
    Scenario(
        name="calendario",
        open=lambda app, pilot: app.action_view_calendar(),
        screen="CalendarScreen",
        critical=("calendar-box", "calendar-grid", "calendar-legend", "calendar-close"),
        todos=_due_today_todos,
    ),
    Scenario(
        name="giorno",
        open=lambda app, pilot: app.action_open_day(
            datetime.now().year, datetime.now().month, datetime.now().day
        ),
        screen="DayScreen",
        critical=("day-box", "day-list", "day-close"),
        todos=_due_today_todos,
        expect_texts=("Task 1",),
    ),
    Scenario(
        name="dettaglio",
        open=_open_detail,
        screen="DetailScreen",
        critical=(
            "detail-box",
            "detail-title",
            "detail-scroll",
            "detail-edit",
            "detail-close",
        ),
        todos=lambda: _basic_todos(1),
        expect_texts=("Task 1",),
    ),
    Scenario(
        name="pomodoro",
        open=_open_pomodoro,
        screen="PomodoroScreen",
        critical=(
            "pomo-box",
            "pomo-time",
            "pomo-durations",
            "pause-btn",
            "done-btn",
            "stop-btn",
            "pomo-close",
        ),
        expect_texts=("12:34", "Task A"),
    ),
    Scenario(
        name="kanban",
        open=lambda app, pilot: app.action_view_kanban(),
        screen="KanbanScreen",
        critical=("kb-box", "kb-cols", "kb-close"),
        todos=lambda: _basic_todos(8),
    ),
    Scenario(
        name="statistiche",
        open=lambda app, pilot: app.action_view_stats(),
        screen="StatsScreen",
        critical=("stats-box", "stats-scroll", "stats-close"),
        top_containers=("stats-scroll",),
        todos=_completed_todos,
    ),
    Scenario(
        name="obiettivi",
        open=lambda app, pilot: app.action_edit_goals(),
        screen="GoalsScreen",
        critical=(
            "goals-box",
            "goals-daily",
            "goals-weekly",
            "goals-pomo",
            "goals-save",
            "goals-cancel",
        ),
        interact=_interact_goals,
    ),
    Scenario(
        name="archivio",
        open=lambda app, pilot: app.action_view_archive(),
        screen="ArchiveScreen",
        critical=("arc-box", "arc-list", "arc-close"),
        setup=_setup_archive,
        expect_texts=("Vecchio 1",),
    ),
    Scenario(
        name="modelli",
        open=lambda app, pilot: app.action_new_from_template(),
        screen="TemplateScreen",
        critical=("tpl-box", "tpl-list", "tpl-close"),
        setup=_setup_templates,
    ),
    Scenario(
        name="modello-nuovo",
        open=_open_tpl_create,
        screen="TemplateCreateScreen",
        critical=("tplc-box", "tplc-name", "tplc-tasks", "tplc-save", "tplc-cancel"),
    ),
    Scenario(
        name="modello-da-progetto",
        open=_open_tpl_project,
        screen="TemplateProjectScreen",
        critical=("tplp-box", "tplp-list", "tplp-close"),
    ),
    Scenario(
        name="import-csv",
        open=_open_import_csv,
        screen="ImportCsvScreen",
        critical=("impcsv-box", "impcsv-list", "impcsv-ok"),
    ),
    Scenario(
        name="ripristino",
        open=_open_restore,
        screen="RestoreScreen",
        critical=("rst-box", "rst-list", "rst-close"),
    ),
    Scenario(
        name="impostazioni",
        open=lambda app, pilot: app.action_open_settings(),
        screen="SettingsScreen",
        critical=(
            "set-box",
            "set-body",
            "set-theme",
            "set-lang",
            "set-save",
            "set-cancel",
        ),
        top_containers=("set-body",),
    ),
    Scenario(
        name="smart-list",
        open=lambda app, pilot: app.action_open_smart_lists(),
        screen="SmartListScreen",
        critical=("smart-box", "smart-rows", "smart-name", "smart-close"),
    ),
    Scenario(
        name="benvenuto",
        open=_open_welcome,
        screen="WelcomeScreen",
        setup=lambda app: app.config.update(onboarded=True),
        critical=("wel-box", "wel-title", "wel-body", "wel-buttons"),
        notes="onboarded=True: il push diretto e' l'unico welcome (altrimenti escape "
        "chiude solo la nostra copia e quella di startup resta)",
    ),
    Scenario(
        name="blocco",
        open=_open_lock,
        screen="LockScreen",
        critical=("lock-box", "lock-pw", "lock-ok", "lock-exit"),
    ),
    Scenario(
        name="sicurezza",
        open=_open_security,
        screen="SecurityScreen",
        critical=("sec-box", "sec-status", "sec-buttons", "sec-change", "sec-disable"),
    ),
    Scenario(
        name="password",
        open=_open_password,
        screen="PasswordScreen",
        critical=("pw-box", "pw-title", "pw-body", "pw-ok", "pw-cancel"),
    ),
    Scenario(
        name="tasti",
        open=lambda app, pilot: app.action_show_keys(),
        screen="KeysScreen",
        critical=("keys-box", "keys-list", "keys-close"),
    ),
    Scenario(
        name="salute",
        open=lambda app, pilot: app.action_view_health(),
        screen="HealthScreen",
        critical=("hea-box", "hea-list", "hea-close"),
        todos=lambda: _basic_todos(8, project="p"),
    ),
]


@pytest.mark.parametrize("scenario", UI_SCENARIOS, ids=lambda s: s.name)
def test_ui_scenario(scenario, tmp_files):
    """Quality gate: layout, viewport, scroll, testi critici, dati, interazione,
    chiusura — a tutte le taglie previste."""
    problems_all: list[str] = []
    skipped: list[str] = []
    for size in SIZES:
        if size in scenario.skip_sizes:
            skipped.append(f"{size}: {scenario.skip_sizes[size]}")
            continue
        app = make_app(scenario.todos() if scenario.todos else [])
        if scenario.setup is not None:
            scenario.setup(app)
        problems = run(run_scenario(app, scenario, size))
        problems_all += [f"{size[0]}x{size[1]}: {p}" for p in problems]
    if skipped:
        problems_all.append(f"taglie escluse motivate: {', '.join(skipped)}")
    assert not problems_all, f"UI regression [{scenario.name}]\n" + "\n".join(
        problems_all
    )


def test_registry_nomi_unici():
    names = [s.name for s in UI_SCENARIOS]
    assert len(names) == len(set(names))


def test_registry_copre_tutte_le_screen():
    """Guardrail §15: ogni ModalScreen esportata da src.screens deve avere
    almeno uno scenario. Una nuova interfaccia senza registry rompe questo test."""
    import src.screens as screens

    modali = {
        name
        for name in screens.__all__
        if isinstance(getattr(screens, name), type)
        and issubclass(getattr(screens, name), ModalScreen)
        # mixin condiviso, non e' una schermata concreta
        and name != "CloseMixin"
    }
    coperte = {s.screen for s in UI_SCENARIOS if s.screen}
    assert modali <= coperte, (
        f"screen senza scenario UI regression: {sorted(modali - coperte)}"
    )
