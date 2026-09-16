"""Screen di input e dialoghi (form, esempi NL, conferme, stato, tema, ricerca). Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

import calendar
from datetime import date, datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
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
    days_short,
    get_lang,
    months,
    prio_disp,
    rec_disp,
)
from src.models import (
    Priority,
    Recurrence,
    TodoItem,
    _due_date_part,
    _due_time_part,
    _is_valid_date,
    _normalize_date,
)
from src.nlparse import parse_with_found
from src.screens._shared import (
    CloseMixin,
    _escape_markup,
)


class TodoFormScreen(ModalScreen[dict | None]):
    """Modal screen to add or edit a todo item."""

    CSS = """
    #form-container {
        width: 72;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
        border: thick $primary;
        background: $surface;
        padding: 0 2 1 2;
    }
    #form-title-wrap {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }
    #form-title {
        width: auto;
        text-style: bold;
        color: $primary;
        height: auto;
        border: solid $primary;
        padding: 0 1;
    }
    #form-body {
        width: 100%;
        height: 1fr;
    }
    #form-body Input {
        margin-bottom: 1;
    }
    #title-input {
        border: solid $primary-darken-1;
        padding: 0 1;
    }
    #nl-preview {
        width: 1fr;
        height: auto;
        margin-bottom: 1;
    }
    #nl-syntax {
        width: 1fr;
        height: auto;
        margin-bottom: 0;
    }
    #nl-try {
        height: auto;
        margin-bottom: 1;
        text-style: underline;
        color: $primary;
    }
    #form-body Label {
        margin-bottom: 0;
    }
    #row-priorita-ricorrenza {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #col-priorita {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }
    #col-ricorrenza {
        width: 1fr;
        height: auto;
        margin-left: 1;
    }
    #row-tags-due, #row-prog-due, #row-tags {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #col-tags, #col-project {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }
    #col-stima {
        width: 20;
        min-width: 12;
        height: auto;
        margin-left: 1;
    }
    #col-due {
        width: 1fr;
        height: auto;
        margin-left: 1;
    }
    #due-row {
        width: 100%;
        height: 3;
    }
    #due-row Input {
        width: 1fr;
        height: 3;
        margin-bottom: 0;
    }
    #due-cal-btn {
        width: 4;
        min-width: 4;
        height: 3;
        margin-left: 1;
        margin-bottom: 0;
    }
    #notes-textarea {
        height: 6;
        margin-bottom: 1;
        border: solid $primary-darken-1;
    }
    #form-buttons {
        align: center middle;
        margin-top: 1;
        width: 100%;
        height: 3;
        dock: bottom;
    }
    #form-buttons Button {
        margin: 0 1;
        width: 1fr;
        min-width: 18;
        height: 3;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+enter", "submit", "Salva", show=False),
        Binding("ctrl+l", "fill_nl", "Compila", show=False),
        Binding("s", "submit", "Salva", show=False),
    ]

    def __init__(
        self, todo: TodoItem | None = None, title: str = "", preset_project: str = ""
    ) -> None:
        super().__init__()
        self.todo = todo
        self.screen_title = title or T("form_new")
        self.preset_project = (preset_project or "").strip().lower()

    @staticmethod
    def _nl_example() -> str:
        """Esempio del giorno (rotazione deterministica, screenshot al sicuro)."""
        examples = [T("nl_exa1"), T("nl_exa2"), T("nl_exa3")]
        return examples[datetime.now().date().toordinal() % len(examples)]

    def compose(self) -> ComposeResult:
        with Vertical(id="form-container"):
            with Horizontal(id="form-title-wrap"):
                yield Label(self.screen_title, id="form-title")
            with VerticalScroll(id="form-body", can_focus=False):
                yield Input(
                    placeholder=T("form_title_ph", ex=self._nl_example()),
                    id="title-input",
                )
                yield Label(f"[dim]{T('nl_hint')}[/]", id="nl-preview")
                yield Label(f"[dim]{T('nl_syntax')}[/]", id="nl-syntax")
                yield Label(T("nl_try"), id="nl-try")
                yield Label(T("form_notes"))
                yield TextArea("", id="notes-textarea")
                with Horizontal(id="row-prog-due"):
                    with Vertical(id="col-project"):
                        yield Label(T("form_project"))
                        yield Input(
                            placeholder=T("form_project_ph"), id="project-input"
                        )
                    with Vertical(id="col-due"):
                        yield Label(T("form_due"))
                        with Horizontal(id="due-row"):
                            yield Input(placeholder=T("form_due_ph"), id="due-input")
                            yield Button(
                                "📅",
                                id="due-cal-btn",
                                variant="default",
                                tooltip=T("form_due_cal"),
                            )
                with Horizontal(id="row-tags"):
                    with Vertical(id="col-tags"):
                        yield Label(T("form_tags"))
                        yield Input(placeholder=T("form_tags_ph"), id="tags-input")
                    with Vertical(id="col-stima"):
                        yield Label(T("form_stima"))
                        yield Input(placeholder=T("form_stima_ph"), id="stima-input")
                with Horizontal(id="row-priorita-ricorrenza"):
                    with Vertical(id="col-priorita"):
                        yield Label(T("form_priority"))
                        yield Select(
                            [(prio_disp(p.value), p) for p in Priority],
                            value=self.todo.priority if self.todo else Priority.MEDIUM,
                            id="priority-select",
                        )
                    with Vertical(id="col-ricorrenza"):
                        yield Label(T("form_recurrence"))
                        yield Select(
                            [(rec_disp(r.value), r) for r in Recurrence],
                            value=self.todo.recurrence
                            if self.todo
                            else Recurrence.NONE,
                            id="recurrence-select",
                        )
            with Horizontal(id="form-buttons"):
                yield Button(T("form_save"), id="save-btn", variant="default")
                yield Button(T("form_cancel"), id="cancel-btn", variant="default")

    def on_mount(self) -> None:
        if self.todo:
            self.query_one("#title-input", Input).value = self.todo.title
            self.query_one("#notes-textarea", TextArea).text = self.todo.notes
            self.query_one("#due-input", Input).value = self.todo.due
            self.query_one("#project-input", Input).value = self.todo.project
            if self.todo.tags:
                self.query_one("#tags-input", Input).value = ", ".join(self.todo.tags)
            if self.todo and self.todo.stima_pomo:
                self.query_one("#stima-input", Input).value = str(self.todo.stima_pomo)
        elif self.preset_project:
            # Nuovo sotto-task: mostra l'ereditarieta' dal padre (modificabile).
            self.query_one("#project-input", Input).value = self.preset_project
        # Form con campi: il focus sta sul primo campo (scrivere e' l'azione primaria).
        try:
            self.query_one("#title-input", Input).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def action_fill_nl(self) -> None:
        """Compila SOLO i campi trovati nel titolo (ctrl+l); mai overwrite.

        A titolo vuoto apre il foglio esempi invece di lamentarsi.
        """
        raw = self.query_one("#title-input", Input).value.strip()
        if not raw:
            # Niente import di app (convenzione): self.app e' runtime Textual.
            self.app.push_screen(NLHelpScreen())
            return
        res, found = parse_with_found(raw, get_lang())
        # Firma anti-eco: il Changed asincrono del set programmatico viene ignorato.
        self._nl_filled = res["title"]
        self.query_one("#title-input", Input).value = res["title"]
        if "due" in found:
            self.query_one("#due-input", Input).value = res["due"]
        if "project" in found:
            self.query_one("#project-input", Input).value = res["project"]
        if "tags" in found:
            self.query_one("#tags-input", Input).value = ", ".join(res["tags"])
        if "stima_pomo" in found:
            stima = int(res["stima_pomo"] or 0)
            self.query_one("#stima-input", Input).value = str(stima) if stima else ""
        if "priority" in found:
            self.query_one("#priority-select", Select).value = res["priority"]
        if "recurrence" in found:
            self.query_one("#recurrence-select", Select).value = res["recurrence"]
        if "notes" in found:
            self.query_one("#notes-textarea", TextArea).text = res["notes"]
        self.query_one("#nl-preview", Label).update(self._nl_summary(res, found))
        try:
            self.query_one("#save-btn", Button).focus()
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Anteprima live mentre digiti il titolo (compila solo con ctrl+l)."""
        try:
            if event.input.id != "title-input":
                return
            if event.value == getattr(self, "_nl_filled", None):
                return  # eco del fill programmatico: preview gia' impostata
            self._nl_filled = None
            res, found = parse_with_found(event.value, get_lang())
            if len(found) > 1:
                self.query_one("#nl-preview", Label).update(
                    self._nl_summary(res, found)
                )
            else:
                self.query_one("#nl-preview", Label).update(f"[dim]{T('nl_hint')}[/]")
        except Exception:
            pass

    @staticmethod
    def _nl_summary(res: dict, found: set | None = None) -> str:
        parts = []
        if res["due"]:
            parts.append(_escape_markup(res["due"]))
        if res["project"]:
            parts.append(f"*{_escape_markup(res['project'])}")
        parts.extend(f"#{_escape_markup(t)}" for t in res["tags"])
        if res["priority"] != Priority.MEDIUM:
            parts.append(f"!{res['priority'].value}")
        if res["recurrence"] != Recurrence.NONE:
            parts.append(rec_disp(res["recurrence"].value))
        if int(res["stima_pomo"] or 0):
            parts.append(f"~{res['stima_pomo']}")
        if res["notes"]:
            parts.append("// …")
        if not parts:
            return f"[dim]{T('nl_none')}[/]"
        return T("nl_preview", s=" · ".join(parts))

    def on_click(self, event) -> None:
        """Solo il link esempi; gli altri click scorrono liberi (niente stop)."""
        try:
            widget, _region = self.get_widget_at(event.screen_x, event.screen_y)
        except Exception:
            return
        if widget is not None and getattr(widget, "id", None) == "nl-try":
            self._insert_example()

    def _insert_example(self) -> None:
        """Scrive l'esempio nel titolo solo se vuoto (mai distruggere digitato)."""
        try:
            title_input = self.query_one("#title-input", Input)
        except Exception:
            return
        if title_input.value.strip():
            self.notify(T("nl_title_busy"), severity="warning")
            return
        title_input.value = self._nl_example()
        title_input.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            self._submit()
        elif event.button.id == "due-cal-btn":
            self._open_calendar()

    def _open_calendar(self) -> None:
        current = self.query_one("#due-input", Input).value.strip()
        self.app.push_screen(CalendarPickScreen(initial=current), self._on_cal_pick)

    def _on_cal_pick(self, picked: str | None) -> None:
        if not picked:
            return
        time_part = _due_time_part(self.query_one("#due-input", Input).value.strip())
        self.query_one("#due-input", Input).value = (
            f"{picked} {time_part}" if time_part else picked
        )
        try:
            self.query_one("#save-btn", Button).focus()
        except Exception:
            pass

    def _submit(self) -> None:
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            title_input = self.query_one("#title-input", Input)
            title_input.border_title = T("form_need_title")
            title_input.focus()
            self.notify(T("n_title_req"), severity="warning")
            return
        priority = self.query_one("#priority-select", Select).value
        due_raw = self.query_one("#due-input", Input).value.strip()
        due = _normalize_date(due_raw)
        if due_raw and not _is_valid_date(due):
            due_input = self.query_one("#due-input", Input)
            due_input.border_title = T("form_need_date")
            due_input.focus()
            self.notify(T("n_date_bad"), severity="error")
            return
        notes = self.query_one("#notes-textarea", TextArea).text.strip()
        recurrence = self.query_one("#recurrence-select", Select).value
        tags_raw = self.query_one("#tags-input", Input).value.strip()
        tags = (
            [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
            if tags_raw
            else []
        )
        project = self.query_one("#project-input", Input).value.strip().lower()
        stima_raw = self.query_one("#stima-input", Input).value.strip()
        try:
            stima = max(0, int(stima_raw)) if stima_raw else 0
        except (ValueError, TypeError):
            stima_input = self.query_one("#stima-input", Input)
            stima_input.border_title = T("form_need_num")
            stima_input.focus()
            self.notify(T("n_stima_bad"), severity="error")
            return
        self.dismiss(
            {
                "title": title,
                "priority": priority,
                "due": due,
                "notes": notes,
                "recurrence": recurrence,
                "tags": tags,
                "project": project,
                "stima_pomo": stima,
            }
        )


class CalendarPickScreen(ModalScreen[str | None]):
    """Popup calendario mensile per scegliere la data di scadenza.

    Ritorna "YYYY-MM-DD" (o None con Esc). Solo composizione: non tocca il
    disco; il form applica la scelta al campo scadenza (orario preservato).
    """

    CSS = """
    #calpick-box {
        width: 46;
        max-width: 95%;
        height: 30;
        max-height: 90%;
    }
    #calpick-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        height: auto;
    }
    #calpick-nav {
        align: center middle;
        margin-bottom: 1;
        width: 100%;
        height: 3;
    }
    #calpick-nav Button {
        margin: 0 1;
        width: 1fr;
        min-width: 10;
        height: 3;
    }
    #calpick-head {
        width: 100%;
        height: 1;
        text-style: bold;
        margin-bottom: 0;
    }
    #calpick-grid {
        width: 100%;
        height: 1fr;
        margin-bottom: 1;
    }
    .calpick-row {
        width: 100%;
        height: 3;
    }
    .calpick-cell {
        width: 1fr;
        height: 3;
        min-width: 0;
        padding: 0;
        margin: 0;
    }
    .calpick-empty {
        width: 1fr;
        height: 3;
        min-width: 0;
        margin: 0;
    }
    .calpick-today {
        border: thick $warning;
    }
    .calpick-sel {
        border: thick $primary;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("enter", "select", "Scegli", show=False),
        Binding("left", "focus_prev", "Sinistra", show=False),
        Binding("right", "focus_next", "Destra", show=False),
        Binding("up", "focus_up", "Sopra", show=False),
        Binding("down", "focus_down", "Sotto", show=False),
    ]

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self.selected = self._parse_initial(initial)
        self.year = self.selected.year if self.selected else datetime.now().year
        self.month = self.selected.month if self.selected else datetime.now().month

    @staticmethod
    def _parse_initial(value: str) -> date | None:
        part = _due_date_part(value)
        if not part:
            return None
        try:
            return datetime.strptime(part, "%Y-%m-%d").date()
        except ValueError:
            return None

    def compose(self) -> ComposeResult:
        month_name = months()[self.month]
        with Vertical(id="calpick-box"):
            yield Label(f"[b]{month_name} {self.year}[/b]", id="calpick-title")
            with Horizontal(id="calpick-nav"):
                yield Button(T("nav_prev"), id="calpick-prev", variant="default")
                yield Button(T("cal_today"), id="calpick-today", variant="default")
                yield Button(T("nav_next"), id="calpick-next", variant="default")
            yield Static(" ".join(f"{g:^3}" for g in days_short()), id="calpick-head")
            with VerticalScroll(id="calpick-grid", can_focus=False):
                today = datetime.now().date()
                for week in calendar.Calendar(firstweekday=0).monthdayscalendar(
                    self.year, self.month
                ):
                    with Horizontal(classes="calpick-row"):
                        for day in week:
                            if day == 0:
                                yield Static("   ", classes="calpick-empty")
                            else:
                                yield self._day_button(day, today)
            yield Button(T("ui_close_esc"), id="calpick-close", variant="default")

    def _day_button(self, day: int, today: date) -> Button:
        d = date(self.year, self.month, day)
        classes = "calpick-cell"
        if d == today:
            classes += " calpick-today"
        if self.selected and d == self.selected:
            classes += " calpick-sel"
        return Button(str(day), id=f"calpick-day-{day}", classes=classes)

    def _days(self) -> list[int]:
        return [d for d in range(1, 32) if self._valid(d)]

    def _valid(self, day: int) -> bool:
        try:
            date(self.year, self.month, day)
            return True
        except ValueError:
            return False

    def _focus_index(self) -> int:
        f = self.focused
        cur = f.id if f is not None else None
        days = self._days()
        if cur and cur.startswith("calpick-day-"):
            try:
                return days.index(int(cur[len("calpick-day-") :]))
            except (ValueError, IndexError):
                pass
        if self.selected and self.selected.year == self.year:
            try:
                return days.index(self.selected.day)
            except ValueError:
                pass
        return days.index(datetime.now().day) if datetime.now().day in days else 0

    def _focus_day(self, idx: int) -> None:
        days = self._days()
        idx = max(0, min(idx, len(days) - 1))
        try:
            self.query_one(f"#calpick-day-{days[idx]}", Button).focus()
        except Exception:
            pass

    def _shift(self, delta: int) -> None:
        self._focus_day(self._focus_index() + delta)

    def action_focus_prev(self) -> None:
        self._shift(-1)

    def action_focus_next(self) -> None:
        self._shift(1)

    def action_focus_up(self) -> None:
        self._shift(-7)

    def action_focus_down(self) -> None:
        self._shift(7)

    def action_select(self) -> None:
        f = self.focused
        if f is not None and f.id and f.id.startswith("calpick-day-"):
            self._dismiss_day(int(f.id[len("calpick-day-") :]))

    def _dismiss_day(self, day: int) -> None:
        try:
            self.dismiss(date(self.year, self.month, day).strftime("%Y-%m-%d"))
        except ValueError:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "calpick-close":
            self.dismiss(None)
        elif bid == "calpick-prev":
            self._shift_month(-1)
        elif bid == "calpick-next":
            self._shift_month(1)
        elif bid == "calpick-today":
            self._go_today()
        elif bid.startswith("calpick-day-"):
            self._dismiss_day(int(bid[len("calpick-day-") :]))

    def _shift_month(self, delta: int) -> None:
        self.month += delta
        if self.month < 1:
            self.month = 12
            self.year -= 1
        if self.month > 12:
            self.month = 1
            self.year += 1
        self.refresh(recompose=True)

    def _go_today(self) -> None:
        self.year = datetime.now().year
        self.month = datetime.now().month
        self.refresh(recompose=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_mount(self) -> None:
        self._focus_day(self._focus_index())


class NLHelpScreen(CloseMixin, ModalScreen[None]):
    """Foglio esempi per l'inserimento in linguaggio naturale."""

    CSS = """
    #nlh-box {
        width: 72;
        max-width: 95%;
        height: auto;
        max-height: 90%;
    }
    #nlh-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        height: auto;
    }
    .nlh-line {
        height: auto;
        margin-bottom: 0;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    ROWS = (
        "nl_h_due",
        "nl_h_proj",
        "nl_h_tags",
        "nl_h_prio",
        "nl_h_est",
        "nl_h_rec",
        "nl_h_notes",
    )

    def compose(self) -> ComposeResult:
        with Vertical(id="nlh-box"):
            yield Label(f"[b]{T('nl_help_t')}[/b]", id="nlh-title")
            for key in self.ROWS:
                yield Label(f"  {T(key)}", classes="nlh-line")
            yield Label(f"  [dim]{T('nl_ex1')}[/]", classes="nlh-line")
            yield Label(f"  [dim]{T('nl_ex2')}[/]", classes="nlh-line")
            yield Button(T("ui_close_esc"), id="nlh-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#nlh-close", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nlh-close":
            self.dismiss()


class ConfirmScreen(ModalScreen[bool]):
    """Simple confirmation dialog."""

    CSS = """
    #confirm-box {
        width: 60;
        max-width: 90%;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #confirm-msg {
        text-align: center;
        margin-bottom: 1;
    }
    #confirm-buttons {
        align: center middle;
        width: 100%;
        height: 3;
    }
    #confirm-buttons Button {
        margin: 0 1;
        width: 1fr;
        min-width: 12;
        height: 3;
    }
    """

    BINDINGS = [Binding("escape", "no", "No")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.message, id="confirm-msg")
            with Horizontal(id="confirm-buttons"):
                yield Button(T("confirm_yes"), id="yes-btn", variant="error")
                yield Button(T("b_cancel"), id="no-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes-btn")

    def on_mount(self) -> None:
        # Focus sull'azione principale: Enter conferma senza mouse (Esc annulla).
        try:
            self.query_one("#yes-btn", Button).focus()
        except Exception:
            pass

    def action_no(self) -> None:
        self.dismiss(False)


class StateChoiceScreen(ModalScreen[str | None]):
    """Menu scelta per lo stato di un todo (Space)."""

    CSS = """
    #state-box {
        width: 38;
        max-width: 90%;
        height: auto;
    }
    #state-buttons {
        width: 100%;
        height: auto;
    }
    #state-row-1, #state-row-2 {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    #state-row-1 Button, #state-row-2 Button {
        width: 1fr;
        min-width: 0;
        height: 3;
        margin: 0 1;
    }
    #state-legend {
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("left", "focus_prev", "Precedente", show=False),
        Binding("right", "focus_next", "Successivo", show=False),
        Binding("up", "focus_up", "Sopra", show=False),
        Binding("down", "focus_down", "Sotto", show=False),
    ]

    def __init__(self, title: str, current: str, current_state: str = "attivo") -> None:
        super().__init__()
        self.todo_title = title
        self.current = current
        self.current_state = (
            current_state
            if current_state in ("attivo", "in_sospeso", "completato")
            else "attivo"
        )

    def _button_label(self, state: str, key: str) -> str:
        label = T(key)
        if state == self.current_state:
            label = f"● {label}"
        return label

    def compose(self) -> ComposeResult:
        with Vertical(id="state-box"):
            yield Label(
                T(
                    "state_title",
                    title=_escape_markup(self.todo_title),
                    current=self.current,
                ),
                id="state-msg",
            )
            with Vertical(id="state-buttons"):
                with Horizontal(id="state-row-1"):
                    yield Button(
                        self._button_label("attivo", "state_btn_attivo"),
                        id="attivo-btn",
                        variant="default",
                    )
                    yield Button(
                        self._button_label("in_sospeso", "state_btn_sospeso"),
                        id="sospeso-btn",
                        variant="default",
                    )
                with Horizontal(id="state-row-2"):
                    yield Button(
                        self._button_label("completato", "state_btn_completato"),
                        id="completato-btn",
                        variant="default",
                    )
                    yield Button(T("ui_cancel_esc"), id="cancel-btn", variant="default")
            yield Static(T("state_legend"), id="state-legend")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "attivo-btn": "attivo",
            "sospeso-btn": "in_sospeso",
            "completato-btn": "completato",
        }
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id in mapping:
            self.dismiss(mapping[event.button.id])

    _STATE_FOCUS = {
        "attivo": "#attivo-btn",
        "in_sospeso": "#sospeso-btn",
        "completato": "#completato-btn",
    }

    def on_mount(self) -> None:
        try:
            self.query_one(
                self._STATE_FOCUS.get(self.current_state, "#attivo-btn"), Button
            ).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    _STATE_FOCUS_IDS = ("attivo-btn", "sospeso-btn", "completato-btn", "cancel-btn")

    def _focus_shift(self, delta: int) -> None:
        """Sposta il focus di delta posizioni nella griglia 2x2."""
        try:
            focused = self.focused
            cur = focused.id if focused is not None else None
            idx = (
                self._STATE_FOCUS_IDS.index(cur) if cur in self._STATE_FOCUS_IDS else 0
            )
            nxt = idx + delta
            if 0 <= nxt < len(self._STATE_FOCUS_IDS):
                self.query_one(f"#{self._STATE_FOCUS_IDS[nxt]}", Button).focus()
        except Exception:
            pass

    def action_focus_prev(self) -> None:
        self._focus_shift(-1)

    def action_focus_next(self) -> None:
        self._focus_shift(1)

    def action_focus_up(self) -> None:
        self._focus_shift(-2)

    def action_focus_down(self) -> None:
        self._focus_shift(2)


