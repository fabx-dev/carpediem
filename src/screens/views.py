"""Viste di lettura, template, import, pomodoro, kanban, dettaglio, giorno, calendario. Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

import calendar
from datetime import date, datetime, timedelta
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from src.lang import (
    T,
    days_long,
    days_short,
    months,
    prio_disp,
    prio_letters,
    rec_disp,
)
from src.models import (
    PRIORITY_ORDER,
    Priority,
    Recurrence,
    TodoItem,
    _due_date_part,
    _due_time_part,
    _format_date_it,
    _pomo_label,
    _status,
)
from src.screens._shared import (
    CloseMixin,
    _agenda_due,
    _escape_markup,
    _parse_day,
)


class AgendaScreen(CloseMixin, ModalScreen[None]):
    """Radar cronologico: scaduti, oggi, domani, prossimi 7 giorni."""

    CSS = """
    #agenda-box {
        width: 86;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #agenda-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #agenda-list {
        height: 1fr;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, all_todos: list[TodoItem]) -> None:
        super().__init__()
        self.all_todos = all_todos

    def compose(self) -> ComposeResult:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=7)
        active = [t for t in self.all_todos if t.state != "completato"]
        with Vertical(id="agenda-box"):
            yield Label(T("agenda_title"), id="agenda-title")
            with VerticalScroll(id="agenda-list"):
                yield from self._section(
                    T("agenda_overdue"),
                    [
                        t
                        for t in active
                        if _due_date_part(t.due) and _parse_day(t.due) < today
                    ],
                )
                yield from self._section(
                    T("agenda_today"),
                    [t for t in active if _parse_day(t.due) == today],
                )
                yield from self._section(
                    T("agenda_tomorrow"),
                    [t for t in active if _parse_day(t.due) == tomorrow],
                )
                yield from self._section(
                    T("agenda_next"),
                    [t for t in active if tomorrow < _parse_day(t.due) <= week_end],
                )
                yield from self._section(
                    T("agenda_important"),
                    [
                        t
                        for t in active
                        if not _due_date_part(t.due) and t.priority == Priority.HIGH
                    ],
                )
            yield Button(T("ui_close_esc"), id="agenda-close", variant="default")

    def _section(self, title: str, todos: list[TodoItem]):
        yield Label(f"[b]{title}[/b]")
        if not todos:
            yield Static(f"  [dim]{T('agenda_empty')}[/]")
            return
        for t in sorted(
            todos,
            key=lambda x: (
                _due_date_part(x.due) or "9999-99-99",
                _due_time_part(x.due) or "99:99",
                PRIORITY_ORDER.get(x.priority.value, 9),
                x.title.lower(),
            ),
        ):
            due = _agenda_due(t)
            proj = f" @{_escape_markup(t.project)}" if t.project else ""
            yield Static(
                f"  {_status(t)} {due}{_escape_markup(t.title)}{proj}  [{t.priority.color}]{prio_disp(t.priority.value)}[/]"
            )
        yield Static("")

    def on_mount(self) -> None:
        try:
            self.query_one("#agenda-close", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "agenda-close":
            self.dismiss()


class WorkflowScreen(CloseMixin, ModalScreen[None]):
    """Guida operativa breve: come usare CarpeDiem nel ciclo quotidiano."""

    CSS = """
    #workflow-box {
        width: 86;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #workflow-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #workflow-list {
        height: 1fr;
        margin-bottom: 1;
    }
    .workflow-head {
        height: auto;
        margin-top: 1;
        margin-bottom: 0;
    }
    .workflow-line {
        height: auto;
        margin-bottom: 0;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def compose(self) -> ComposeResult:
        with Vertical(id="workflow-box"):
            yield Label(T("workflow_title"), id="workflow-title")
            with VerticalScroll(id="workflow-list"):
                yield Label(T("workflow_intro"), classes="workflow-line")
                for i in range(1, 6):
                    yield Label(T(f"workflow_s{i}_t"), classes="workflow-head")
                    yield Static(T(f"workflow_s{i}_b"), classes="workflow-line")
            yield Button(T("ui_close_esc"), id="workflow-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#workflow-close", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "workflow-close":
            self.dismiss()


class WeekScreen(CloseMixin, ModalScreen[None]):
    """Vista settimana Lun-Dom."""

    CSS = """
    #week-box {
        width: 80;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #week-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #week-nav {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    #week-nav Button {
        width: 1fr;
        min-width: 14;
        height: 3;
        margin: 0 1;
    }
    #week-list {
        height: 1fr;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, all_todos: list[TodoItem], monday: date) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.monday = monday

    def compose(self) -> ComposeResult:
        end = self.monday + timedelta(days=6)
        with Vertical(id="week-box"):
            yield Label(
                f"[b]{T('week_title', a=self.monday.strftime('%d/%m'), b=end.strftime('%d/%m/%Y'))}[/b]",
                id="week-title",
            )
            with Horizontal(id="week-nav"):
                yield Button(T("nav_prev"), id="prev-btn", variant="default")
                yield Button(T("nav_next"), id="next-btn", variant="default")
            with VerticalScroll(id="week-list"):
                for i in range(7):
                    d = self.monday + timedelta(days=i)
                    ds = d.strftime("%Y-%m-%d")
                    day_todos = [
                        t
                        for t in self.all_todos
                        if _due_date_part(t.due) == ds and t.state != "completato"
                    ]
                    label = (
                        f"{days_long()[d.weekday()]} {d.day:02d} {months()[d.month]}"
                    )
                    if d == datetime.now().date():
                        yield Label(f"[b reverse] {label} [/b reverse]")
                    else:
                        yield Label(f"[b]{label}[/b]")
                    if day_todos:
                        for t in sorted(
                            day_todos,
                            key=lambda x: (
                                PRIORITY_ORDER.get(x.priority.value, 9),
                                x.title.lower(),
                            ),
                        ):
                            tm = (
                                f" {_due_time_part(t.due)}"
                                if _due_time_part(t.due)
                                else ""
                            )
                            yield Static(
                                f"  {_status(t)} {_escape_markup(t.title)}{tm}  [{t.priority.color}]{prio_disp(t.priority.value)}[/]"
                            )
                    else:
                        yield Static("  [dim]-[/]")
            yield Button(T("ui_close_esc"), id="week-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#week-close", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "week-close":
            self.dismiss()
        elif event.button.id == "prev-btn":
            self.monday -= timedelta(days=7)
            self.refresh(recompose=True)
        elif event.button.id == "next-btn":
            self.monday += timedelta(days=7)
            self.refresh(recompose=True)


class TemplateScreen(ModalScreen[tuple | None]):
    """Scelta template: Usa per creare i task, N nuovo, P da progetto."""

    CSS = """
    #tpl-box {
        width: 60;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #tpl-list {
        height: 1fr;
        margin-bottom: 1;
    }
    .tpl-row {
        width: 100%;
        height: 3;
        margin-bottom: 1;
        align-vertical: middle;
    }
    .tpl-use-btn {
        width: 1fr;
        min-width: 16;
        height: 3;
    }
    .tpl-del-btn {
        width: 3;
        min-width: 3;
        height: 1;
        min-height: 1;
        padding: 0;
        border: none;
        margin: 1 0 0 1;
    }
    .tpl-edit-btn {
        width: 3;
        min-width: 3;
        height: 1;
        min-height: 1;
        padding: 0;
        border: none;
        margin: 1 0 0 1;
    }
    #tpl-empty {
        height: auto;
        margin-bottom: 1;
    }
    #tpl-actions {
        width: 100%;
        height: auto;
    }
    #tpl-actions Button {
        width: 1fr;
        min-width: 12;
        height: 3;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("n", "new_template", "Nuovo"),
        Binding("p", "from_project", "Da progetto"),
    ]

    def __init__(self, templates: dict[str, list[dict]] | None = None) -> None:
        super().__init__()
        self.templates = templates if templates is not None else {}

    def compose(self) -> ComposeResult:
        with Vertical(id="tpl-box"):
            yield Label(T("tpl_title"), id="tpl-title")
            with VerticalScroll(id="tpl-list"):
                if not self.templates:
                    yield Label(T("tpl_empty"), id="tpl-empty")
                for i, (name, items) in enumerate(self.templates.items()):
                    with Horizontal(classes="tpl-row"):
                        yield Button(
                            T("tpl_use", name=_escape_markup(name), n=len(items)),
                            id=f"tpl-use-{i}",
                            variant="default",
                            classes="tpl-use-btn",
                        )
                        yield Button(
                            "M",
                            id=f"tpl-edit-{i}",
                            variant="default",
                            classes="tpl-edit-btn",
                        )
                        yield Button(
                            "X",
                            id=f"tpl-del-{i}",
                            variant="error",
                            classes="tpl-del-btn",
                        )
            with Horizontal(id="tpl-actions"):
                yield Button(T("tpl_new"), id="tpl-new", variant="default")
                yield Button(
                    T("tpl_fromproj"), id="tpl-from-project", variant="default"
                )
                yield Button(T("ui_close_esc"), id="tpl-close", variant="default")

    def _name_at(self, idx: int) -> str | None:
        try:
            return list(self.templates.keys())[idx]
        except IndexError:
            return None

    def on_mount(self) -> None:
        # Focus su "Nuovo": Enter apre subito la creazione (mouse non necessario).
        try:
            self.query_one("#tpl-new", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "tpl-close":
            self.dismiss(None)
        elif bid == "tpl-new":
            self.dismiss(("new", None))
        elif bid == "tpl-from-project":
            self.dismiss(("from_project", None))
        elif bid.startswith("tpl-use-"):
            try:
                name = self._name_at(int(bid[len("tpl-use-") :]))
            except ValueError:
                return
            if name:
                self.dismiss(("use", name))
        elif bid.startswith("tpl-del-"):
            try:
                name = self._name_at(int(bid[len("tpl-del-") :]))
            except ValueError:
                return
            if name:
                self.dismiss(("delete", name))
        elif bid.startswith("tpl-edit-"):
            try:
                name = self._name_at(int(bid[len("tpl-edit-") :]))
            except ValueError:
                return
            if name:
                self.dismiss(("edit", name))

    def action_close(self) -> None:
        self.dismiss(None)

    def action_new_template(self) -> None:
        self.dismiss(("new", None))

    def action_from_project(self) -> None:
        self.dismiss(("from_project", None))


class TemplateCreateScreen(ModalScreen[dict | None]):
    """Crea un nuovo template: nome + un task per riga."""

    CSS = """
    #tplc-box {
        width: 64;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #tplc-body {
        width: 100%;
        height: 1fr;
    }
    #tplc-tasks {
        height: 10;
        margin-bottom: 1;
        border: solid $primary-darken-1;
    }
    #tplc-buttons {
        width: 100%;
        height: 3;
        dock: bottom;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+enter", "submit", "Salva", show=False),
        Binding("s", "submit", "Salva", show=False),
    ]

    def __init__(self, initial: dict | None = None) -> None:
        """initial: {'name': str, 'items': [{'title', 'priority'}]} per la modifica."""
        super().__init__()
        self.initial = initial or {}

    def compose(self) -> ComposeResult:
        title = T("tplc_edit") if self.initial.get("name") else T("tplc_new")
        with Vertical(id="tplc-box"):
            yield Label(f"[b]{title}[/b]", id="tplc-title")
            with VerticalScroll(id="tplc-body", can_focus=False):
                yield Label(T("tplc_name"))
                yield Input(placeholder=T("tplc_name_ph"), id="tplc-name")
                yield Label(T("tplc_prio"))
                yield Select(
                    [(prio_disp(p.value), p) for p in Priority],
                    value=Priority.MEDIUM,
                    id="tplc-priority",
                )
                yield Label(T("tplc_tasks"))
                yield TextArea("", id="tplc-tasks")
            with Horizontal(id="tplc-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="tplc-save", variant="default")
                yield Button(T("form_cancel"), id="tplc-cancel", variant="default")

    def on_mount(self) -> None:
        # Form con campi: il focus sta sul nome da compilare.
        try:
            if self.initial.get("name"):
                self.query_one("#tplc-name", Input).value = str(self.initial["name"])
            items = self.initial.get("items") or []
            if items:
                self.query_one("#tplc-tasks", TextArea).text = "\n".join(
                    str(i.get("title", "")) for i in items if isinstance(i, dict)
                )
                prios = [i.get("priority") for i in items if isinstance(i, dict)]
                prios = [p for p in prios if isinstance(p, Priority)]
                if prios:
                    top = max(set(prios), key=prios.count)
                    try:
                        self.query_one("#tplc-priority", Select).value = top
                    except Exception:
                        pass
            self.query_one("#tplc-name", Input).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tplc-cancel":
            self.dismiss(None)
        elif event.button.id == "tplc-save":
            self._submit()

    def _submit(self) -> None:
        name = self.query_one("#tplc-name", Input).value.strip()
        if not name:
            self.query_one("#tplc-name", Input).focus()
            self.notify(T("n_tpl_name_req"), severity="warning")
            return
        default_priority = self.query_one("#tplc-priority", Select).value
        lines = [
            ln.strip()
            for ln in (self.query_one("#tplc-tasks", TextArea).text or "").splitlines()
        ]
        titles = [ln for ln in lines if ln]
        if not titles:
            self.query_one("#tplc-tasks", TextArea).focus()
            self.notify(T("n_tpl_tasks_req"), severity="warning")
            return
        self.dismiss(
            {
                "name": name,
                "items": [{"title": t, "priority": default_priority} for t in titles],
            }
        )


class TemplateProjectScreen(ModalScreen[str | None]):
    """Sceglie un progetto esistente da cui creare un template."""

    CSS = """
    #tplp-box {
        width: 52;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #tplp-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #tplp-list Button {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, projects: list[tuple[str, int]]) -> None:
        super().__init__()
        self.projects = projects

    def compose(self) -> ComposeResult:
        with Vertical(id="tplp-box"):
            yield Label(T("tplp_title"), id="tplp-title")
            with VerticalScroll(id="tplp-list"):
                for name, count in self.projects:
                    yield Button(
                        T("tplp_row", name=_escape_markup(name), n=count),
                        id=f"tplp-{name}",
                        variant="default",
                    )
            yield Button(T("ui_close_esc"), id="tplp-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "tplp-close":
            self.dismiss(None)
        elif bid.startswith("tplp-"):
            self.dismiss(bid[len("tplp-") :])

    def on_mount(self) -> None:
        try:
            first = self.query("#tplp-list Button")
            (first.first() if first else self.query_one("#tplp-close", Button)).focus()
        except Exception:
            pass

    def action_close(self) -> None:
        self.dismiss(None)


class ImportCsvScreen(ModalScreen[str | None]):
    """Sceglie un CSV da importare (lista + percorso manuale)."""

    CSS = """
    #impcsv-box {
        width: 64;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #impcsv-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #impcsv-list Button {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-bottom: 1;
    }
    #impcsv-path {
        margin-bottom: 1;
    }
    #impcsv-buttons {
        width: 100%;
        height: 3;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+enter", "submit", "Salva", show=False),
        Binding("s", "submit", "Salva", show=False),
    ]

    def __init__(self, files: list[Path]) -> None:
        super().__init__()
        self.files = files

    def compose(self) -> ComposeResult:
        with Vertical(id="impcsv-box"):
            yield Label(T("imp_title"), id="impcsv-title")
            with VerticalScroll(id="impcsv-list"):
                if not self.files:
                    yield Label(T("imp_empty"))
                for i, p in enumerate(self.files):
                    yield Button(
                        f"{_escape_markup(p.name)}", id=f"impcsv-{i}", variant="default"
                    )
            yield Label(T("imp_path"))
            yield Input(placeholder=T("imp_path_ph"), id="impcsv-path")
            with Horizontal(id="impcsv-buttons", classes="btn-row"):
                yield Button(T("imp_ok"), id="impcsv-ok", variant="default")
                yield Button(T("form_cancel"), id="impcsv-cancel", variant="default")

    def on_mount(self) -> None:
        try:
            first = self.query("#impcsv-list Button")
            (first.first() if first else self.query_one("#impcsv-path", Input)).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "impcsv-cancel":
            self.dismiss(None)
        elif bid == "impcsv-ok":
            self._submit()
        elif bid.startswith("impcsv-"):
            try:
                self.dismiss(str(self.files[int(bid[len("impcsv-") :])]))
            except (ValueError, IndexError):
                pass

    def _submit(self) -> None:
        path = self.query_one("#impcsv-path", Input).value.strip()
        if not path:
            self.query_one("#impcsv-path", Input).focus()
            self.notify(T("n_imp_pick"), severity="warning")
            return
        self.dismiss(path)


