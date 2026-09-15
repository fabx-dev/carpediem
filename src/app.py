"""Applicazione TodoApp + tabella cliccabile."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import CommandPalette
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Static,
    TextArea,
)

from src import crypto as _crypto
from src import domain
from src.commands import CarpeDiemMenuProvider, menu_categories
from src.lang import T, prio_disp, rec_disp
from src.models import (
    MAX_DEPTH,
    PRIORITY_ORDER,
    Priority,
    Recurrence,
    TodoItem,
    _due_date_part,
    _is_valid_due,
    _normalize_date,
    _pomo_label,
    _status,
)
from src.screens import (
    AgendaScreen,
    ArchiveScreen,
    BriefingScreen,
    CalendarScreen,
    ConfirmScreen,
    DailyPlanScreen,
    DayScreen,
    DetailScreen,
    GoalsScreen,
    HealthScreen,
    ImportCsvScreen,
    KanbanScreen,
    KeysScreen,
    LockScreen,
    MenuScreen,
    PasswordScreen,
    PlanProposalScreen,
    PomodoroScreen,
    RestoreScreen,
    ReviewScreen,
    SearchScreen,
    SecurityScreen,
    SettingsScreen,
    StateChoiceScreen,
    StatsScreen,
    TemplateCreateScreen,
    TemplateProjectScreen,
    TemplateScreen,
    ThemeListScreen,
    TodoFormScreen,
    WeekScreen,
    WelcomeScreen,
    WorkflowScreen,
)
from src.screens._shared import _escape_markup
from src.storage import (
    FILTER_STATES,
    POMO_PHASE_PRESETS,
    POMO_PHASES,
    _backup_sources,
    _clamp_int,
    _home,
    create_backup,
    list_snapshots,
    load_archive,
    load_config,
    load_pomodoro,
    load_templates,
    restore_snapshot,
    save_archive,
    save_config,
    save_pomodoro,
    save_templates,
    snapshot_info,
    state_readable,
)
from src.store import TodoStore

# Il toast del reminder scadenze resta visibile finche' non lo clicchi
# (default Textual: 5 s) e suona 3 beep invece di 1.
REMINDER_TOAST_TIMEOUT = 600
REMINDER_BEEPS = 3


class ClickableDataTable(DataTable):
    """DataTable that opens a row detail on a single click."""

    async def _on_click(self, event) -> None:
        try:
            self._set_hover_cursor(True)
            meta = getattr(event.style, "meta", {}) or {}
            if (
                "row" in meta
                and "column" in meta
                and meta["row"] is not None
                and meta["row"] >= 0
            ):
                row_index = meta["row"]
                if 0 <= row_index < len(self.ordered_rows):
                    self.move_cursor(row=row_index, scroll=True)
                    self.post_message(
                        self.RowSelected(
                            self, row_index, self.ordered_rows[row_index].key
                        )
                    )
                    event.stop()
                    return
        except Exception:
            pass
        await super()._on_click(event)


def _demo_todos(start_id: int = 1) -> list[TodoItem]:
    """Dati di esempio con date relative a oggi (onboarding)."""
    today = datetime.now().date()

    def iso(offset: int) -> str:
        return (today + timedelta(days=offset)).strftime("%Y-%m-%d")

    nid = start_id
    items: list[TodoItem] = []

    def add(**kw) -> TodoItem:
        nonlocal nid
        t = TodoItem(todo_id=nid, **kw)
        nid += 1
        items.append(t)
        return t

    padre = add(
        title="Preventivo cliente Acme",
        priority=Priority.HIGH,
        due=iso(2),
        project="acme",
        tags=["preventivo"],
        notes="- [ ] Voce manodopera\n- [ ] Voce materiali",
        stima_pomo=4,
    )
    add(
        title="Raccogli requisiti",
        priority=Priority.MEDIUM,
        parent_id=padre.id,
        project="acme",
    )
    add(
        title="Sopralluogo",
        priority=Priority.MEDIUM,
        due=iso(1),
        parent_id=padre.id,
        project="acme",
    )
    add(
        title="Chiamare Banca",
        priority=Priority.MEDIUM,
        due=iso(0),
        project="personale",
        tags=["call"],
    )
    add(title="Spesa settimanale", priority=Priority.LOW, due=iso(5))
    add(
        title="Leggere report",
        priority=Priority.LOW,
        done=True,
        completed_at=(today - timedelta(days=1)).strftime("%Y-%m-%d") + " 18:00",
    )
    return items


def _needs_unlock() -> bool:
    """True se almeno un file dati e' cifrato."""
    for name, path in _backup_sources():
        if name == "config":
            continue
        try:
            if path.exists() and _crypto.is_envelope(path.read_text(encoding="utf-8")):
                return True
        except OSError:
            pass
    return False