class ThemeListScreen(ModalScreen[str | None]):
    """Popup con lista temi selezionabile."""

    CSS = """
    #theme-box {
        width: 52;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #theme-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #theme-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #theme-list Button {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-bottom: 0;
        text-align: left;
        content-align: left middle;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("up", "cursor_up", "Su", show=False, priority=True),
        Binding("down", "cursor_down", "Giu", show=False, priority=True),
    ]

    def __init__(self, themes: list[str], current: str) -> None:
        super().__init__()
        self.themes = themes
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-box"):
            yield Label(T("theme_title"), id="theme-title")
            with VerticalScroll(id="theme-list"):
                for name in self.themes:
                    label = f"● {name}" if name == self.current else f"○ {name}"
                    yield Button(label, id=f"theme-{name}", variant="default")
            yield Button(T("ui_close_esc"), id="theme-close", variant="default")

    def on_mount(self) -> None:
        # Focus sul tema corrente (o Chiudi): stile deterministico.
        try:
            buttons = [b for b in self.query("#theme-list Button")]
            target = next((b for b in buttons if b.id == f"theme-{self.current}"), None)
            (target or self.query_one("#theme-close", Button)).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "theme-close":
            self.dismiss(None)
        elif bid.startswith("theme-"):
            self.dismiss(bid[len("theme-") :])

    def _focusables(self) -> list[Button]:
        try:
            return [
                *self.query("#theme-list Button"),
                self.query_one("#theme-close", Button),
            ]
        except Exception:
            return []

    def _step_focus(self, delta: int) -> None:
        items = self._focusables()
        if not items:
            return
        cur = -1 if delta > 0 else 0
        if isinstance(self.focused, Button):
            try:
                cur = items.index(self.focused)
            except ValueError:
                pass
        try:
            items[(cur + delta) % len(items)].focus()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        self._step_focus(-1)

    def action_cursor_down(self) -> None:
        self._step_focus(1)

    def action_close(self) -> None:
        self.dismiss(None)


class RadarPickScreen(CloseMixin, ModalScreen[int | None]):
    """Popup di scelta quando il click sul radar copre N task sovrapposti."""

    CSS = """
    #pick-box {
        width: 60;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #pick-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #pick-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #pick-list Button {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-bottom: 0;
        text-align: left;
        content-align: left middle;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("up", "cursor_up", "Su", show=False, priority=True),
        Binding("down", "cursor_down", "Giu", show=False, priority=True),
    ]

    def __init__(self, rows: list[tuple[int, str, int]]) -> None:
        """rows: (id, titolo, giorni-a-scadenza) gia' ordinati per vicinanza."""
        super().__init__()
        self.rows = rows

    def compose(self) -> ComposeResult:
        with Vertical(id="pick-box"):
            yield Label(T("radar_pick_title"), id="pick-title")
            with VerticalScroll(id="pick-list"):
                for i, (tid, title, h) in enumerate(self.rows):
                    label = f"{T('radar_worst_one', id=tid, h=h)} {_escape_markup(title[:30])}"
                    # id con indice: mai DuplicateIds con dati corrotti (id doppi).
                    yield Button(label, id=f"pick-{i}", variant="default")
            yield Button(T("ui_close_esc"), id="pick-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query("#pick-list Button").first().focus()
        except Exception:
            try:
                self.query_one("#pick-close", Button).focus()
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "pick-close":
            self.dismiss(None)
        elif bid.startswith("pick-"):
            try:
                self.dismiss(self.rows[int(bid[len("pick-") :])][0])
            except (ValueError, IndexError):
                self.dismiss(None)

    def _focusables(self) -> list[Button]:
        try:
            return [
                *self.query("#pick-list Button"),
                self.query_one("#pick-close", Button),
            ]
        except Exception:
            return []

    def _step_focus(self, delta: int) -> None:
        items = self._focusables()
        if not items:
            return
        cur = -1 if delta > 0 else 0
        if isinstance(self.focused, Button):
            try:
                cur = items.index(self.focused)
            except ValueError:
                pass
        try:
            items[(cur + delta) % len(items)].focus()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        self._step_focus(-1)

    def action_cursor_down(self) -> None:
        self._step_focus(1)

    def action_close(self) -> None:
        self.dismiss(None)


class SearchScreen(ModalScreen[str | None]):
    """Popup ricerca full-text con / ."""

    CSS = """
    #search-box {
        width: 60;
        max-width: 90%;
        height: auto;
    }
    #search-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #search-input {
        margin-bottom: 1;
    }
    #search-buttons {
        width: 100%;
        height: 3;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Annulla")]

    def __init__(self, current: str = "") -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="search-box"):
            yield Label(T("search_title"), id="search-title")
            yield Input(
                value=self.current, placeholder=T("search_ph"), id="search-input"
            )
            with Horizontal(id="search-buttons", classes="btn-row"):
                yield Button(T("b_search"), id="ok-btn", variant="default")
                yield Button(T("search_clear"), id="clear-btn", variant="default")

    def on_mount(self) -> None:
        # Query presente -> focus su Pulisci (Enter azzera); vuota -> cursore nel campo.
        try:
            if (self.current or "").strip():
                self.query_one("#clear-btn", Button).focus()
            else:
                self.query_one("#search-input", Input).focus()
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok-btn":
            self.dismiss(self.query_one("#search-input", Input).value.strip())
        elif event.button.id == "clear-btn":
            self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss(None)