class PomodoroScreen(CloseMixin, ModalScreen[None]):
    """Timer pomodoro con durata impostabile, pausa/riprendi, live countdown."""

    CSS = """
    #pomo-box {
        width: 46;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #pomo-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #pomo-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 0;
        height: auto;
    }
    #pomo-task {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        height: auto;
    }
    #pomo-time {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        height: 3;
    }
    #pomo-dur-label {
        margin-bottom: 0;
        height: auto;
    }
    #pomo-durations {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    #pomo-durations Button {
        width: 1fr;
        min-width: 0;
        height: 3;
        margin: 0 1;
    }
    #pomo-buttons {
        width: 100%;
        height: auto;
    }
    #pomo-buttons Button {
        width: 100%;
        min-width: 0;
        height: 3;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("p", "pause_resume", "Pausa/Riprendi", show=False),
        Binding("x", "done", "Completa", show=False),
        Binding("X", "done", "Completa", show=False),
        Binding("1", "dur_0", "Durata 1", show=False),
        Binding("2", "dur_1", "Durata 2", show=False),
        Binding("3", "dur_2", "Durata 3", show=False),
    ]

    def __init__(
        self, get_state, on_pause_resume, on_stop, on_done, on_set_duration
    ) -> None:
        super().__init__()
        self.get_state = get_state
        self.on_pause_resume = on_pause_resume
        self.on_stop = on_stop
        self.on_done = on_done
        self.on_set_duration = on_set_duration
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="pomo-box"):
            # Contenuto in scroll + bottoni fissi: a terminale piccolo
            # (70x20) il box auto usciva dal viewport e Chiudi era
            # irraggiungibile (pattern cornice fissa, come le altre screen).
            with VerticalScroll(id="pomo-scroll"):
                yield Label("[b]🍅 Pomodoro[/b]", id="pomo-title")
                yield Label("", id="pomo-task")
                yield Label("", id="pomo-time")
                yield Label(T("pomo_dur_focus"), id="pomo-dur-label")
                with Horizontal(id="pomo-durations"):
                    yield Button("", id="pomo-dur-0", variant="default")
                    yield Button("", id="pomo-dur-1", variant="default")
                    yield Button("", id="pomo-dur-2", variant="default")
            with Vertical(id="pomo-buttons"):
                yield Button(T("pomo_pause"), id="pause-btn", variant="default")
                yield Button(T("pomo_done"), id="done-btn", variant="default")
                yield Button(T("pomo_stop"), id="stop-btn", variant="default")
                yield Button(T("pomo_close"), id="pomo-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#pause-btn", Button).focus()
        except Exception:
            pass
        self._refresh()
        try:
            self._timer = self.set_interval(1, self._refresh)
        except Exception:
            pass

    def _refresh(self) -> None:
        try:
            state = self.get_state()
        except Exception:
            return
        if not isinstance(state, dict) or state.get("empty"):
            try:
                self.dismiss()
            except Exception:
                pass
            return
        try:
            is_break = bool(state.get("is_break"))
            if state.get("phase") == "long":
                title = T("pomo_t_long")
            elif is_break:
                title = T("pomo_t_short")
            else:
                title = T("pomo_t_focus")
            self.query_one("#pomo-title", Label).update(f"[b]{title}[/b]")
            self.query_one("#pomo-task", Label).update(state["task"])
            self.query_one("#pomo-time", Label).update(f"[b]{state['clock']}[/b]")
            self.query_one("#pause-btn", Button).label = (
                T("pomo_resume") if state["paused"] else T("pomo_pause")
            )
            self.query_one("#done-btn", Button).label = (
                T("pomo_skip") if is_break else T("pomo_done")
            )
            self.query_one("#pomo-dur-label", Label).update(
                T("pomo_dur_break") if is_break else T("pomo_dur_focus")
            )
            presets = state.get("presets") or (15, 25, 50)
            for i in range(3):
                try:
                    btn = self.query_one(f"#pomo-dur-{i}", Button)
                    btn.label = f"{presets[i]}'"
                    btn.variant = (
                        "primary" if state["total_min"] == presets[i] else "default"
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _preset_value(self, index: int) -> int | None:
        try:
            presets = self.get_state().get("presets") or ()
            return int(presets[index])
        except (ValueError, TypeError, IndexError):
            return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "pomo-close":
            self.dismiss()
        elif bid == "pause-btn":
            self.on_pause_resume()
            self._refresh()
        elif bid == "stop-btn":
            self.on_stop()
            self.dismiss()
        elif bid == "done-btn":
            self.on_done()
            self.dismiss()
        elif bid.startswith("pomo-dur-"):
            try:
                minutes = self._preset_value(int(bid[len("pomo-dur-") :]))
            except ValueError:
                return
            if minutes is None:
                return
            self.on_set_duration(minutes)
            self._refresh()

    def action_pause_resume(self) -> None:
        self.on_pause_resume()
        self._refresh()

    def action_done(self) -> None:
        self.on_done()
        self.dismiss()

    def action_dur_0(self) -> None:
        minutes = self._preset_value(0)
        if minutes is None:
            return
        self.on_set_duration(minutes)
        self._refresh()

    def action_dur_1(self) -> None:
        minutes = self._preset_value(1)
        if minutes is None:
            return
        self.on_set_duration(minutes)
        self._refresh()

    def action_dur_2(self) -> None:
        minutes = self._preset_value(2)
        if minutes is None:
            return
        self.on_set_duration(minutes)
        self._refresh()


class KanbanScreen(CloseMixin, ModalScreen[None]):
    """Board kanban Attivo / Sospeso / Completato."""

    CSS = """
    #kb-box {
        width: 96;
        max-width: 98%;
        height: 90%;
        max-height: 92%;
    }
    #kb-title {
        text-align: center;
        text-style: bold;
        color: $primary;
    }
    #kb-hint {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
    }
    #kb-cols {
        width: 100%;
        height: 1fr;
        margin-bottom: 1;
    }
    #kb-col-attivo, #kb-col-sospeso, #kb-col-fatto {
        width: 1fr;
        height: 100%;
        margin: 0 1;
        border: solid $primary-darken-1;
        padding: 0 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, all_todos: list[TodoItem]) -> None:
        super().__init__()
        self.all_todos = all_todos

    def _col(self, state: str) -> list[TodoItem]:
        items = [t for t in self.all_todos if not t.is_subtask and t.state == state]
        return sorted(
            items,
            key=lambda x: (
                (_due_date_part(x.due) or "9999"),
                PRIORITY_ORDER.get(x.priority.value, 9),
            ),
        )

    def compose(self) -> ComposeResult:
        cols = [
            ("attivo", T("kb_col_attivo"), self._col("attivo"), "red"),
            ("sospeso", T("kb_col_sospeso"), self._col("in_sospeso"), "yellow"),
            ("fatto", T("kb_col_fatto"), self._col("completato"), "green"),
        ]
        with Vertical(id="kb-box"):
            yield Label(T("kb_title"), id="kb-title")
            yield Label(
                T("kb_hint"),
                id="kb-hint",
            )
            with Horizontal(id="kb-cols"):
                for key, title, items, color in cols:
                    with VerticalScroll(id=f"kb-col-{key}"):
                        yield Label(f"[{color}][b]{title} ({len(items)})[/b][/]")
                        if not items:
                            yield Static("[dim]—[/]")
                        for t in items[:30]:
                            proj = f" @{_escape_markup(t.project)}" if t.project else ""
                            tm = (
                                f" {_due_date_part(t.due)}"
                                if _due_date_part(t.due)
                                else ""
                            )
                            yield Static(
                                f"#{t.id} {_escape_markup(t.title[:28])}{proj}{tm}"
                            )
                        if len(items) > 30:
                            yield Static(f"[dim]{T('kb_more', n=len(items) - 30)}[/]")
            yield Button(T("ui_close_esc"), id="kb-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "kb-close":
            self.dismiss()

    def on_mount(self) -> None:
        try:
            self.query_one("#kb-close", Button).focus()
        except Exception:
            pass


class DetailScreen(ModalScreen[str | None]):
    """Screen to show todo details including notes and subtasks."""

    CSS = """
    #detail-box {
        width: 60;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #detail-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #detail-notes {
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
        border: solid $primary-darken-1;
    }
    #detail-scroll {
        height: 1fr;
    }
    #detail-subtasks-label {
        margin-top: 1;
    }
    #detail-buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("e", "edit", "Modifica"),
    ]

    def __init__(self, todo: TodoItem, all_todos: list[TodoItem]) -> None:
        super().__init__()
        self.todo = todo
        self.all_todos = all_todos

    def _get_subtasks(self, parent_id: int | None) -> list[TodoItem]:
        return [t for t in self.all_todos if t.parent_id == parent_id]

    def _build_tree(
        self, todo: TodoItem, depth: int = 0, prefix: str = "", is_last: bool = True
    ) -> list[tuple[int, str, TodoItem]]:
        result = []
        status = _status(todo)
        if depth == 0:
            display = f"  {status} {_escape_markup(todo.title)}"
        else:
            connector = "└── " if is_last else "├── "
            display = f"  {prefix}{connector}{status} {_escape_markup(todo.title)}"
        result.append((depth, display, todo))

        subtasks = self._get_subtasks(todo.id)
        for i, sub in enumerate(subtasks):
            is_last_sub = i == len(subtasks) - 1
            new_prefix = prefix + ("    " if is_last else "│   ") if depth > 0 else ""
            result.extend(self._build_tree(sub, depth + 1, new_prefix, is_last_sub))
        return result

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-box"):
            with VerticalScroll(id="detail-scroll"):
                yield Label(
                    f"[b]{_escape_markup(self.todo.title)}[/b]", id="detail-title"
                )
                yield Label(
                    f"{T('detail_prio')} [{self.todo.priority.color}]{prio_disp(self.todo.priority.value)}[/]"
                )
                if self.todo.project:
                    yield Label(
                        f"{T('form_project')} [blue]{_escape_markup(self.todo.project)}[/]"
                    )
                if self.todo.pomodoros or getattr(self.todo, "stima_pomo", 0):
                    pomo_txt = f"{T('detail_pomo')} [red]{_pomo_label(self.todo)}[/]"
                    try:
                        actual = int(getattr(self.todo, "actual_pomo", 0) or 0)
                    except (ValueError, TypeError):
                        actual = 0
                    if actual > 0:
                        pomo_txt += f" ({T('detail_actual', n=actual)})"
                    yield Label(pomo_txt)
                if self.todo.tags:
                    yield Label(
                        f"{T('form_tags')} "
                        + ", ".join(
                            f"[magenta]#{_escape_markup(t)}[/]" for t in self.todo.tags
                        )
                    )
                yield Label(
                    T(
                        "detail_dueline",
                        due=self.todo.due or "-",
                        created=self.todo.created,
                    )
                )
                if self.todo.recurrence != Recurrence.NONE:
                    yield Label(
                        f"{T('detail_ric')} [cyan]{rec_disp(self.todo.recurrence.value)}[/]"
                    )
                stato_label = {
                    "attivo": f"[red]{T('state_attivo').capitalize()}[/red]",
                    "in_sospeso": f"[yellow]{T('state_sospeso').capitalize()}[/yellow]",
                    "completato": f"[green]{T('state_completato').capitalize()}[/green]",
                }[self.todo.state]
                yield Label(f"{T('detail_state')} {stato_label}")
                if self.todo.notes:
                    yield Label(T("detail_notes"))
                    pretty_notes = (
                        self.todo.notes.replace("- [ ]", "☐")
                        .replace("- [x]", "☑")
                        .replace("- [X]", "☑")
                    )
                    yield Static(_escape_markup(pretty_notes), id="detail-notes")
                tree_items = self._build_tree(self.todo)
                if len(tree_items) > 1:
                    yield Label(T("detail_subs"), id="detail-subtasks-label")
                    for depth, display, item in tree_items[1:]:
                        yield Static(display)
                else:
                    yield Label(T("detail_nosubs"), id="detail-subtasks-label")
            with Horizontal(id="detail-buttons", classes="btn-row"):
                yield Button(T("detail_edit"), id="detail-edit", variant="default")
                yield Button(T("ui_close_esc"), id="detail-close", variant="default")

    def on_mount(self) -> None:
        # Focus su Chiudi: Enter/Esc chiude, e resta la via breve da tastiera.
        try:
            self.query_one("#detail-close", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "detail-close":
            self.dismiss(None)
        elif event.button.id == "detail-edit":
            self.dismiss("edit")

    def action_close(self) -> None:
        self.dismiss(None)

    def action_edit(self) -> None:
        self.dismiss("edit")


class DayScreen(CloseMixin, ModalScreen[None]):
    """Screen showing the todos due on a specific day."""

    CSS = """
    #day-box {
        width: 70;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #day-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #day-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #day-empty {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, date_str: str, todos: list[TodoItem]) -> None:
        super().__init__()
        self.date_str = date_str
        self.todos = todos

    def compose(self) -> ComposeResult:
        label = _format_date_it(self.date_str)
        with Vertical(id="day-box"):
            yield Label(f"[b]{T('day_title', label=label)}[/b]", id="day-title")
            if self.todos:
                with VerticalScroll(id="day-list"):
                    for t in self.todos:
                        yield Static(
                            f"  {_status(t)} {_escape_markup(t.title)}  [{t.priority.color}]{prio_disp(t.priority.value)}[/]"
                        )
            else:
                yield Static(T("day_empty"), id="day-empty")
            yield Button(T("ui_close_esc"), id="day-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "day-close":
            self.dismiss()

    def on_mount(self) -> None:
        try:
            self.query_one("#day-close", Button).focus()
        except Exception:
            pass


class CalendarGrid(Static):
    """Griglia mensile con giorni cliccabili.

    Textual 3.x non dispatcha piu' le azioni-in-markup [@click=...] (meta
    assente dai segmenti renderizzati): il click viene risolto qui,
    mappando riga/colonna sul giorno. Struttura: riga 0 = intestazione,
    poi coppie di righe per settimana (numeri / marche), celle da 5
    caratteri + 1 separatore."""

    CELL = 6

    def __init__(self, content: str, year: int, month: int, **kwargs) -> None:
        super().__init__(content, **kwargs)
        self.year = year
        self.month = month

    def _day_at(self, x: int, y: int) -> int | None:
        """Il giorno sotto la colonna/riga di testo, o None (header/vuoto)."""
        try:
            cl = calendar.Calendar(firstweekday=0)
            weeks = cl.monthdayscalendar(self.year, self.month)
        except Exception:
            return None
        if y <= 0:  # intestazione giorni
            return None
        week, half = divmod(y - 1, 2)
        if week >= len(weeks):
            return None
        pos = x // self.CELL
        if not 0 <= pos < 7:
            return None
        return weeks[week][pos] or None

    def on_click(self, event) -> None:
        try:
            day = self._day_at(event.x, event.y)
        except Exception:
            return
        if day:
            try:
                handler = getattr(self.app, "action_open_day", None)
                if callable(handler):
                    handler(self.year, self.month, day)
            except Exception:
                pass


class CalendarScreen(CloseMixin, ModalScreen[None]):
    """Screen to show todos on a monthly calendar grid."""

    CSS = """
    #calendar-box {
        width: 80;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #calendar-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #calendar-nav {
        align: center middle;
        margin-bottom: 1;
        width: 100%;
        height: 3;
    }
    #calendar-nav Button {
        margin: 0 1;
        width: 1fr;
        min-width: 14;
        height: 3;
    }
    #calendar-scroll {
        height: 1fr;
        width: 100%;
        margin-bottom: 1;
    }
    #calendar-grid-wrap {
        height: auto;
        width: 100%;
        align: center middle;
    }
    #calendar-grid {
        height: auto;
        width: auto;
    }
    #calendar-legend {
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, all_todos: list[TodoItem], year: int, month: int) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.year = year
        self.month = month

    def _todos_by_day(self) -> dict[int, list[TodoItem]]:
        result: dict[int, list[TodoItem]] = {}
        for t in self.all_todos:
            if t.due and t.state != "completato":
                try:
                    d = datetime.strptime(_due_date_part(t.due), "%Y-%m-%d").date()
                except ValueError:
                    continue
                if d.year == self.year and d.month == self.month:
                    result.setdefault(d.day, []).append(t)
        return result

    def compose(self) -> ComposeResult:
        month_name = months()[self.month]
        with Vertical(id="calendar-box"):
            yield Label(f"[b]{month_name} {self.year}[/b]", id="calendar-title")
            with Horizontal(id="calendar-nav"):
                yield Button(T("nav_prev"), id="prev-btn", variant="default")
                yield Button(T("nav_next"), id="next-btn", variant="default")
            with VerticalScroll(id="calendar-scroll"):
                with Horizontal(id="calendar-grid-wrap"):
                    yield CalendarGrid(
                        self._render_grid(), self.year, self.month, id="calendar-grid"
                    )
                yield Static(T("cal_legend"), id="calendar-legend")
            yield Button(T("ui_close_esc"), id="calendar-close", variant="default")

    def _render_grid(self) -> str:
        cl = calendar.Calendar(firstweekday=0)
        header = " ".join(f"{g:^5}" for g in days_short())
        todos_by_day = self._todos_by_day()
        today = datetime.now().date()
        lines = [header]
        prio_color = {
            Priority.HIGH: ("red", prio_letters()["alta"]),
            Priority.MEDIUM: ("yellow", prio_letters()["media"]),
            Priority.LOW: ("green", prio_letters()["bassa"]),
        }
        for week in cl.monthdayscalendar(self.year, self.month):
            day_cells = []
            task_cells = []
            for day in week:
                if day == 0:
                    day_cells.append(" " * 5)
                    task_cells.append(" " * 5)
                    continue
                todos = todos_by_day.get(day, [])
                plain_num = str(day)
                number_markup = plain_num
                if any(t.priority == Priority.HIGH for t in todos):
                    number_markup = f"[red]{plain_num}[/]"
                elif any(t.priority == Priority.MEDIUM for t in todos):
                    number_markup = f"[yellow]{plain_num}[/]"
                elif any(t.priority == Priority.LOW for t in todos):
                    number_markup = f"[green]{plain_num}[/]"
                if datetime(self.year, self.month, day).date() == today:
                    number_markup = f"[bold reverse]{number_markup}[/]"
                number_markup = self._center_markup(number_markup, len(plain_num), 5)
                marks = ""
                plain_marks = ""
                for t in todos[:3]:
                    color, letter = prio_color[t.priority]
                    marks += f"[{color}]{letter}[/]"
                    plain_marks += letter
                if len(todos) > 3:
                    suffix = f"+{len(todos) - 3}"
                    if len(plain_marks) + len(suffix) > 5:
                        plain_marks = plain_marks[: max(0, 5 - len(suffix))]
                        marks = "".join(
                            f"[{prio_color[t.priority][0]}]{prio_color[t.priority][1]}[/]"
                            for t in todos[: len(plain_marks)]
                        )
                    marks += f"[dim]{suffix}[/]"
                    plain_marks += suffix
                day_cells.append(number_markup)
                task_cells.append(
                    self._center_markup(marks, len(plain_marks), 5)
                    if marks
                    else " " * 5
                )
            lines.append(" ".join(day_cells))
            lines.append(" ".join(task_cells))
        return "\n".join(lines)

    @staticmethod
    def _center_markup(marked: str, plain_len: int, width: int) -> str:
        total = max(0, width - plain_len)
        left = total // 2
        return " " * left + marked + " " * (total - left)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "calendar-close":
            self.dismiss()
        elif button_id == "prev-btn":
            self.month -= 1
            if self.month < 1:
                self.month = 12
                self.year -= 1
            self.refresh(recompose=True)
        elif button_id == "next-btn":
            self.month += 1
            if self.month > 12:
                self.month = 1
                self.year += 1
            self.refresh(recompose=True)

    def on_mount(self) -> None:
        try:
            self.query_one("#calendar-close", Button).focus()
        except Exception:
            pass


class SmartListScreen(CloseMixin, ModalScreen[None]):
    """Filtri salvati: applica in un click, salva quello attuale, elimina."""

    CSS = """
    #smart-box {
        width: 100;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #smart-count {
        height: auto;
        margin-bottom: 1;
    }
    #smart-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    .smart-row {
        height: 3;
        margin-bottom: 1;
    }
    .smart-apply {
        width: 1fr;
        min-width: 14;
        height: 3;
    }
    .smart-del {
        width: 8;
        min-width: 8;
        height: 3;
        margin-left: 1;
    }
    #smart-snapshot {
        height: auto;
        margin-bottom: 1;
    }
    #smart-name {
        margin-bottom: 1;
    }
    #smart-legend {
        height: auto;
    }
    #smart-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("s", "save", "Salva", show=False),
        Binding("x", "delete_focused", "Elimina", show=False),
    ]

    def __init__(
        self,
        lists: list[dict],
        snapshot: str,
        on_apply,
        on_save,
        on_delete,
    ) -> None:
        super().__init__()
        self._lists = list(lists)
        self._snapshot = snapshot
        self._on_apply = on_apply
        self._on_save = on_save
        self._on_delete = on_delete

    @staticmethod
    def spec_details(spec: dict) -> str:
        """Descrizione breve della spec (niente []: va in label di Button)."""
        parts = []
        if spec.get("state"):
            parts.append(str(spec["state"]))
        if spec.get("tag"):
            parts.append(f"#{spec['tag']}")
        if spec.get("project"):
            parts.append(f"*{spec['project']}")
        if spec.get("search"):
            parts.append(f'"{spec["search"]}"')
        return ", ".join(parts)

    def _row_label(self, spec: dict) -> str:
        name = _escape_markup(str(spec.get("name", "")))
        details = _escape_markup(self.spec_details(spec))
        return f"{name} ({details})" if details else name

    def _row_widgets(self) -> list:
        widgets: list = []
        for i, spec in enumerate(self._lists):
            widgets.append(
                Horizontal(
                    Button(
                        self._row_label(spec),
                        id=f"smart-apply-{i}",
                        variant="default",
                        classes="smart-apply",
                    ),
                    Button(
                        "x",
                        id=f"smart-del-{i}",
                        variant="default",
                        classes="smart-del",
                    ),
                    classes="smart-row",
                )
            )
        return widgets

    def compose(self) -> ComposeResult:
        with Vertical(id="smart-box"):
            yield Label(T("smart_title"), id="smart-title")
            yield Static(T("smart_count", n=len(self._lists)), id="smart-count")
            with VerticalScroll(id="smart-scroll"):
                with Vertical(id="smart-rows"):
                    if self._lists:
                        for w in self._row_widgets():
                            yield w
                    else:
                        yield Static(T("smart_empty"), id="smart-empty")
                if len(self._lists) >= 10:
                    yield Static(T("smart_full"))
                yield Static(self._snapshot, id="smart-snapshot")
                yield Input(placeholder=T("smart_name_ph"), id="smart-name")
            yield Static(T("smart_legend"), id="smart-legend")
            with Horizontal(id="smart-buttons", classes="btn-row"):
                yield Button(T("smart_save"), id="smart-save", variant="default")
                yield Button(T("form_cancel"), id="smart-close", variant="default")

    def on_mount(self) -> None:
        try:
            if self._lists:
                self.query_one("#smart-apply-0", Button).focus()
            else:
                self.query_one("#smart-name", Input).focus()
        except Exception:
            pass

    async def _refresh_rows(self) -> None:
        try:
            box = self.query_one("#smart-rows", Vertical)
        except Exception:
            return
        await box.remove_children()
        if self._lists:
            await box.mount(*self._row_widgets())
        else:
            await box.mount(Static(T("smart_empty"), id="smart-empty"))
        try:
            self.query_one("#smart-count", Static).update(
                T("smart_count", n=len(self._lists))
            )
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "smart-close":
            self.dismiss()
        elif bid == "smart-save":
            await self.action_save()
        elif bid.startswith("smart-apply-"):
            try:
                idx = int(bid.rsplit("-", 1)[1])
                self._on_apply(self._lists[idx]["name"])
            except (ValueError, IndexError, KeyError):
                return
            self.dismiss()
        elif bid.startswith("smart-del-"):
            try:
                idx = int(bid.rsplit("-", 1)[1])
                name = self._lists[idx]["name"]
            except (ValueError, IndexError, KeyError):
                return
            self._lists = self._on_delete(name)
            await self._refresh_rows()

    async def action_save(self) -> None:
        try:
            name = self.query_one("#smart-name", Input).value.strip()
        except Exception:
            name = ""
        ok, key, params, lists = self._on_save(name)
        if ok:
            self._lists = list(lists)
            try:
                self.query_one("#smart-name", Input).value = ""
            except Exception:
                pass
            self.notify(T(key, **params))
            await self._refresh_rows()
        else:
            self.notify(T(key, **params), severity="warning")

    async def action_delete_focused(self) -> None:
        try:
            fid = getattr(self.focused, "id", "") or ""
        except Exception:
            return
        for prefix in ("smart-apply-", "smart-del-"):
            if fid.startswith(prefix):
                try:
                    idx = int(fid.rsplit("-", 1)[1])
                    name = self._lists[idx]["name"]
                except (ValueError, IndexError, KeyError):
                    return
                self._lists = self._on_delete(name)
                await self._refresh_rows()
                return