class TodoApp(App):
    """A TUI To-Do application."""

    TITLE = "CarpeDiem"
    SUB_TITLE = T("app_subtitle")

    CSS = """
    Screen {
        layout: vertical;
    }
    Button {
        min-width: 16;
        height: 3;
    }
    #stats-bar {
        height: auto;
        min-height: 1;
        dock: bottom;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    DataTable {
        height: 1fr;
    }
    #help-panel {
        height: auto;
        max-height: 12;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
        margin: 0 1;
    }
    #help-panel.hidden {
        display: none;
    }
    #kanban-bar {
        height: 7;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
        margin: 0 1;
    }
    #kanban-bar.hidden {
        display: none;
    }
    #pomodoro-bar {
        height: 3;
        border: solid $error;
        background: $error-darken-2;
        color: $text;
        text-style: bold;
        padding: 0 1;
        margin: 0 1;
    }
    #pomodoro-bar.paused {
        border: solid $warning;
        background: $warning-darken-2;
    }
    #pomodoro-bar.break {
        border: solid $success;
        background: $success-darken-2;
    }
    #pomodoro-bar.hidden {
        display: none;
    }
    Footer {
        padding-left: 1;
    }
    /* Shell modali condivisa: stesse regole di prima, un solo punto.
       (Dichiarazioni spostate dalle 27 screen: root, box, titoli, chiudi.) */
    ModalScreen {
        align: center middle;
    }
    #state-box, #theme-box, #search-box, #agenda-box, #week-box, #tpl-box, #tplc-box,
    #tplp-box, #impcsv-box, #pomo-box, #kb-box, #detail-box, #day-box,
    #calendar-box, #plan-box, #goals-box, #stats-box, #keys-box, #set-box,
    #arc-box, #rst-box, #wel-box, #pw-box, #sec-box, #hea-box, #rev-box,
    #menu-box, #workflow-box, #brief-box, #planp-box {
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #agenda-title, #tpl-title, #tplc-title, #tplp-title, #impcsv-title, #goals-title,
    #keys-title, #set-title, #arc-title, #rst-title, #wel-title,
    #pw-title, #sec-title, #rev-title, #menu-title, #workflow-title,
    #brief-title, #planp-title, #state-msg {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        height: auto;
    }
    #theme-close, #kb-close, #day-close, #calendar-close, #plan-close,
    #stats-close, #menu-close {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-top: 1;
    }
    #agenda-close, #week-close, #tplp-close, #keys-close, #rst-close, #hea-close,
    #workflow-close, #brief-close {
        width: 100%;
        min-width: 16;
        height: 3;
    }
    /* Righe bottone condivise (le screen con misure specifiche sovrascrivono). */
    .btn-row Button {
        width: 1fr;
        min-width: 14;
        height: 3;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("n", "new_todo", T("b_new")),
        Binding("s", "add_subtask", T("b_subtask")),
        Binding("space", "toggle_done", T("b_status")),
        Binding("e", "edit_todo", T("b_edit")),
        Binding("d", "delete_todo", T("b_delete")),
        Binding("h", "toggle_help", T("b_help")),
        Binding("enter", "view_detail", "Dettagli", show=False),
        Binding("f", "filter_todos", "Filtro stato", show=False),
        Binding("t", "filter_by_tag", "Filtro tag", show=False),
        Binding("g", "filter_by_project", "Filtro progetto", show=False),
        Binding("slash", "search_todos", T("b_search"), show=True),
        Binding("q", "quit", T("b_quit")),
        Binding("c", "view_calendar", "Calendario", show=False),
        Binding("w", "view_week", "Settimana", show=False),
        Binding("b", "toggle_kanban", "Kanban", show=False),
        Binding("B", "view_kanban", "Kanban full", show=False),
        Binding("p", "view_daily_plan", "Piano", show=False),
        Binding("P", "plan_day", "Pianifica", show=False),
        Binding("k", "view_stats", "Statistiche", show=False),
        Binding("o", "start_pomodoro", "Pomodoro", show=False),
        Binding("O", "pomodoro_pause", "Pausa/Riprendi", show=False),
        Binding("X", "pomodoro_finish", "Completa pomo", show=False),
        Binding("u", "undo_delete", "Annulla", show=False),
        Binding("T", "new_from_template", "Template", show=False),
        Binding("y", "view_health", "Salute", show=False),
        Binding("v", "choose_theme", "Tema...", show=False),
        Binding("ctrl+s", "save_screenshot", "Screenshot", show=False),
        Binding("ctrl+e", "export_data", "Export", show=False),
        Binding("r", "refresh", "Ricarica", show=False),
        Binding("R", "open_review", "Chiusura", show=False),
        Binding(
            "ctrl+p",
            "command_palette",
            T("b_palette"),
            show=False,
            tooltip=T("palette_tooltip"),
        ),
        Binding("m", "open_menu", T("b_menu"), show=True, tooltip=T("menu_tooltip")),
    ]

    COMMAND_PALETTE_BINDING = "ctrl+p"

    COMMANDS = App.COMMANDS | {CarpeDiemMenuProvider}

    def get_system_commands(self, screen: Screen):
        """Comandi di sistema della palette, localizzati (senza ingrandisci: inutile qui)."""
        yield SystemCommand(
            T("sys_theme_t"), T("sys_theme_h"), self.action_choose_theme
        )
        yield SystemCommand(T("sys_quit_t"), T("sys_quit_h"), self.action_quit)
        yield SystemCommand(T("sys_keys_t"), T("sys_keys_h"), self.action_show_keys)
        yield SystemCommand(
            T("sys_snap_t"),
            T("sys_snap_h"),
            lambda: self.set_timer(0.1, self.deliver_screenshot),
        )

    def action_command_palette(self) -> None:
        """Mostra la palette comandi (ricerca globale)."""
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(
                CommandPalette(id="--command-palette", placeholder=T("pal_placeholder"))
            )

    def action_open_menu(self) -> None:
        """Apre il menu per funzioni (categorie -> voci)."""

        def on_pick(action_name: str | None) -> None:
            if not action_name:
                return
            callback = getattr(self, action_name, None)
            if callable(callback):
                callback()

        self.push_screen(MenuScreen(menu_categories()), on_pick)

    #: Action App sempre consentite sotto modale: navigazione focus di Textual
    #: + open_day (il calendario apre il giorno sopra di se': modale legittima).
    _MODAL_SAFE_ACTIONS = frozenset({"focus_next", "focus_previous", "open_day"})

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Sotto una modale le action App sono inerti: niente screen impilate
        sopra i dialoghi (le screen si chiudono da sole con dismiss+callback)."""
        try:
            if (
                isinstance(self.screen, ModalScreen)
                and action not in self._MODAL_SAFE_ACTIONS
            ):
                return False
        except Exception:
            pass
        return super().check_action(action, parameters)

    def __init__(self) -> None:
        super().__init__()
        from textual.theme import Theme

        self.register_theme(
            Theme(
                name="matrix",
                primary="#00ff41",
                secondary="#33ff00",
                warning="#ffd500",
                error="#ff0033",
                success="#00ff41",
                accent="#00cc88",
                foreground="#00ff41",
                background="#000000",
                surface="#0a1a0a",
                panel="#062206",
                boost="#00ff41",
                dark=True,
                variables={
                    "footer-key-foreground": "#012601",
                    "footer-key-background": "#00ff41",
                    "footer-description-foreground": "#65ff9f",
                    "footer-description-background": "#011001",
                },
            )
        )
        self.theme = "matrix"
        self.config: dict = load_config()
        try:
            if self.config.get("theme") in self.available_themes:
                self.theme = self.config["theme"]
        except Exception:
            pass
        self.store = TodoStore.load()
        self.templates: dict[str, list[dict]] = load_templates()
        self.filter_state: str | None = self.config.get("filter_state", "attivo")
        if self.filter_state not in FILTER_STATES:
            self.filter_state = "attivo"
        self.filter_tag: str | None = None
        self.filter_project: str | None = None
        self.filter_search: str = ""
        self._row_map: list[TodoItem] = []
        self._undo_stack: list[list[TodoItem]] = []
        self._reminded: set[tuple] = set()
        self.focus_task_id: int | None = None
        self.focus_end: datetime | None = None
        self.focus_paused_secs: int | None = None
        self.focus_phase: str | None = None  # None=pronto, altrimenti focus/short/long
        self.focus_total_secs: int = 25 * 60
        self.POMODORO_MIN = 25
        self.POMO_SHORT_MIN = 5
        self.POMO_LONG_MIN = 15
        self.POMO_LONG_EVERY = 4
        self.pomo_cycle = 0
        self._pending_pomo: dict = load_pomodoro()
        try:
            self.POMODORO_MIN = int(self._pending_pomo.get("default_minutes", 25))
        except (ValueError, TypeError):
            self.POMODORO_MIN = 25
        self.focus_total_secs = self.POMODORO_MIN * 60

    def export_screenshot(
        self, *, title: str | None = None, simplify: bool = False
    ) -> str:
        try:
            return super().export_screenshot(title=title, simplify=simplify)
        except KeyError:
            orig_theme = self.theme
            try:
                self.theme = "textual-dark"
                return super().export_screenshot(title=title, simplify=simplify)
            finally:
                self.theme = orig_theme

    @property
    def todos(self) -> list[TodoItem]:
        """Compat: lista live dallo store (solo lettura; mutare via store)."""
        return self.store.all()

    @todos.setter
    def todos(self, value: list[TodoItem]) -> None:
        self.store.replace_all(value)

    @property
    def next_id(self) -> int:
        return self.store.next_id

    @next_id.setter
    def next_id(self, value: int) -> None:
        self.store.next_id = value

    def _save_data(self) -> None:
        self.store.commit()

    def _commit_refresh(self, notify_key: str | None = None, **params) -> None:
        """Salva su disco, riaggiorna la tabella e (opzionale) notifica.

        Pattern standard delle action: muta -> commit -> refresh -> notify."""
        self._save_data()
        self._populate_table()
        if notify_key is not None:
            self.notify(T(notify_key, **params))

    def _on_plan_changed(self) -> None:
        """Callback delle screen di pianificazione: salva e aggiorna la tabella."""
        self._save_data()
        self._populate_table()

    def _save_config(self) -> None:
        try:
            save_config(self.config)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Header()
        yield ClickableDataTable(id="todo-table")
        yield Static(
            "",
            id="kanban-bar",
            classes="" if self.config.get("kanban_visible", True) else "hidden",
        )
        yield Static("", id="pomodoro-bar", classes="hidden")
        yield Static(self._stats_text(), id="stats-bar")
        yield Static(self._help_text(), id="help-panel", classes="hidden")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        table.add_columns(
            T("col_id"),
            T("col_state"),
            T("col_title"),
            T("col_proj"),
            T("col_tags"),
            T("col_notes"),
            T("col_prio"),
            T("col_recur"),
            T("col_due"),
        )
        table.cursor_type = "row"
        try:
            self.set_interval(1, self._tick_focus)
        except Exception:
            pass
        try:
            self.set_interval(30, self._check_reminders)
        except Exception:
            pass
        self._populate_table()
        if _needs_unlock() and not _crypto.is_unlocked():
            self.push_screen(LockScreen(), self._on_unlocked)
            return
        self._continue_startup(reload=False)

    def _on_unlocked(self, ok: bool | None) -> None:
        if not ok:
            self.exit()
            return
        self._continue_startup(reload=True)

    def _continue_startup(self, reload: bool) -> None:
        if reload:
            self._reload_all()
        else:
            self._pending_pomo = load_pomodoro()
            self._restore_pomodoro()
            self._auto_backup()
        if not self.todos:
            self.query_one("#help-panel").remove_class("hidden")
            if not self.config.get("onboarded"):
                self.push_screen(WelcomeScreen(), self._on_welcome)
            else:
                self.notify(T("n_welcome"))
        try:
            self._check_reminders()
        except Exception:
            pass

    def _on_welcome(self, choice: str | None) -> None:
        self.config["onboarded"] = True
        self._save_config()
        if choice == "demo":
            self.store.replace_all(_demo_todos(self.store.next_id))
            self._commit_refresh("n_welcome_demo")
        else:
            self.notify(T("n_welcome"))

    def _help_text(self) -> str:
        return "\n".join(T(f"help_l{i}") for i in range(1, 6))

    def _stats_text(self) -> str:
        parents = [t for t in self.todos if not t.is_subtask]
        attivi = sum(1 for t in parents if t.state == "attivo")
        sospesi = sum(1 for t in parents if t.state == "in_sospeso")
        completati = sum(1 for t in parents if t.state == "completato")
        sub_count = sum(1 for t in self.todos if t.is_subtask)
        planned_count = sum(
            1
            for t in self.todos
            if t.planned_for == datetime.now().strftime("%Y-%m-%d")
        )
        base = f" O:{attivi} P:{sospesi} X:{completati} | Sub:{sub_count} Piano:{planned_count}"
        if getattr(self, "focus_task_id", None):
            base += f" | 🍅 {self._focus_label()}"
        active_filter = (
            self.filter_state is not None
            or self.filter_tag is not None
            or getattr(self, "filter_project", None)
            or getattr(self, "filter_search", "")
        )
        if not active_filter:
            return f"{base} | {T('bar_all')}"
        parts = []
        if self.filter_state is not None:
            parts.append(T("bar_filter", v=self.filter_state.replace("_", " ")))
        if self.filter_tag is not None:
            parts.append(T("bar_tag", v=_escape_markup(self.filter_tag)))
        if getattr(self, "filter_project", None):
            parts.append(T("bar_proj", v=_escape_markup(self.filter_project or "")))
        if getattr(self, "filter_search", ""):
            parts.append(T("bar_search", v=_escape_markup(self.filter_search)))
        return f"{base} | [black on yellow] {' + '.join(parts)} [/]"

    def _kanban_text(self) -> str:
        def top(state: str) -> str:
            items = [t for t in self.todos if not t.is_subtask and t.state == state]
            items = sorted(items, key=self._sort_key)[:3]
            if not items:
                return "-"
            return " · ".join(f"#{t.id} {_escape_markup(t.title[:18])}" for t in items)

        n_att = sum(1 for t in self.todos if not t.is_subtask and t.state == "attivo")
        n_sos = sum(
            1 for t in self.todos if not t.is_subtask and t.state == "in_sospeso"
        )
        n_fat = sum(
            1 for t in self.todos if not t.is_subtask and t.state == "completato"
        )
        return (
            f"{T('kb_head')}\n"
            f" [red]○ {T('kb_attivo')} ({n_att})[/red]: {top('attivo')}\n"
            f" [yellow]◐ {T('kb_sospeso')} ({n_sos})[/yellow]: {top('in_sospeso')}\n"
            f" [green]● {T('kb_fatto')} ({n_fat})[/green]: {top('completato')}"
        )

    def _update_kanban(self) -> None:
        try:
            self.query_one("#kanban-bar", Static).update(self._kanban_text())
        except Exception:
            pass

    def _get_parents(self) -> list[TodoItem]:
        ids = {t.id for t in self.todos}
        # Gli orfani (parent_id puntato a id inesistente) vengono mostrati come radici
        # invece di sparire dalla tabella.
        return [t for t in self.todos if not t.is_subtask or t.parent_id not in ids]

    def _matches_state(self, todo: TodoItem) -> bool:
        if self.filter_state is None:
            return True
        target = {
            "attivo": "attivo",
            "in_sospeso": "in_sospeso",
            "completati": "completato",
        }[self.filter_state]
        if todo.state == target:
            return True
        return any(self._matches_state(sub) for sub in self._get_subtasks(todo.id))

    def _matches_tag(self, todo: TodoItem) -> bool:
        if self.filter_tag is None:
            return True
        if self.filter_tag in todo.tags:
            return True
        return any(self._matches_tag(sub) for sub in self._get_subtasks(todo.id))

    def _sort_key(self, todo: TodoItem):
        due_key = todo.due if _is_valid_due(todo.due) and todo.due else "9999-99-99"
        return (due_key, PRIORITY_ORDER.get(todo.priority.value, 9), todo.title.lower())

    def _matches_project(self, todo: TodoItem) -> bool:
        if not getattr(self, "filter_project", None):
            return True
        if todo.project == self.filter_project:
            return True
        return any(self._matches_project(sub) for sub in self._get_subtasks(todo.id))

    def _matches_search(self, todo: TodoItem) -> bool:
        q = (getattr(self, "filter_search", "") or "").strip().lower()
        if not q:
            return True
        hay = f"{todo.title} {todo.notes} {todo.project} {' '.join(todo.tags)}".lower()
        if q in hay:
            return True
        return any(self._matches_search(sub) for sub in self._get_subtasks(todo.id))

    def _filtered_todos(self) -> list[TodoItem]:
        parents = self._get_parents()
        if self.filter_state is not None:
            parents = [t for t in parents if self._matches_state(t)]
        if self.filter_tag is not None:
            parents = [t for t in parents if self._matches_tag(t)]
        if getattr(self, "filter_project", None):
            parents = [t for t in parents if self._matches_project(t)]
        if getattr(self, "filter_search", ""):
            parents = [t for t in parents if self._matches_search(t)]
        return sorted(parents, key=self._sort_key)

    def _get_subtasks(self, parent_id: int | None) -> list[TodoItem]:
        return self.store.children(parent_id)

    def _get_depth(self, todo: TodoItem) -> int:
        return self.store.depth(todo)

    def _get_all_descendants(self, todo_id: int | None) -> list[TodoItem]:
        return self.store.descendants(todo_id)

    def _populate_table(self) -> None:
        table = self.query_one("#todo-table", DataTable)
        selected = self._get_selected_todo()
        selected_id = selected.id if selected else None
        table.clear()
        self._row_map = []
        for todo in self._filtered_todos():
            self._add_todo_rows(table, todo, depth=0, prefix="", is_last=True)
        if not self._row_map:
            table.add_row(
                "-",
                "-",
                T("table_empty"),
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
            )
        elif selected_id is not None:
            for idx, t in enumerate(self._row_map):
                if t.id == selected_id:
                    try:
                        table.move_cursor(row=idx, scroll=True)
                    except Exception:
                        pass
                    break
        self.query_one("#stats-bar", Static).update(self._stats_text())
        self._update_kanban()
        self._update_pomodoro_bar()

    def _add_todo_rows(
        self, table: DataTable, todo: TodoItem, depth: int, prefix: str, is_last: bool
    ) -> None:
        status = f"{_status(todo)}{' ○' if todo.state == 'attivo' else ' ◐' if todo.state == 'in_sospeso' else ' ●'}"
        priority_str = f"[{todo.priority.color}]{prio_disp(todo.priority.value)}[/]"
        raw_notes = (
            todo.notes.replace("- [ ]", "☐").replace("- [x]", "☑").replace("- [X]", "☑")
        )
        notes_preview = (
            (raw_notes[:30] + "...") if len(raw_notes) > 30 else (raw_notes or "-")
        )
        notes_preview = _escape_markup(notes_preview)
        recurrence_str = (
            f"[cyan]{rec_disp(todo.recurrence.value)}[/]"
            if todo.recurrence != Recurrence.NONE
            else "-"
        )
        tags_str = (
            ", ".join(f"[magenta]#{_escape_markup(t)}[/]" for t in todo.tags)
            if todo.tags
            else "-"
        )
        project_str = (
            f"[blue]{_escape_markup(todo.project)}[/]" if todo.project else "-"
        )

        if depth == 0:
            title_display = _escape_markup(todo.title)
        else:
            connector = "└── " if is_last else "├── "
            title_display = f"{prefix}{connector}{_escape_markup(todo.title)}"
        # Progresso figli + pomodori
        children = self._get_subtasks(todo.id)
        if children:
            done_c = sum(1 for c in children if c.done)
            title_display += f" [dim]({done_c}/{len(children)})[/]"
        if todo.pomodoros or getattr(todo, "stima_pomo", 0):
            title_display += f" [red]{_pomo_label(todo)}[/]"
        if todo.done:
            title_display = f"[strike]{title_display}[/strike]"

        table.add_row(
            str(todo.id),
            status,
            title_display,
            project_str,
            tags_str,
            notes_preview,
            priority_str,
            recurrence_str,
            todo.due or "-",
        )
        self._row_map.append(todo)

        if depth < MAX_DEPTH:
            subtasks = self._get_subtasks(todo.id)
            if self.filter_state is not None:
                subtasks = [s for s in subtasks if self._matches_state(s)]
            if self.filter_tag is not None:
                subtasks = [s for s in subtasks if self._matches_tag(s)]
            if getattr(self, "filter_project", None):
                subtasks = [s for s in subtasks if self._matches_project(s)]
            if getattr(self, "filter_search", ""):
                subtasks = [s for s in subtasks if self._matches_search(s)]
            subtasks = sorted(subtasks, key=self._sort_key)
            for i, sub in enumerate(subtasks):
                is_last_sub = i == len(subtasks) - 1
                if depth == 0:
                    new_prefix = ""
                else:
                    new_prefix = prefix + ("    " if is_last else "│   ")
                self._add_todo_rows(table, sub, depth + 1, new_prefix, is_last_sub)

    def _get_selected_todo(self) -> TodoItem | None:
        table = self.query_one("#todo-table", DataTable)
        if not table.rows:
            return None
        row_idx = table.cursor_row
        if 0 <= row_idx < len(self._row_map):
            return self._row_map[row_idx]
        return None

    def action_new_todo(self) -> None:
        def on_submit(result: dict | None) -> None:
            if result:
                todo = TodoItem(
                    title=result["title"],
                    priority=result["priority"],
                    due=result["due"],
                    notes=result["notes"],
                    recurrence=result["recurrence"],
                    tags=result["tags"],
                    project=result.get("project", ""),
                    stima_pomo=result.get("stima_pomo", 0),
                    todo_id=self.store.allocate_id(),
                )
                self.store.add(todo)
                self._commit_refresh("n_added", t=_escape_markup(todo.title))

        self.push_screen(TodoFormScreen(title=T("form_new")), on_submit)

    def action_edit_todo(self) -> None:
        todo = self._get_selected_todo()
        if not todo:
            self.notify(T("n_nosel"), severity="warning")
            return
        self._open_edit_form(todo)

    def _open_edit_form(self, todo: TodoItem, reopen_detail: bool = False) -> None:
        def on_submit(result: dict | None) -> None:
            if result:
                domain.apply_form(todo, result)
                self._commit_refresh("n_updated", t=_escape_markup(todo.title))
                if reopen_detail:
                    self.push_screen(
                        DetailScreen(todo, self.todos), self._on_detail_closed
                    )

        self.push_screen(TodoFormScreen(todo=todo, title=T("form_edit")), on_submit)

    def _on_detail_closed(self, choice: str | None) -> None:
        # Callback riusabile quando il dettaglio viene richiuso dopo una modifica:
        # al momento non serve riaprire altro, il dettaglio aggiornato e' gia' visibile.
        return

    def action_delete_todo(self) -> None:
        todo = self._get_selected_todo()
        if not todo:
            self.notify(T("n_nosel"), severity="warning")
            return

        descendants = self._get_all_descendants(todo.id)
        msg = T("n_del_t", t=_escape_markup(todo.title))
        if descendants:
            msg += T("n_del_sub", n=len(descendants))

        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                desc_ids = {d.id for d in descendants}
                removed = self.store.remove_ids({todo.id} | desc_ids)
                self._undo_stack.append(removed)
                self._commit_refresh("n_deleted", t=_escape_markup(todo.title))

        self.push_screen(ConfirmScreen(msg), on_confirm)

    def action_toggle_done(self) -> None:
        todo = self._get_selected_todo()
        if not todo:
            self.notify(T("n_nosel"), severity="warning")
            return
        if not self._row_map or todo.id is None:
            return
        current_label = {
            "attivo": T("state_attivo"),
            "in_sospeso": T("state_sospeso"),
            "completato": T("state_completato"),
        }[todo.state]

        def on_pick(choice: str | None) -> None:
            if choice is None or choice == todo.state:
                return
            self._apply_state(todo, choice)

        self.push_screen(
            StateChoiceScreen(todo.title, current_label, todo.state), on_pick
        )

    def _apply_state(self, todo: TodoItem, choice: str) -> None:
        labels = {
            "attivo": T("n_to_active"),
            "in_sospeso": T("n_to_paused"),
            "completato": T("n_to_done"),
        }
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_todo = domain.apply_state(todo, choice, now)
        if new_todo is not None:
            self.store.add(new_todo)
            self.notify(T("n_recur", t=_escape_markup(new_todo.title), d=new_todo.due))
        self._commit_refresh("n_state", t=_escape_markup(todo.title), s=labels[choice])

    def action_add_subtask(self) -> None:
        todo = self._get_selected_todo()
        if not todo:
            self.notify(T("n_nosel"), severity="warning")
            return
        current_depth = self._get_depth(todo)
        if current_depth >= MAX_DEPTH:
            self.notify(T("n_maxdepth", n=MAX_DEPTH), severity="error")
            return
        parent_id = todo.id
        parent_title = todo.title
        parent_project = todo.project

        def on_submit(result: dict | None) -> None:
            if result:
                sub = TodoItem(
                    title=result["title"],
                    priority=result["priority"],
                    due=result["due"],
                    notes=result["notes"],
                    parent_id=parent_id,
                    todo_id=self.store.allocate_id(),
                    recurrence=result["recurrence"],
                    tags=result["tags"],
                    project=result.get("project", "") or parent_project,
                    stima_pomo=result.get("stima_pomo", 0),
                )
                self.store.add(sub)
                self._commit_refresh("n_sub_added", s=sub.title, p=parent_title)

        self.push_screen(
            TodoFormScreen(
                title=T("form_sub", parent=parent_title), preset_project=parent_project
            ),
            on_submit,
        )

    def action_view_detail(self) -> None:
        todo = self._get_selected_todo()
        if not todo:
            self.notify(T("n_nosel"), severity="warning")
            return

        def on_detail(choice: str | None) -> None:
            if choice == "edit":
                self._open_edit_form(todo, reopen_detail=True)

        self.push_screen(DetailScreen(todo, self.todos), on_detail)

    def on_data_table_row_selected(self, event) -> None:
        # Guardia anti-doppio-push: un singolo click puo' generare due RowSelected
        # (manuale + highlight-click nativo). Se il dettaglio e' gia' aperto, ignora.
        if isinstance(self.screen, DetailScreen):
            return
        self.action_view_detail()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        # TextArea a altezza fissa resta indietro di una riga: forza il
        # follow del cursore dopo il refresh (note, task template).
        try:
            ta = event.control
            if isinstance(ta, TextArea):
                self.call_after_refresh(ta.scroll_cursor_visible, animate=False)
        except Exception:
            pass

    def action_view_workflow(self) -> None:
        self.push_screen(WorkflowScreen())

    def action_view_agenda(self) -> None:
        self.push_screen(AgendaScreen(self.todos))

    def action_view_calendar(self) -> None:
        today = datetime.now().date()
        self.push_screen(CalendarScreen(self.todos, today.year, today.month))

    def action_open_day(self, year: int, month: int, day: int) -> None:
        date_str = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        todos = [
            t
            for t in self.todos
            if _due_date_part(t.due) == date_str and t.state != "completato"
        ]
        self.push_screen(DayScreen(date_str, todos))

    def action_view_daily_plan(self) -> None:
        self.push_screen(
            DailyPlanScreen(self.todos, self._on_plan_changed, on_add=self.store.add)
        )

    def action_open_review(self) -> None:
        try:
            goal = int(self.config.get("daily_goal", 0) or 0)
        except (ValueError, TypeError):
            goal = 0
        self.push_screen(
            ReviewScreen(self.todos, self._on_plan_changed, daily_goal=goal)
        )

    def action_plan_day(self) -> None:
        try:
            hours = float(self.config.get("day_hours", 6) or 6)
        except (ValueError, TypeError):
            hours = 6.0
        self.push_screen(
            PlanProposalScreen(self.todos, self._on_plan_changed, hours=hours)
        )

    def _briefing_evening(self) -> None:
        try:
            goal = int(self.config.get("daily_goal", 0) or 0)
        except (ValueError, TypeError):
            goal = 0

        def on_print(m: str, day: str, text: str):
            out_dir = _home() / "CarpeDiem_screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"carpediem_briefing_{m}_{day.replace('-', '')}.md"
            path.write_text(text, encoding="utf-8")
            return path

        def on_briefing_done(result: str | None) -> None:
            if result == "review":
                self.action_open_review()

        self.push_screen(
            BriefingScreen(self.todos, daily_goal=goal, on_print=on_print),
            on_briefing_done,
        )

    def action_briefing_evening(self) -> None:
        self._briefing_evening()

    def action_view_stats(self) -> None:
        self.push_screen(
            StatsScreen(
                self.todos,
                self.config.get("daily_goal", 5),
                self.config.get("weekly_goal", 25),
                self.config.get("pomo_daily_goal", 8),
            )
        )

    def action_filter_todos(self) -> None:
        order = ["attivo", "in_sospeso", "completati", None]
        labels = {
            "attivo": T("n_f_attivo"),
            "in_sospeso": T("n_f_sospeso"),
            "completati": T("n_f_fatti"),
            None: T("n_f_tutti"),
        }
        idx = order.index(self.filter_state)
        self.filter_state = order[(idx + 1) % len(order)]
        self.config["filter_state"] = self.filter_state
        self._save_config()
        self.notify(T("n_filter", v=labels[self.filter_state]))
        self._populate_table()

    def action_clear_filters(self) -> None:
        """Pulisce stato, tag, progetto e ricerca in un colpo (solo dal menu)."""
        self.filter_state = None
        self.filter_tag = None
        self.filter_project = None
        self.filter_search = ""
        self.config["filter_state"] = None
        self._save_config()
        self._populate_table()
        self.notify(T("n_filters_clear"))

    def action_filter_by_tag(self) -> None:
        all_tags = sorted({t for todo in self.todos for t in todo.tags})
        if not all_tags:
            self.notify(T("n_notags"), severity="warning")
            return
        # Ciclo: tutti -> primo tag -> ... -> ultimo tag -> tutti
        order: list[str | None] = [None] + all_tags
        try:
            idx = order.index(self.filter_tag)
        except ValueError:
            idx = 0
        self.filter_tag = order[(idx + 1) % len(order)]
        if self.filter_tag is None:
            self.notify(T("n_ftag_all"))
        else:
            self.notify(T("n_ftag", t=_escape_markup(self.filter_tag)))
        self._populate_table()

    def action_filter_by_project(self) -> None:
        all_projects = sorted({t.project for t in self.todos if t.project})
        if not all_projects:
            self.notify(T("n_noproj"), severity="warning")
            return
        order: list[str | None] = [None] + all_projects
        try:
            idx = order.index(self.filter_project)
        except ValueError:
            idx = 0
        self.filter_project = order[(idx + 1) % len(order)]
        self.notify(
            T("n_fproj_all")
            if self.filter_project is None
            else T("n_fproj", p=_escape_markup(self.filter_project))
        )
        self._populate_table()

    def action_search_todos(self) -> None:
        def on_submit(result: str | None) -> None:
            if result is None:
                return
            self.filter_search = result
            self.notify(
                T("n_search_clear")
                if not result
                else T("n_search", q=_escape_markup(result))
            )
            self._populate_table()

        self.push_screen(SearchScreen(self.filter_search), on_submit)

    def action_view_week(self) -> None:
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        self.push_screen(WeekScreen(self.todos, monday))

    def _open_pomodoro_popup(self) -> None:
        self.push_screen(
            PomodoroScreen(
                self._pomodoro_state,
                self._pomodoro_pause_resume,
                self._pomodoro_stop,
                self._pomodoro_done,
                self._pomodoro_set_duration,
            )
        )

    def _phase_total_secs(self, phase: str) -> int:
        if phase == "short":
            return self.POMO_SHORT_MIN * 60
        if phase == "long":
            return self.POMO_LONG_MIN * 60
        return self.POMODORO_MIN * 60

    def _start_phase(self, phase: str, task_id: int | None) -> None:
        self.focus_phase = phase
        self.focus_task_id = task_id
        self.focus_total_secs = self._phase_total_secs(phase)
        self.focus_end = datetime.now() + timedelta(seconds=self.focus_total_secs)
        self.focus_paused_secs = None
        self._save_pomodoro()
        self._populate_table()

    def action_start_pomodoro(self) -> None:
        if self.focus_task_id is not None:
            # Timer già attivo: apri il popup ovunque tu sia, senza vincoli di selezione.
            self._open_pomodoro_popup()
            return
        todo = self._get_selected_todo()
        if not todo:
            self.notify(T("n_nosel"), severity="warning")
            return
        self._start_phase("focus", todo.id)
        self.notify(
            T("n_pomo_start", t=_escape_markup(todo.title), m=self.POMODORO_MIN)
        )
        self._open_pomodoro_popup()

    def action_pomodoro_pause(self) -> None:
        """Pausa/riprendi globale: funziona da ovunque, senza popup."""
        if self.focus_task_id is None:
            self.notify(T("n_pomo_none"), severity="warning")
            return
        self._pomodoro_pause_resume()

    def action_pomodoro_finish(self) -> None:
        """Completa il focus o salta la pausa (globale)."""
        if self.focus_task_id is None:
            self.notify(T("n_timer_none"), severity="warning")
            return
        self._pomodoro_done()

    def _cycle_dots(self) -> str:
        n = min(self.pomo_cycle, self.POMO_LONG_EVERY)
        return "●" * n + "○" * (self.POMO_LONG_EVERY - n)

    def _pomo_today_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        n = 0
        for t in self.todos:
            for ts in getattr(t, "pomodoro_log", []) or []:
                if str(ts)[:10] == today:
                    n += 1
        return n

    def _pomo_goal_text(self) -> str:
        goal = self.config.get("pomo_daily_goal", 8)
        try:
            goal = int(goal)
        except (ValueError, TypeError):
            goal = 0
        if goal <= 0:
            return ""
        return f" · oggi {self._pomo_today_count()}/{goal} 🍅"

    def _is_break(self) -> bool:
        return self.focus_phase in ("short", "long")

    def _pomodoro_text(self) -> str:
        todo = self.store.by_id(self.focus_task_id)
        name = _escape_markup(todo.title[:28]) if todo else f"#{self.focus_task_id}"
        plbl = _pomo_label(todo) if todo else ""
        total = f" ({plbl})" if plbl else ""
        secs = self._pomodoro_remaining_secs()
        clock = f"{secs // 60:02d}:{secs % 60:02d}"
        total_min = max(1, self.focus_total_secs // 60)
        dots = self._cycle_dots()
        x_key = "pomo_hint_skip" if self._is_break() else "pomo_hint_done"
        hints = (
            f" [dim][o] [@click=app.action_start_pomodoro][underline]{T('pomo_hint_open')}[/underline][/]"
            f"  [O] [@click=app.action_pomodoro_pause][underline]{T('pomo_hint_pause')}[/underline][/]"
            f"  [X] [@click=app.action_pomodoro_finish][underline]{T(x_key)}[/underline][/][/dim]"
        )
        if self.focus_paused_secs is not None:
            state = f"[yellow]⏸ {T('pomo_paused')} {clock}/{total_min:02d}:00[/yellow]"
        elif self._is_break():
            state = f"[green]☕ {T('pomo_phase_long') if self.focus_phase == 'long' else T('pomo_phase_short')} {clock}/{total_min:02d}:00 {dots}[/green]"
            return f" {state}  {T('pomo_break_after', name=name)}{self._pomo_goal_text()}{hints}"
        elif secs <= 60:
            state = f"[green]🍅 {clock}/{total_min:02d}:00 {dots} — {T('pomo_almost')}[/green]"
        else:
            state = f"[red]🍅 {clock}/{total_min:02d}:00 {dots}[/red]"
        return f" {state}  {name}{total}{self._pomo_goal_text()}{hints}"

    def _update_pomodoro_bar(self) -> None:
        try:
            bar = self.query_one("#pomodoro-bar", Static)
        except Exception:
            return
        if self.focus_task_id is None:
            bar.add_class("hidden")
            return
        bar.remove_class("hidden")
        bar.set_class(self.focus_paused_secs is not None, "paused")
        bar.set_class(self._is_break() and self.focus_paused_secs is None, "break")
        bar.update(self._pomodoro_text())

    def _pomodoro_remaining_secs(self) -> int:
        if self.focus_task_id is None:
            return 0
        if self.focus_paused_secs is not None:
            return self.focus_paused_secs
        if not self.focus_end:
            return 0
        return max(0, int((self.focus_end - datetime.now()).total_seconds()))

    def _pomodoro_state(self) -> dict:
        if self.focus_task_id is None:
            return {"empty": True}
        todo = self.store.by_id(self.focus_task_id)
        secs = self._pomodoro_remaining_secs()
        paused = self.focus_paused_secs is not None
        phase = self.focus_phase or "focus"
        is_break = phase in ("short", "long")
        total_min = max(1, self.focus_total_secs // 60)
        name = _escape_markup(todo.title) if todo else "-"
        plbl = _pomo_label(todo) if todo else ""
        count = f"  {plbl}" if plbl else ""
        dots = self._cycle_dots()
        if is_break:
            info = f"{T('pomo_break_after', name=name)}\n{T('pomo_cycle', dots=dots)}"
        else:
            coming = (
                T("pomo_next_long")
                if (self.pomo_cycle + 1) % self.POMO_LONG_EVERY == 0
                else T("pomo_next_short")
            )
            info = f"{name}{count}\n{T('pomo_cycle', dots=dots)} · {coming}"
        return {
            "empty": False,
            "clock": f"{secs // 60:02d}:{secs % 60:02d} / {total_min:02d}:00{T('pomo_paused_tag') if paused else ''}",
            "total_min": total_min,
            "task": f"{name}{count}",
            "info": info,
            "paused": paused,
            "phase": phase,
            "is_break": is_break,
            "presets": POMO_PHASE_PRESETS.get(phase, (15, 25, 50)),
        }

    def _pomodoro_set_duration(self, minutes: int) -> None:
        """Cambia la durata della fase corrente e riavvia da capo."""
        if self.focus_task_id is None:
            return
        phase = self.focus_phase or "focus"
        lo, hi = (1, 180) if phase == "focus" else (1, 60)
        if minutes not in range(lo, hi + 1):
            self.notify(T("n_dur_bad", lo=lo, hi=hi), severity="error")
            return
        if phase == "short":
            self.POMO_SHORT_MIN = minutes
        elif phase == "long":
            self.POMO_LONG_MIN = minutes
        else:
            self.POMODORO_MIN = minutes
        self.focus_total_secs = minutes * 60
        if self.focus_paused_secs is not None:
            self.focus_paused_secs = self.focus_total_secs
        else:
            self.focus_end = datetime.now() + timedelta(seconds=self.focus_total_secs)
        self._save_pomodoro()
        self._populate_table()
        self.notify(T("n_dur_set", m=minutes))

    def _save_pomodoro(self) -> None:
        if self.focus_task_id is None:
            session = None
        else:
            session = {
                "task_id": self.focus_task_id,
                "phase": self.focus_phase or "focus",
                "total_secs": self.focus_total_secs,
                "end": self.focus_end.isoformat() if self.focus_end else None,
                "paused_secs": self.focus_paused_secs,
            }
        save_pomodoro(
            {
                "default_minutes": self.POMODORO_MIN,
                "short_minutes": self.POMO_SHORT_MIN,
                "long_minutes": self.POMO_LONG_MIN,
                "long_every": self.POMO_LONG_EVERY,
                "cycle": self.pomo_cycle,
                "session": session,
            }
        )

    def _clear_pomodoro_state(self) -> None:
        self.focus_task_id = None
        self.focus_end = None
        self.focus_paused_secs = None
        self.focus_phase = None

    def _restore_pomodoro(self) -> None:
        """Ripristina ciclo e timer (focus o pausa) dall'ultima sessione salvata."""
        data = getattr(self, "_pending_pomo", None) or load_pomodoro()
        self.POMODORO_MIN = _clamp_int(data.get("default_minutes", 25), 25, 1, 180)
        self.POMO_SHORT_MIN = _clamp_int(data.get("short_minutes", 5), 5, 1, 60)
        self.POMO_LONG_MIN = _clamp_int(data.get("long_minutes", 15), 15, 1, 60)
        self.POMO_LONG_EVERY = _clamp_int(data.get("long_every", 4), 4, 2, 12)
        self.pomo_cycle = _clamp_int(data.get("cycle", 0), 0, 0, 1000)
        self.focus_total_secs = self.POMODORO_MIN * 60
        session = data.get("session")
        if not isinstance(session, dict):
            self._update_pomodoro_bar()
            return
        todo = self.store.by_id(session.get("task_id"))
        if todo is None:
            self._save_pomodoro()
            return
        phase = session.get("phase")
        phase = phase if isinstance(phase, str) and phase in POMO_PHASES else "focus"
        try:
            total = int(session.get("total_secs") or self._phase_total_secs(phase))
        except (ValueError, TypeError):
            total = self._phase_total_secs(phase)
        self.focus_task_id = todo.id
        self.focus_phase = phase
        self.focus_total_secs = total
        if session.get("paused_secs") is not None:
            try:
                self.focus_paused_secs = int(session["paused_secs"])
            except (ValueError, TypeError):
                self.focus_paused_secs = total
            self.focus_end = None
            self._populate_table()
            what = (
                T("pomo_what_break")
                if phase in ("short", "long")
                else T("pomo_what_focus")
            )
            self.notify(T("n_rest_paused", w=what, t=_escape_markup(todo.title)))
            return
        try:
            end = datetime.fromisoformat(str(session.get("end")))
        except (ValueError, TypeError):
            self._clear_pomodoro_state()
            self._save_pomodoro()
            self._populate_table()
            return
        # Consuma le fasi scadute ad app chiusa (focus -> pausa -> ...).
        credited = 0
        break_done: str | None = None
        for _ in range(6):
            if datetime.now() < end:
                break
            if phase == "focus":
                domain.credit_pomodoro(todo, end.strftime("%Y-%m-%d %H:%M"))
                self._save_data()
                credited += 1
                self.pomo_cycle += 1
                phase = (
                    "long" if self.pomo_cycle % self.POMO_LONG_EVERY == 0 else "short"
                )
                total = self._phase_total_secs(phase)
                end = end + timedelta(seconds=total)
                continue
            break_done = phase
            if phase == "long":
                self.pomo_cycle = 0
            phase = ""
            break
        if not phase:
            self._clear_pomodoro_state()
            self._save_pomodoro()
            self._populate_table()
            bits = []
            if credited:
                bits.append(T("n_rest_cred", n=credited))
            if break_done:
                bits.append(T("n_rest_breakdone"))
            head = ". ".join(bits) + ". " if bits else T("n_rest_expired") + ". "
            self.notify(
                head + T("n_rest_total", t=_escape_markup(todo.title), n=todo.pomodoros)
            )
            return
        self.focus_phase = phase
        self.focus_total_secs = total
        self.focus_end = end
        self.focus_paused_secs = None
        self._save_pomodoro()
        self._populate_table()
        what = (
            T("pomo_what_break") if phase in ("short", "long") else T("pomo_what_timer")
        )
        extra = T("n_rest_extra", n=credited) if credited else ""
        self.notify(
            T(
                "n_rest_active",
                icon="☕" if phase in ("short", "long") else "🍅",
                w=what,
                t=_escape_markup(todo.title),
                extra=extra,
            )
        )

    def _pomodoro_pause_resume(self) -> None:
        if self.focus_task_id is None:
            return
        if self.focus_paused_secs is not None:
            self.focus_end = datetime.now() + timedelta(seconds=self.focus_paused_secs)
            self.focus_paused_secs = None
            self.notify(T("n_resumed"))
        else:
            self.focus_paused_secs = self._pomodoro_remaining_secs()
            self.focus_end = None
            self.notify(T("n_paused"))
        self._save_pomodoro()
        self._populate_table()

    def _pomodoro_stop(self) -> None:
        self._clear_pomodoro_state()
        self._save_pomodoro()
        self._populate_table()
        self.notify(T("n_stopped"))

    def _complete_focus(self) -> None:
        todo = self.store.by_id(self.focus_task_id)
        if todo:
            domain.credit_pomodoro(todo, datetime.now().strftime("%Y-%m-%d %H:%M"))
            self._save_data()
        self.pomo_cycle += 1
        kind = "long" if self.pomo_cycle % self.POMO_LONG_EVERY == 0 else "short"
        task_id = self.focus_task_id
        self._start_phase(kind, task_id)
        dots = self._cycle_dots()
        mins = self.POMO_LONG_MIN if kind == "long" else self.POMO_SHORT_MIN
        name = f"su '{_escape_markup(todo.title)}'" if todo else ""
        self.notify(
            T(
                "n_focus_done",
                name=name,
                dots=dots,
                kind=T("pomo_long_w") if kind == "long" else T("pomo_short_w"),
                mins=mins,
            )
        )
        self._beep(1)

    def _finish_break(self, skipped: bool) -> None:
        was_long = self.focus_phase == "long"
        if was_long:
            self.pomo_cycle = 0
        self._clear_pomodoro_state()
        self._save_pomodoro()
        self._populate_table()
        if skipped:
            self.notify(T("n_skipped"))
        elif was_long:
            self.notify(T("n_long_done"))
            self._beep(2)
        else:
            self.notify(T("n_short_done"))
            self._beep(2)

    def _pomodoro_done(self) -> None:
        if self.focus_task_id is None:
            return
        if (self.focus_phase or "focus") == "focus":
            self._complete_focus()
        else:
            self._finish_break(skipped=True)

    def _expire_current(self) -> None:
        """Scadenza naturale del timer (dal tick): la pausa si completa, non si salta."""
        if self.focus_task_id is None:
            return
        if (self.focus_phase or "focus") == "focus":
            self._complete_focus()
        else:
            self._finish_break(skipped=False)

    def action_view_health(self) -> None:
        self.push_screen(HealthScreen(self.todos))

    def action_view_kanban(self) -> None:
        self.push_screen(KanbanScreen(self.todos))

    def action_toggle_kanban(self) -> None:
        bar = self.query_one("#kanban-bar", Static)
        bar.set_class(not bar.has_class("hidden"), "hidden")
        self.config["kanban_visible"] = not bar.has_class("hidden")
        self._save_config()
        if not bar.has_class("hidden"):
            self._update_kanban()
            self.notify(T("n_kb_show"))
        else:
            self.notify(T("n_kb_hide"))

    def _focus_label(self) -> str:
        if self.focus_task_id is None:
            return ""
        todo = self.store.by_id(self.focus_task_id)
        name = todo.title[:20] if todo else f"#{self.focus_task_id}"
        secs = self._pomodoro_remaining_secs()
        if self.focus_paused_secs is not None:
            tag = "⏸"
        else:
            tag = "☕" if self._is_break() else "🍅"
        return f"{tag} {name} {secs // 60:02d}:{secs % 60:02d}"

    def _tick_focus(self) -> None:
        if self.focus_task_id is None:
            return
        if self.focus_paused_secs is not None or not self.focus_end:
            return
        if datetime.now() >= self.focus_end:
            self._expire_current()
            return
        try:
            self.query_one("#stats-bar", Static).update(self._stats_text())
            self._update_pomodoro_bar()
        except Exception:
            pass

    def _beep(self, times: int = 1) -> None:
        if not self.config.get("sounds", True):
            return
        try:
            print("\a" * max(1, times), end="", flush=True)
        except Exception:
            pass

    def _check_reminders(self) -> None:
        """10 min prima della scadenza oraria: info + suono, una sola volta."""
        try:
            lead = int(self.config.get("reminder_min", 10))
        except (ValueError, TypeError):
            lead = 10
        if lead <= 0:
            return
        now = datetime.now()
        for t in self.todos:
            if t.state != "attivo" or not t.due or len(t.due.strip()) < 16:
                continue
            try:
                due_dt = datetime.strptime(t.due.strip()[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if not due_dt - timedelta(minutes=lead) <= now < due_dt:
                continue
            key = (t.id, due_dt.strftime("%Y-%m-%d %H:%M"))
            if key in self._reminded:
                continue
            self._reminded.add(key)
            mins = max(1, int((due_dt - now).total_seconds() // 60))
            self.notify(
                T("n_rem_due", n=mins, h=due_dt.strftime("%H:%M"), t=t.title),
                timeout=REMINDER_TOAST_TIMEOUT,
            )
            self._beep(REMINDER_BEEPS)

    def action_undo_delete(self) -> None:
        if not self._undo_stack:
            self.notify(T("n_nothing"), severity="warning")
            return
        restored = self._undo_stack.pop()
        self.store.add_many(restored)
        self._purge_archive({t.id for t in restored if t.id is not None})
        self._commit_refresh("n_restored", n=len(restored))

    def _purge_archive(self, ids: set) -> None:
        if not ids:
            return
        try:
            archive = load_archive()
            kept = [
                d for d in archive if not (isinstance(d, dict) and d.get("id") in ids)
            ]
            if len(kept) != len(archive):
                save_archive(kept)
        except Exception:
            pass

    def action_archive_done(self) -> None:
        roots = [t for t in self._get_parents() if t.state == "completato"]
        if not roots:
            self.notify(T("n_arc_none"), severity="warning")
            return
        all_ids = {t.id for t in roots}
        for t in roots:
            all_ids |= {d.id for d in self._get_all_descendants(t.id)}
        removed = [t for t in self.todos if t.id in all_ids]

        def on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                archive = load_archive()
                archive.extend([t.to_dict() for t in removed])
                save_archive(archive)
            except Exception as exc:
                self.notify(
                    T("n_arc_err", e=_escape_markup(str(exc))), severity="error"
                )
                return
            self._undo_stack.append(removed)
            self.store.remove_ids(all_ids)
            self._commit_refresh("n_archived", n=len(removed))

        self.push_screen(
            ConfirmScreen(T("n_arc_confirm", n=len(removed))),
            on_confirm,
        )

    def action_view_archive(self) -> None:
        items: list[TodoItem] = []
        for d in load_archive():
            if not isinstance(d, dict):
                continue
            try:
                items.append(TodoItem.from_dict(d))
            except Exception:
                continue
        items.sort(key=lambda t: (t.completed_at or "", t.title.lower()), reverse=True)
        self.push_screen(ArchiveScreen(items), self._on_archive_action)

    def _on_archive_action(self, result: tuple | None) -> None:
        if not result:
            return
        action, payload = result
        archive = load_archive()
        if action == "all":
            if not archive:
                return
            restored = 0
            for d in archive:
                if not isinstance(d, dict):
                    continue
                try:
                    t = TodoItem.from_dict(d)
                except Exception:
                    continue
                self.store.add(t)
                restored += 1
            save_archive([])
            self._commit_refresh("n_arc_emptied", n=restored)
            return
        if action == "one":
            try:
                idx = int(payload)
                raw = archive[idx]
            except (ValueError, TypeError, IndexError):
                return
            if not isinstance(raw, dict):
                return
            try:
                t = TodoItem.from_dict(raw)
            except Exception:
                return
            self.store.add(t)
            del archive[idx]
            save_archive(archive)
            self._commit_refresh("n_arc_one", t=t.title)
            self.action_view_archive()

    def action_new_from_template(self) -> None:
        self._open_template_picker()

    def _open_template_picker(self) -> None:
        self.push_screen(TemplateScreen(self.templates), self._on_template_action)

    def _persist_templates(self) -> None:
        save_templates(self.templates)

    def _on_template_action(self, result: tuple | None) -> None:
        if not result:
            return
        action, payload = result
        if action == "use":
            self._instantiate_template(payload)
        elif action == "delete":
            self._confirm_delete_template(payload)
        elif action == "new":
            self.push_screen(TemplateCreateScreen(), self._on_template_created)
        elif action == "edit":
            self._open_template_editor(payload)
        elif action == "from_project":
            self._open_template_from_project()

    def _instantiate_template(self, name: str) -> None:
        if not name or name not in self.templates:
            return
        created = []
        for item in self.templates[name]:
            todo = TodoItem(
                title=item["title"],
                priority=item.get("priority", Priority.MEDIUM),
                project=name.lower(),
            )
            self.store.add(todo)
            created.append(todo)
        self._commit_refresh("n_tpl_made", n=_escape_markup(name), c=len(created))

    def _confirm_delete_template(self, name: str) -> None:
        if name not in self.templates:
            return

        def on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                self._open_template_picker()
                return
            del self.templates[name]
            self._persist_templates()
            self.notify(T("n_tpl_del", n=_escape_markup(name)))
            self._open_template_picker()

        self.push_screen(
            ConfirmScreen(T("n_tpl_confirm", n=_escape_markup(name))), on_confirm
        )

    def _on_template_created(self, result: dict | None) -> None:
        if not result:
            self._open_template_picker()
            return
        name = str(result.get("name", "") or "").strip()
        if not name:
            self.notify(T("n_tpl_badname"), severity="error")
            self._open_template_picker()
            return
        if name in self.templates:
            self.notify(T("n_tpl_dup", n=_escape_markup(name)), severity="error")
            self._open_template_picker()
            return
        items = result.get("items", [])
        if not items:
            self.notify(T("n_tpl_empty"), severity="error")
            self._open_template_picker()
            return
        self.templates[name] = items
        self._persist_templates()
        self.notify(T("n_tpl_created", n=_escape_markup(name), c=len(items)))
        self._open_template_picker()

    def _open_template_editor(self, name: str) -> None:
        if not name or name not in self.templates:
            self._open_template_picker()
            return

        def on_edited(result: dict | None) -> None:
            if not result:
                self._open_template_picker()
                return
            new_name = str(result.get("name", "") or "").strip()
            items = result.get("items", [])
            if not new_name or not items:
                self.notify(T("n_tpl_need"), severity="error")
                self._open_template_picker()
                return
            if new_name != name and new_name in self.templates:
                self.notify(
                    T("n_tpl_dup", n=_escape_markup(new_name)), severity="error"
                )
                self._open_template_picker()
                return
            if new_name != name:
                del self.templates[name]
            self.templates[new_name] = items
            self._persist_templates()
            self.notify(T("n_tpl_updated", n=_escape_markup(new_name), c=len(items)))
            self._open_template_picker()

        self.push_screen(
            TemplateCreateScreen({"name": name, "items": self.templates[name]}),
            on_edited,
        )

    def _open_template_from_project(self) -> None:
        counts: dict[str, int] = {}
        for t in self.todos:
            if t.project:
                counts[t.project] = counts.get(t.project, 0) + 1
        if not counts:
            self.notify(T("n_tpl_noproj"), severity="warning")
            self._open_template_picker()
            return
        projects = sorted(counts.items(), key=lambda kv: kv[0])

        def on_pick(project: str | None) -> None:
            if not project:
                self._open_template_picker()
                return
            self._create_template_from_project(project)

        self.push_screen(TemplateProjectScreen(projects), on_pick)

    def _create_template_from_project(self, project: str) -> None:
        source = sorted(
            [t for t in self.todos if t.project == project],
            key=self._sort_key,
        )
        if not source:
            self.notify(
                T("n_tpl_emptyproj", p=_escape_markup(project)), severity="warning"
            )
            self._open_template_picker()
            return
        base = project.strip().capitalize() or project
        name = base
        suffix = 2
        while name in self.templates:
            name = f"{base} ({suffix})"
            suffix += 1
        self.templates[name] = [
            {"title": t.title, "priority": t.priority} for t in source
        ]
        self._persist_templates()
        self.notify(
            T(
                "n_tpl_fromproj",
                n=_escape_markup(name),
                p=_escape_markup(project),
                c=len(source),
            )
        )
        self._open_template_picker()

    def action_export_data(self) -> None:
        try:
            out_dir = _home() / "CarpeDiem_screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            md = out_dir / f"carpediem_export_{ts}.md"
            lines = ["# CarpeDiem export", ""]
            for t in sorted(self.todos, key=self._sort_key):
                box = "x" if t.done else " "
                proj = f" @{t.project}" if t.project else ""
                lines.append(
                    f"- [{box}] {t.title}{proj} (scad: {t.due or '-'}, prio: {t.priority.value})"
                )
            md.write_text("\n".join(lines), encoding="utf-8")
            self.notify(T("n_exp_saved", p=_escape_markup(str(md))))
        except Exception as exc:
            self.notify(T("n_exp_err", e=_escape_markup(str(exc))), severity="error")

    def action_export_ical(self) -> None:
        """Export calendario iCal (.ics) dei task non completati con scadenza."""
        try:
            out_dir = _home() / "CarpeDiem_screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ics_path = out_dir / f"carpediem_calendar_{ts}.ics"
            items = [
                t
                for t in self.todos
                if t.state != "completato" and _due_date_part(t.due)
            ]
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//CarpeDiem//CarpeDiem//IT",
                "CALSCALE:GREGORIAN",
            ]
            for t in sorted(items, key=lambda x: (x.due or "", self._sort_key(x))):
                date_part = _due_date_part(t.due)
                time_part = ""
                parts = (t.due or "").split()
                if len(parts) >= 2 and len(parts[1]) == 5 and parts[1][2] == ":":
                    time_part = parts[1]
                lines.extend(self._ical_event_lines(t, date_part, time_part, stamp))
            lines.append("END:VCALENDAR")
            ics_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
            self.notify(
                T("n_ical_saved", p=_escape_markup(str(ics_path)), n=len(items))
            )
        except Exception as exc:
            self.notify(T("n_ical_err", e=_escape_markup(str(exc))), severity="error")

    def _ical_event_lines(
        self, todo: TodoItem, date_part: str, time_part: str, stamp: str
    ) -> list[str]:
        uid = (
            f"carpediem-{todo.id or abs(hash((todo.title, todo.due)))}@carpediem.local"
        )
        desc_bits = []
        if todo.project:
            desc_bits.append(f"Progetto: {todo.project}")
        if todo.tags:
            desc_bits.append("Tags: " + ", ".join(todo.tags))
        desc_bits.append(f"Priorita: {prio_disp(todo.priority.value)}")
        if todo.notes:
            desc_bits.append(todo.notes)
        lines = [
            "BEGIN:VEVENT",
            f"UID:{self._ical_escape(uid)}",
            f"DTSTAMP:{stamp}",
            f"SUMMARY:{self._ical_escape(todo.title)}",
            f"DESCRIPTION:{self._ical_escape(chr(10).join(desc_bits))}",
        ]
        if time_part:
            start = date_part.replace("-", "") + "T" + time_part.replace(":", "") + "00"
            lines.append(f"DTSTART:{start}")
        else:
            start = date_part.replace("-", "")
            try:
                end = (
                    datetime.strptime(date_part, "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y%m%d")
            except ValueError:
                end = start
            lines.append(f"DTSTART;VALUE=DATE:{start}")
            lines.append(f"DTEND;VALUE=DATE:{end}")
        lines.append("END:VEVENT")
        return lines

    def _ical_escape(self, value: str) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    def action_export_stats_csv(self) -> None:
        """Export aggregati giornalieri (CSV): data, completati, pomodori."""
        import csv

        try:
            by_date: dict[str, int] = {}
            for t in self.todos:
                if t.completed_at:
                    k = t.completed_at[:10]
                    by_date[k] = by_date.get(k, 0) + 1
            pomo_by_date: dict[str, int] = {}
            for t in self.todos:
                for ts in getattr(t, "pomodoro_log", []) or []:
                    k = str(ts)[:10]
                    pomo_by_date[k] = pomo_by_date.get(k, 0) + 1
            days = sorted(set(by_date) | set(pomo_by_date))
            out_dir = _home() / "CarpeDiem_screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = out_dir / f"carpediem_stats_{ts}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["data", "completati", "pomodori"])
                for d in days:
                    writer.writerow([d, by_date.get(d, 0), pomo_by_date.get(d, 0)])
            self.notify(T("n_stat_saved", p=_escape_markup(str(csv_path)), d=len(days)))
        except Exception as exc:
            self.notify(T("n_stat_err", e=_escape_markup(str(exc))), severity="error")

    def action_export_csv(self) -> None:
        """Export foglio di calcolo (CSV) in ~/CarpeDiem_screenshots."""
        import csv

        try:
            out_dir = _home() / "CarpeDiem_screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = out_dir / f"carpediem_export_{ts}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "id",
                        "titolo",
                        "stato",
                        "priorita",
                        "scadenza",
                        "progetto",
                        "tags",
                        "creazione",
                        "completato_il",
                        "pomodori",
                        "stima_pomo",
                        "padre",
                        "note",
                    ]
                )
                for t in sorted(self.todos, key=self._sort_key):
                    writer.writerow(
                        [
                            t.id,
                            t.title,
                            t.state,
                            t.priority.value,
                            t.due or "",
                            t.project or "",
                            ";".join(t.tags),
                            t.created or "",
                            t.completed_at or "",
                            t.pomodoros,
                            t.stima_pomo,
                            t.parent_id if t.parent_id is not None else "",
                            (t.notes or "").replace("\r", " "),
                        ]
                    )
            self.notify(
                T("n_csv_saved", p=_escape_markup(str(csv_path)), n=len(self.todos))
            )
        except Exception as exc:
            self.notify(T("n_csv_err", e=_escape_markup(str(exc))), severity="error")

    def action_import_csv(self) -> None:
        try:
            out_dir = _home() / "CarpeDiem_screenshots"
            files = (
                sorted(
                    out_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True
                )
                if out_dir.exists()
                else []
            )
        except OSError:
            files = []

        def on_pick(path: str | None) -> None:
            if not path:
                return
            try:
                imported, skipped = self._import_csv_file(path)
            except Exception as exc:
                self.notify(
                    T("n_imp_err", e=_escape_markup(str(exc))), severity="error"
                )
                return
            if imported:
                self._save_data()
                self._populate_table()
            msg = T("n_imp_ok", n=imported, f=Path(path).name)
            if skipped:
                msg += T("n_imp_skip", s=skipped)
            self.notify(msg, severity="information" if imported else "warning")

        self.push_screen(ImportCsvScreen(files[:20]), on_pick)

    def _import_csv_file(self, path: str) -> tuple[int, int]:
        """Importa task da CSV (formato export o compatibile). Ritorna (importati, scartati)."""
        import csv

        p = Path(str(path).strip()).expanduser()
        pr_map = {
            "alta": Priority.HIGH,
            "high": Priority.HIGH,
            "media": Priority.MEDIUM,
            "medium": Priority.MEDIUM,
            "bassa": Priority.LOW,
            "low": Priority.LOW,
        }
        with open(p, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0, 0
            cols = {c.strip().lower(): c for c in reader.fieldnames if c and c.strip()}

            def col(*names: str) -> str:
                for n in names:
                    if n in cols:
                        v = row.get(cols[n])
                        return str(v or "").strip()
                return ""

            raw_rows: list[dict | None] = []
            for row in reader:
                if not isinstance(row, dict):
                    continue
                title = col("titolo", "title", "name", "task")
                if not title:
                    raw_rows.append(None)
                    continue
                state = col("stato", "state", "status").lower()
                priority = pr_map.get(
                    col("priorita", "priority").lower(), Priority.MEDIUM
                )
                tags_raw = col("tags", "tag", "etichette")
                tags = [
                    t.strip().lower()
                    for t in tags_raw.replace(";", ",").split(",")
                    if t.strip()
                ]
                try:
                    pomodoros = int(col("pomodori", "pomodoros") or 0)
                except (ValueError, TypeError):
                    pomodoros = 0
                try:
                    stima = max(0, int(col("stima_pomo", "stima", "estimate") or 0))
                except (ValueError, TypeError):
                    stima = 0
                try:
                    old_parent = int(col("padre", "parent_id", "parent") or 0) or None
                except (ValueError, TypeError):
                    old_parent = None
                try:
                    old_id = int(col("id") or 0) or None
                except (ValueError, TypeError):
                    old_id = None
                raw_rows.append(
                    {
                        "old_id": old_id,
                        "title": title,
                        "priority": priority,
                        "done": state
                        in ("completato", "completed", "done", "x", "true", "1"),
                        "paused": state
                        in ("in_sospeso", "sospeso", "paused", "suspended"),
                        "due": _normalize_date(col("scadenza", "due", "deadline")),
                        "notes": col("note", "notes", "descrizione"),
                        "project": col("progetto", "project"),
                        "tags": tags,
                        "created": col("creazione", "created"),
                        "completed_at": col("completato_il", "completed_at")[:16],
                        "pomodoros": pomodoros,
                        "stima_pomo": stima,
                        "old_parent": old_parent,
                    }
                )
        # Rimappa gli id (padri compresi) sui nuovi.
        id_map: dict[int, int] = {}
        created: list[TodoItem] = []
        pending_parents: list = []
        skipped = 0
        for raw in raw_rows:
            if raw is None:
                skipped += 1
                continue
            assert raw is not None
            nid = self.store.allocate_id()
            todo = TodoItem(
                title=raw["title"],
                priority=raw["priority"],
                done=raw["done"],
                paused=raw["paused"] and not raw["done"],
                created=raw["created"] or datetime.now().strftime("%Y-%m-%d %H:%M"),
                due=raw["due"],
                notes=raw["notes"],
                project=raw["project"],
                tags=raw["tags"],
                completed_at=raw["completed_at"] if raw["done"] else "",
                pomodoros=raw["pomodoros"],
                stima_pomo=raw.get("stima_pomo", 0),
                todo_id=nid,
            )
            if raw["old_id"] is not None:
                id_map[raw["old_id"]] = nid
            pending_parents.append(raw["old_parent"])
            created.append(todo)
        for todo, old_parent in zip(created, pending_parents):
            if old_parent is not None and old_parent in id_map:
                todo.parent_id = id_map[old_parent]
        self.store.add_many(created)
        return len(created), skipped

    def action_edit_goals(self) -> None:
        def on_submit(result: dict | None) -> None:
            if not result:
                return
            self.config["daily_goal"] = result["daily"]
            self.config["weekly_goal"] = result["weekly"]
            self.config["pomo_daily_goal"] = result["pomo_daily"]
            self._save_config()
            self._populate_table()
            self.notify(
                T(
                    "n_goals_saved",
                    d=result["daily"],
                    w=result["weekly"],
                    p=result["pomo_daily"],
                )
            )

        self.push_screen(
            GoalsScreen(
                self.config.get("daily_goal", 5),
                self.config.get("weekly_goal", 25),
                self.config.get("pomo_daily_goal", 8),
            ),
            on_submit,
        )

    def action_open_settings(self) -> None:
        def on_submit(result: dict | None) -> None:
            if not result:
                return
            try:
                self.theme = result["theme"]
            except Exception as exc:
                self.notify(
                    T("n_theme_bad", e=_escape_markup(str(exc))), severity="error"
                )
                return
            self.config["theme"] = result["theme"]
            self.config["kanban_visible"] = result["kanban_visible"]
            self.config["filter_state"] = result["filter_state"]
            self.config["daily_goal"] = result["daily_goal"]
            self.config["weekly_goal"] = result["weekly_goal"]
            self.config["pomo_daily_goal"] = result["pomo_daily_goal"]
            self.config["reminder_min"] = result["reminder_min"]
            self.config["day_hours"] = result["day_hours"]
            self.config["sounds"] = result["sounds"]
            old_lang = self.config.get("lang", "auto")
            self.config["lang"] = result.get("lang", old_lang)
            self._save_config()
            self.POMODORO_MIN = result["focus_min"]
            self.POMO_SHORT_MIN = result["short_min"]
            self.POMO_LONG_MIN = result["long_min"]
            self.POMO_LONG_EVERY = result["long_every"]
            self._save_pomodoro()
            try:
                bar = self.query_one("#kanban-bar", Static)
                bar.set_class(not result["kanban_visible"], "hidden")
                if result["kanban_visible"]:
                    self._update_kanban()
            except Exception:
                pass
            self._populate_table()
            if result.get("lang", old_lang) != old_lang:
                self.notify(T("n_lang_restart"))
            else:
                self.notify(T("n_settings_saved"))

        current = dict(self.config)
        current.update(
            {
                "focus_min": self.POMODORO_MIN,
                "short_min": self.POMO_SHORT_MIN,
                "long_min": self.POMO_LONG_MIN,
                "long_every": self.POMO_LONG_EVERY,
            }
        )
        self.push_screen(
            SettingsScreen(sorted(self.available_themes.keys()), current), on_submit
        )

    def action_backup_now(self) -> None:
        try:
            path = create_backup()
        except Exception as exc:
            self.notify(T("n_bak_fail", e=_escape_markup(str(exc))), severity="error")
            return
        self.notify(T("n_bak_ok", n=_escape_markup(path.name)))

    def action_restore_backup(self) -> None:
        snaps = list_snapshots()
        if not snaps:
            self.notify(T("n_no_snap"), severity="warning")
            return

        def on_pick(path: str | None) -> None:
            if not path:
                return
            info = snapshot_info(Path(path))

            def on_confirm(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                try:
                    restore_snapshot(Path(path))
                except Exception as exc:
                    self.notify(
                        T("n_restore_fail", e=_escape_markup(str(exc))),
                        severity="error",
                    )
                    return
                if not state_readable():
                    self.notify(T("n_restore_badkey"), severity="error")
                    return
                self._reload_all()
                self.notify(T("n_restored_snap", d=info.get("created", "?")))

            self.push_screen(
                ConfirmScreen(T("n_restore_confirm", d=info.get("created", "?"))),
                on_confirm,
            )

        self.push_screen(RestoreScreen(snaps[:20]), on_pick)

    def _reload_all(self) -> None:
        self.store.reload()
        self.templates = load_templates()
        self.config = load_config()
        try:
            if self.config.get("theme") in self.available_themes:
                self.theme = self.config["theme"]
        except Exception:
            pass
        if self.config.get("filter_state") in FILTER_STATES:
            self.filter_state = self.config["filter_state"]
        try:
            bar = self.query_one("#kanban-bar", Static)
            bar.set_class(not self.config.get("kanban_visible", True), "hidden")
        except Exception:
            pass
        if self.focus_task_id is None:
            self._pending_pomo = load_pomodoro()
            self._restore_pomodoro()
        else:
            self._update_pomodoro_bar()
        self._populate_table()
        self._auto_backup()

    def _auto_backup(self) -> None:
        try:
            snaps = list_snapshots()
            if snaps:
                latest = max(p.stat().st_mtime for p in snaps)
                if (
                    datetime.now() - datetime.fromtimestamp(latest)
                ).total_seconds() < 24 * 3600:
                    return
            path = create_backup()
            self.notify(T("n_auto_bak", n=_escape_markup(path.name)))
        except Exception:
            pass

    def action_open_security(self) -> None:
        self.push_screen(SecurityScreen(_needs_unlock()), self._on_security_action)

    def _on_security_action(self, action: str | None) -> None:
        if action == "enable":
            self.push_screen(
                PasswordScreen(
                    "sec_pw_title_enable",
                    ["sec_pw_new", "sec_pw_repeat"],
                    self._pw_valid_new,
                ),
                self._sec_enable,
            )
        elif action == "change":
            self.push_screen(
                PasswordScreen(
                    "sec_pw_title_change",
                    ["sec_pw_current", "sec_pw_new", "sec_pw_repeat"],
                    self._pw_valid_change,
                ),
                self._sec_change,
            )
        elif action == "disable":
            self.push_screen(
                PasswordScreen(
                    "sec_pw_title_disable", ["sec_pw_current"], self._pw_valid_disable
                ),
                self._sec_disable,
            )

    def _pw_valid_new(self, values: list[str]) -> str | None:
        if any(not v for v in values):
            return T("n_sec_fill")
        new, repeat = values[-2], values[-1]
        if len(new) < 8:
            return T("n_sec_need8")
        if new != repeat:
            return T("n_sec_mismatch")
        return None

    def _pw_valid_change(self, values: list[str]) -> str | None:
        if any(not v for v in values):
            return T("n_sec_fill")
        if not self._sec_current_ok(values[0]):
            return T("n_sec_badcurrent")
        return self._pw_valid_new(values[1:])

    def _pw_valid_disable(self, values: list[str]) -> str | None:
        if any(not v for v in values):
            return T("n_sec_fill")
        if not self._sec_current_ok(values[0]):
            return T("n_sec_badcurrent")
        return None

    def _rewrite_all_state(self) -> None:
        self._save_data()
        save_templates(self.templates)
        self._save_pomodoro()
        try:
            save_archive(load_archive())
        except Exception:
            pass

    def _sec_enable(self, values: list[str] | None) -> None:
        if not values:
            return
        new, repeat = values[0], values[1]
        if len(new) < 8:
            self.notify(T("n_sec_need8"), severity="error")
            return
        if new != repeat:
            self.notify(T("n_sec_mismatch"), severity="error")
            return
        try:
            create_backup()
        except Exception as exc:
            self.notify(T("n_bak_fail", e=_escape_markup(str(exc))), severity="error")
            return
        _crypto.set_key(_crypto.encode_password(new))
        try:
            self._rewrite_all_state()
        except Exception as exc:
            _crypto.set_key(None)
            self.notify(T("n_bak_fail", e=_escape_markup(str(exc))), severity="error")
            return
        self._populate_table()
        self.notify(T("n_sec_enabled"))

    def _sec_current_ok(self, password: str) -> bool:
        for name, path in _backup_sources():
            if name == "config":
                continue
            try:
                if path.exists() and not _crypto.try_password(password, path):
                    return False
            except OSError:
                pass
        return True

    def _sec_change(self, values: list[str] | None) -> None:
        if not values:
            return
        old, new, repeat = values[0], values[1], values[2]
        if not self._sec_current_ok(old):
            self.notify(T("n_sec_badcurrent"), severity="error")
            return
        if len(new) < 8:
            self.notify(T("n_sec_need8"), severity="error")
            return
        if new != repeat:
            self.notify(T("n_sec_mismatch"), severity="error")
            return
        _crypto.set_key(_crypto.encode_password(new))
        try:
            self._rewrite_all_state()
        except Exception as exc:
            self.notify(T("n_bak_fail", e=_escape_markup(str(exc))), severity="error")
            return
        self._populate_table()
        self.notify(T("n_sec_changed"))

    def _sec_disable(self, values: list[str] | None) -> None:
        if not values:
            return
        if not self._sec_current_ok(values[0]):
            self.notify(T("n_sec_badcurrent"), severity="error")
            return
        _crypto.set_key(None)
        try:
            self._rewrite_all_state()
        except Exception as exc:
            self.notify(T("n_bak_fail", e=_escape_markup(str(exc))), severity="error")
            return
        self._populate_table()
        self.notify(T("n_sec_disabled"))

    def action_refresh(self) -> None:
        self._reload_all()
        self.notify(T("n_reloaded"))

    def action_toggle_help(self) -> None:
        help_panel = self.query_one("#help-panel")
        help_panel.set_class(not help_panel.has_class("hidden"), "hidden")

    def action_show_keys(self) -> None:
        """Apre il popup con tutte le combinazioni di tasti (voce Tasti del menu)."""
        self.push_screen(KeysScreen())

    def action_choose_theme(self) -> None:
        themes = sorted(self.available_themes.keys())

        def on_pick(choice: str | None) -> None:
            if choice is None:
                return
            try:
                self.theme = choice
            except Exception as exc:
                self.notify(
                    T("n_theme_bad", e=_escape_markup(str(exc))), severity="error"
                )
                return
            self.config["theme"] = choice
            self._save_config()
            self.notify(T("n_theme", c=choice))

        self.push_screen(ThemeListScreen(themes, self.theme), on_pick)

    def action_save_screenshot(self) -> None:
        try:
            path = self._save_screenshot_safe()
            self.notify(T("n_shot_saved", p=path))
        except Exception as exc:
            self.notify(T("n_shot_err", e=_escape_markup(str(exc))), severity="error")

    def _save_screenshot_safe(self) -> str:
        out_dir = _home() / "CarpeDiem_screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = out_dir / f"carpediem_{timestamp}.svg"
        screenshot = self.export_screenshot(title="CarpeDiem")
        output.write_text(screenshot, encoding="utf-8")
        return str(output)

    def deliver_screenshot(
        self,
        filename: str | None = None,
        path: str | None = None,
        time_format: str | None = None,
    ) -> str | None:
        """Override the built-in palette 'Screenshot' command: save to disk locally
        instead of attempting a browser download (which fails outside a browser)."""
        try:
            path = (
                self._save_screenshot_safe()
                if path is None and filename is None
                else None
            )
            if path is not None:
                self.notify(T("n_shot_saved", p=path))
                return None
            out_dir = Path(path) if path else (_home() / "CarpeDiem_screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            name = (
                filename or f"carpediem_{datetime.now().strftime('%Y%m%d_%H%M%S')}.svg"
            )
            output = out_dir / name
            output.write_text(
                self.export_screenshot(title="CarpeDiem"), encoding="utf-8"
            )
        except Exception as exc:
            self.notify(T("n_shot_err", e=_escape_markup(str(exc))), severity="error")
            return None
        self.notify(T("n_shot_saved", p=output))
        return None
