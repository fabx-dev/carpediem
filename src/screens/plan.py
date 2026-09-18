"""Pianificazione giornata: piano giorno, review, proposta smart, briefing sera. Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Label,
    ListItem,
    ListView,
    SelectionList,
    Static,
)

from src import domain
from src.lang import (
    T,
)
from src.models import (
    PRIORITY_ORDER,
    TodoItem,
    _due_date_part,
    _format_date_it,
    _pomo_label,
    _status,
)
from src.planner import Planner, explain
from src.screens._shared import (
    CloseMixin,
    _completed_by_date,
    _done_on_day,
    _escape_markup,
    _hero_row,
    _pomo_on_day,
    _streak_days,
    _strip_rich_tags,
)


class PlanRow(ListItem):
    """Riga del piano con task_id e sezione tipizzati (niente setattr dinamici)."""

    def __init__(self, *args, task_id=None, section: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task_id = task_id
        self.section = section


class PlanListView(ListView):
    """Lista del piano: Enter apre il dettaglio, il click sposta solo l'highlight.

    ListView binda Enter a select_cursor (ombra i binding della screen) ed emette
    Selected anche al click: per questo Enter e' ribindato qui a un dispatch verso
    la screen, mentre il click resta invariato (nessun handler Selected).
    """

    BINDINGS = [
        Binding("enter", "plan_detail", "Dettaglio", show=False),
    ]

    def action_plan_detail(self) -> None:
        handler = getattr(self.screen, "action_view_detail", None)
        if callable(handler):
            handler()


class DailyPlanScreen(CloseMixin, ModalScreen[None]):
    """Screen showing today's planned tasks with quick add/remove."""

    CSS = """
    #plan-box {
        width: 80;
        max-width: 95%;
        height: 90%;
    }
    #plan-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #plan-section {
        height: 1fr;
        margin-bottom: 1;
    }
    #plan-legend {
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("+", "add_planned", "Aggiungi al piano", show=False),
        Binding("x", "remove_planned", "Rimuovi", show=False),
        Binding("enter", "view_detail", "Dettaglio", show=False),
        Binding("space", "toggle_done", "Stato", show=False),
        Binding("o", "start_pomodoro", "Pomodoro", show=False),
        Binding("O", "pomodoro_pause", "Pausa/Riprendi", show=False),
    ]

    def __init__(
        self,
        all_todos: list[TodoItem],
        on_change,
        today: str | None = None,
        on_add=None,
        on_pomodoro_start=None,
        on_pomodoro_pause=None,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.on_change = on_change
        # store.add (per le ricorrenze create dal cambio stato); senza, fallback
        # in lista (i test senza store restano comunque verificabili).
        self.on_add = on_add
        # Timer pomodoro (vive in app): start su id esplicito, pausa globale.
        self.on_pomodoro_start = on_pomodoro_start
        self.on_pomodoro_pause = on_pomodoro_pause
        self.today = today or datetime.now().strftime("%Y-%m-%d")

    def _planned_todos(self) -> list[TodoItem]:
        return [
            t
            for t in self.all_todos
            if t.planned_for == self.today and t.state == "attivo"
        ]

    def _due_today(self) -> list[TodoItem]:
        return [
            t
            for t in self.all_todos
            if _due_date_part(t.due) == self.today
            and t.state == "attivo"
            and t.planned_for != self.today
        ]

    def _overdue(self) -> list[TodoItem]:
        try:
            today_d = datetime.strptime(self.today, "%Y-%m-%d").date()
        except ValueError:
            return []
        result = []
        for t in self.all_todos:
            if t.state != "attivo" or not t.due:
                continue
            if t.planned_for == self.today:
                continue
            try:
                d = datetime.strptime(_due_date_part(t.due), "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < today_d:
                result.append(t)
        return result

    def _upcoming(self) -> list[TodoItem]:
        try:
            today_d = datetime.strptime(self.today, "%Y-%m-%d").date()
        except ValueError:
            return []
        result = []
        for t in self.all_todos:
            if t.state != "attivo" or not t.due:
                continue
            if t.planned_for == self.today:
                continue
            try:
                d = datetime.strptime(_due_date_part(t.due), "%Y-%m-%d").date()
            except ValueError:
                continue
            if d > today_d:
                result.append(t)
        result.sort(key=lambda t: (_due_date_part(t.due) or "9999", t.id or 0))
        return result

    def _unplanned(self) -> list[TodoItem]:
        return [
            t
            for t in self.all_todos
            if t.state == "attivo" and not t.due and not t.planned_for
        ]

    @staticmethod
    def _row(t: TodoItem, marker: str, extra: str = "") -> str:
        plbl = _pomo_label(t)
        pomo = f" [red]{plbl}[/]" if plbl else ""
        return f"  [cyan]{marker}[/] {_status(t)} {_escape_markup(t.title)}{extra}  [dim]#{t.id}[/]{pomo}"

    def compose(self) -> ComposeResult:
        today_display = _format_date_it(self.today)
        with Vertical(id="plan-box"):
            yield Label(
                f"[b]{T('plan_title', date=today_display)}[/b]", id="plan-title"
            )
            planned = self._planned_todos()
            due = self._due_today()
            overdue = self._overdue()
            upcoming = self._upcoming()
            unplanned = self._unplanned()
            load = ""
            if planned:
                load_f = sum(t.pomodoros for t in planned)
                load_s = sum(getattr(t, "stima_pomo", 0) or 0 for t in planned)
                load = T("plan_load", f=load_f, s=load_s) if load_s else ""
            sections = [
                (T("plan_sec_planned", load=load), "planned", planned, "x"),
                (T("plan_sec_due"), "due", due, "+"),
                (T("plan_sec_overdue"), "overdue", overdue, "+"),
                (T("plan_sec_upcoming"), "upcoming", upcoming, "+"),
                (T("plan_sec_unplanned"), "unplanned", unplanned, "+"),
            ]
            items = [t for _h, _k, todos, _m in sections for t in todos]
            if items:
                keep = getattr(self, "_keep_id", None)
                keep_section = getattr(self, "_keep_section", None)
                children = []
                found_keep: int | None = None
                first_in_section: int | None = None
                for header, kind, todos, marker in sections:
                    if not todos:
                        continue
                    children.append(ListItem(Label(header), disabled=True))
                    for t in todos:
                        extra = (
                            T("plan_overdue_row", due=t.due)
                            if kind in ("overdue", "upcoming")
                            else ""
                        )
                        row = PlanRow(
                            Label(self._row(t, marker, extra)),
                            task_id=t.id,
                            section=kind,
                        )
                        if found_keep is None and t.id == keep:
                            found_keep = len(children)
                        if (
                            first_in_section is None
                            and keep_section is not None
                            and kind == keep_section
                        ):
                            first_in_section = len(children)
                        children.append(row)
                if found_keep is None:
                    found_keep = first_in_section
                initial = found_keep if found_keep is not None else 1
                yield PlanListView(*children, id="plan-section", initial_index=initial)
            else:
                yield Static(T("plan_empty"))
            yield Static(T("plan_legend"), id="plan-legend")
            yield Button(T("ui_close_esc"), id="plan-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#plan-section", ListView).focus()
        except Exception:
            self.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "plan-close":
            self.dismiss()

    def _current(self) -> tuple:
        """(task_id, sezione) della riga evidenziata, o (None, None)."""
        try:
            item = self.query_one("#plan-section", ListView).highlighted_child
        except Exception:
            return None, None
        if item is None:
            return None, None
        return getattr(item, "task_id", None), getattr(item, "section", None)

    def _todo_by_id(self, tid) -> TodoItem | None:
        """Rilettura per id (mai riusare oggetti stale dopo push annidati)."""
        return next((t for t in self.all_todos if t.id == tid), None)

    def _refresh_keep(self, task_id=None, section: str | None = None) -> None:
        self._keep_id = task_id
        self._keep_section = section
        self.on_change()
        self.refresh(recompose=True)

    def action_add_planned(self) -> None:
        tid, section = self._current()
        if tid is None or section not in ("due", "overdue", "upcoming", "unplanned"):
            self.notify(T("n_plan_noop"), severity="warning")
            return
        todo = next(
            (t for t in self.all_todos if t.id == tid and t.state == "attivo"), None
        )
        if todo is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        domain.plan_add(todo, self.today)
        self._refresh_keep(tid)
        self.notify(T("n_plan_added", t=_escape_markup(todo.title)))

    def action_remove_planned(self) -> None:
        tid, section = self._current()
        if tid is None or section != "planned":
            self.notify(T("n_plan_noop"), severity="warning")
            return
        for t in self.all_todos:
            if t.id == tid and t.planned_for == self.today and t.state == "attivo":
                domain.plan_remove(t)
                self._refresh_keep(tid)
                return
        self.notify(T("n_plan_rm_none"), severity="warning")

    def action_view_detail(self) -> None:
        """Enter: dettaglio del task con possibilita' di modifica (come home)."""
        tid, section = self._current()
        if tid is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        todo = self._todo_by_id(tid)
        if todo is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        # Import locale: evita dipendenze tra aree screen all'import.
        from src.screens.views import DetailScreen

        self.app.push_screen(
            DetailScreen(todo, self.all_todos),
            lambda result: self._on_detail_result(tid, section, result),
        )

    def _on_detail_result(self, tid, section: str | None, result) -> None:
        if result != "edit":
            return
        todo = self._todo_by_id(tid)
        if todo is None:
            return
        from src.screens.form import TodoFormScreen

        def on_submit(form_result: dict | None) -> None:
            if not form_result:
                return
            target = self._todo_by_id(tid)
            if target is None:
                return
            domain.apply_form(target, form_result)
            self._refresh_keep(tid, section)
            self.notify(T("n_updated", t=_escape_markup(target.title)))

        self.app.push_screen(TodoFormScreen(todo=todo, title=T("form_edit")), on_submit)

    def action_toggle_done(self) -> None:
        """Space: scelta stato completa (come home), su qualunque riga task."""
        tid, section = self._current()
        if tid is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        todo = self._todo_by_id(tid)
        if todo is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        from src.screens.form import StateChoiceScreen

        current_label = {
            "attivo": T("state_attivo"),
            "in_sospeso": T("state_sospeso"),
            "completato": T("state_completato"),
        }[todo.state]
        self.app.push_screen(
            StateChoiceScreen(todo.title, current_label, todo.state),
            lambda choice: self._on_state_picked(tid, section, choice),
        )

    def _on_state_picked(self, tid, section: str | None, choice) -> None:
        if choice is None:
            return
        todo = self._todo_by_id(tid)
        if todo is None or choice == todo.state:
            return
        labels = {
            "attivo": T("n_to_active"),
            "in_sospeso": T("n_to_paused"),
            "completato": T("n_to_done"),
        }
        new_todo = domain.apply_state(
            todo, choice, datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        if new_todo is not None:
            if self.on_add is not None:
                try:
                    self.on_add(new_todo)
                except Exception:
                    self.all_todos.append(new_todo)
            else:
                self.all_todos.append(new_todo)
            self.notify(T("n_recur", t=_escape_markup(new_todo.title), d=new_todo.due))
        self._refresh_keep(tid, section)
        self.notify(T("n_state", t=_escape_markup(todo.title), s=labels[choice]))
        if choice == "completato":
            self._ask_actual(tid, section)

    def _ask_actual(self, tid, section: str | None) -> None:
        """Chiede i pomodori reali dopo un completamento stimato (salta se no)."""
        todo = self._todo_by_id(tid)
        if todo is None:
            return
        try:
            stima = int(todo.stima_pomo or 0)
            actual = int(todo.actual_pomo or 0)
            counted = int(todo.pomodoros or 0)
        except (ValueError, TypeError):
            return
        if stima <= 0 or actual > 0:
            return
        from src.screens.form import ActualScreen

        def on_actual(result: int | None) -> None:
            if result is None:
                return
            target = self._todo_by_id(tid)
            if target is None:
                return
            domain.record_actual(target, result)
            self._refresh_keep(tid, section)
            d = result - stima
            sign = f"+{d}" if d > 0 else str(d)
            self.notify(T("n_actual_saved", a=result, s=stima, d=sign))

        self.app.push_screen(ActualScreen(todo.title, stima, counted), on_actual)

    def action_start_pomodoro(self) -> None:
        """o: avvia (o riapre) il pomodoro sul task evidenziato, come in home."""
        tid, _section = self._current()
        if tid is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        if self.on_pomodoro_start is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        try:
            self.on_pomodoro_start(tid)
        except Exception as exc:
            self.notify(T("n_exp_err", e=_escape_markup(str(exc))), severity="error")

    def action_pomodoro_pause(self) -> None:
        """O: pausa/riprendi globale, come in home (nessuna selezione richiesta)."""
        if self.on_pomodoro_pause is None:
            self.notify(T("n_plan_noop"), severity="warning")
            return
        try:
            self.on_pomodoro_pause()
        except Exception as exc:
            self.notify(T("n_exp_err", e=_escape_markup(str(exc))), severity="error")


class ReviewScreen(CloseMixin, ModalScreen[None]):
    """Chiusura giornata: riepilogo di oggi + scelta del piano di domani."""

    CSS = """
    #rev-box {
        width: 100;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #rev-list {
        height: auto;
        margin-bottom: 1;
    }
    #rev-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #rev-summary {
        height: auto;
        margin-bottom: 1;
    }
    #rev-additive {
        height: auto;
        margin-bottom: 1;
    }
    #rev-legend {
        height: auto;
    }
    #rev-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("ctrl+enter", "confirm", "Conferma", show=False),
        Binding("s", "confirm", "Conferma", show=False),
    ]

    def __init__(
        self,
        all_todos: list[TodoItem],
        on_change,
        today: str | None = None,
        daily_goal: int = 0,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.on_change = on_change
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.daily_goal = max(0, int(daily_goal or 0))
        except (ValueError, TypeError):
            self.daily_goal = 0
        try:
            self.tomorrow = (
                datetime.strptime(self.today, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
        except ValueError:
            self.tomorrow = self.today

    def _is_overdue(self, t: TodoItem) -> bool:
        due = _due_date_part(t.due)
        return bool(due) and due < self.today

    def _candidates(self) -> list[TodoItem]:
        cands = [t for t in self.all_todos if t.state == "attivo"]
        cands.sort(
            key=lambda t: (
                not self._is_overdue(t),
                _due_date_part(t.due) != self.tomorrow,
                PRIORITY_ORDER.get(t.priority.value, 9),
                _due_date_part(t.due) or "9999",
                t.title.lower(),
            )
        )
        return cands

    @staticmethod
    def _option_label(t: TodoItem) -> str:
        due = _due_date_part(t.due)
        extra = f" (scad. {due})" if due else ""
        # Niente #id in coda (resta nel value) e quadre letterali nei titoli.
        return f"{_escape_markup(t.title)}{extra}"

    def compose(self) -> ComposeResult:
        with Vertical(id="rev-box"):
            yield Label(
                f"[b]{T('rev_title', date=_format_date_it(self.today))}[/b]",
                id="rev-title",
            )
            yield Static(T("rev_additive"), id="rev-additive")
            with VerticalScroll(id="rev-scroll"):
                done = _done_on_day(self.all_todos, self.today)
                yield Static(self._summary_text(len(done)), id="rev-summary")
                yield Label(T("rev_cand", date=_format_date_it(self.tomorrow)))
                cands = self._candidates()
                if cands:
                    yield SelectionList(
                        *[
                            (self._option_label(t), t.id, i < 3)
                            for i, t in enumerate(cands)
                        ],
                        id="rev-list",
                    )
                else:
                    yield Static(T("rev_empty_cand"))
            yield Static(T("rev_legend"), id="rev-legend")
            with Horizontal(id="rev-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="rev-confirm", variant="default")
                yield Button(T("form_cancel"), id="rev-close", variant="default")

    def _summary_text(self, n_done: int) -> str:
        goal_txt = T("rev_goal", n=self.daily_goal) if self.daily_goal > 0 else ""
        return T(
            "rev_summary",
            done=n_done,
            goal=goal_txt,
            pomo=_pomo_on_day(self.all_todos, self.today),
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#rev-list", SelectionList).focus()
        except Exception:
            try:
                self.query_one("#rev-confirm", Button).focus()
            except Exception:
                self.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rev-close":
            self.dismiss()
        elif event.button.id == "rev-confirm":
            self._confirm()

    def action_confirm(self) -> None:
        self._confirm()

    def _selected_ids(self) -> set:
        try:
            return set(self.query_one("#rev-list", SelectionList).selected)
        except Exception:
            return set()

    def _confirm(self) -> None:
        selected = self._selected_ids()
        n, k = domain.review_plan(self.all_todos, selected, self.tomorrow)
        self.on_change()
        self.notify(T("n_rev_saved", n=n, k=k))
        self.dismiss()


class PlanProposalScreen(CloseMixin, ModalScreen[None]):
    """Buongiorno: contesto di oggi + proposta da confermare (scrive planned_for)."""

    CSS = """
    #planp-box {
        width: 100;
        max-width: 95%;
        height: 90%;
    }
    #planp-context {
        height: auto;
        margin-bottom: 1;
    }
    #planp-additive {
        height: auto;
        margin-bottom: 1;
    }
    #planp-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #planp-list {
        height: auto;
        margin-bottom: 1;
    }
    #planp-summary {
        height: auto;
        margin-bottom: 1;
    }
    #planp-legend {
        height: auto;
    }
    #planp-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("ctrl+enter", "confirm", "Conferma", show=False),
        Binding("s", "confirm", "Conferma", show=False),
    ]

    def __init__(
        self,
        all_todos: list[TodoItem],
        on_change,
        today: str | None = None,
        hours: float = 6.0,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.on_change = on_change
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.hours = max(1.0, float(hours))
        except (ValueError, TypeError):
            self.hours = 6.0
        self.plan = Planner(
            self.all_todos,
            today=self.today,
            hours=self.hours,
        ).propose()
        # Semantica additiva: i gia' pianificati non si ripropongono (per
        # togliere c'e' il piano giorno con x). Restano nel computo capacita'.
        planned_ids = {
            t.id
            for t in self.all_todos
            if t.state == "attivo" and t.planned_for == self.today
        }
        self.n_planned = len(planned_ids)
        self.rows = [it for it in self.plan.items if it.todo_id not in planned_ids]
        self.by_id = {t.id: t for t in self.all_todos if t.id is not None}

    @staticmethod
    def _is_cut(reasons) -> bool:
        return any(k == explain.CUT for k, _p in reasons)

    @staticmethod
    def _is_skipped(reasons) -> bool:
        return any(k == explain.SKIPPED for k, _p in reasons)

    @classmethod
    def _preselected(cls, reasons) -> bool:
        return not cls._is_cut(reasons) and not cls._is_skipped(reasons)

    def _option_label(self, t_id: int, reasons) -> str:
        t = self.by_id.get(t_id)
        title = _escape_markup(t.title) if t else f"#{t_id}"
        due = _due_date_part(t.due) if t else ""
        extra = f" (scad. {due})" if due else ""
        why = ", ".join(
            T(k, **p) for k, p in reasons if k not in (explain.CUT, explain.SKIPPED)
        )
        # Niente []: le option del SelectionList interpretano il markup Rich.
        # Niente #id in coda: gli id interni restano nel value, cosi' i motivi
        # (il vero contenuto della riga) non vengono troncati dal terminale.
        flags = "".join(
            f" — {T(k)}"
            for k in (explain.CUT, explain.SKIPPED)
            if any(k == kk for kk, _p in reasons)
        )
        return f"{title}{extra} ({why}){flags}" if why else f"{title}{extra}{flags}"

    def _context_lines(self) -> list[str]:
        """Contesto di oggi (ex briefing mattina): conteggi, carico, ieri, serie."""
        active = [t for t in self.all_todos if t.state == "attivo"]
        if not active:
            return []
        planned = [t for t in active if t.planned_for == self.today]
        due = [t for t in active if _due_date_part(t.due) == self.today]
        overdue = [
            t
            for t in active
            if _due_date_part(t.due) and _due_date_part(t.due) < self.today
        ]
        load = sum(int(t.stima_pomo or 0) for t in planned)
        cap = int(self.hours / 0.5)
        try:
            yest = (
                datetime.strptime(self.today, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y-%m-%d")
        except ValueError:
            yest = self.today
        lines = [
            T("brief_m_sec_today"),
            _hero_row(T("brief_k_plan"), str(len(planned))),
            _hero_row(T("brief_k_due"), str(len(due))),
            _hero_row(T("brief_k_over"), str(len(overdue))),
            "  " + T("brief_m_load", s=load, c=cap, h=int(self.hours)),
            "  "
            + T(
                "brief_m_yest",
                d=len(_done_on_day(self.all_todos, yest)),
                p=_pomo_on_day(self.all_todos, yest),
            ),
        ]
        by_date: dict[str, int] = {}
        for t in self.all_todos:
            if t.completed_at:
                day = t.completed_at[:10]
                by_date[day] = by_date.get(day, 0) + 1
        streak = _streak_days(by_date, self.today)
        streak_txt = (
            T("stats_serie", n=streak) if streak else T("stats_serie_off")
        ).lstrip()
        lines.append("  " + streak_txt)
        return lines

    def compose(self) -> ComposeResult:
        with Vertical(id="planp-box"):
            yield Label(
                f"[b]{T('planp_title', date=_format_date_it(self.today))}[/b]",
                id="planp-title",
            )
            yield Static(T("planp_additive"), id="planp-additive")
            with VerticalScroll(id="planp-scroll"):
                ctx = self._context_lines()
                if ctx:
                    yield Static("\n".join(ctx), id="planp-context")
                n_in = sum(1 for it in self.rows if self._preselected(it.reasons))
                yield Static(
                    T(
                        "planp_summary",
                        n=n_in,
                        m=self.n_planned,
                        c=len(self.rows) - n_in,
                        h=int(self.hours),
                    ),
                    id="planp-summary",
                )
                if self.rows:
                    yield SelectionList(
                        *[
                            (
                                self._option_label(it.todo_id, it.reasons),
                                it.todo_id,
                                self._preselected(it.reasons),
                            )
                            for it in self.rows
                        ],
                        id="planp-list",
                    )
                else:
                    yield Static(T("planp_done" if self.n_planned else "planp_empty"))
            yield Static(T("rev_legend"), id="planp-legend")
            with Horizontal(id="planp-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="planp-confirm", variant="default")
                yield Button(T("form_cancel"), id="planp-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#planp-list", SelectionList).focus()
        except Exception:
            try:
                self.query_one("#planp-confirm", Button).focus()
            except Exception:
                self.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "planp-close":
            self.dismiss()
        elif event.button.id == "planp-confirm":
            self._confirm()

    def action_confirm(self) -> None:
        self._confirm()

    def _selected_ids(self) -> set:
        try:
            return set(self.query_one("#planp-list", SelectionList).selected)
        except Exception:
            return set()

    def _confirm(self) -> None:
        # Solo additivo: aggiunge i selezionati, non toglie mai i pianificati.
        selected = self._selected_ids()
        n, r = domain.proposal_plan(self.all_todos, selected, self.today)
        self.on_change()
        self.notify(T("n_planp_saved", n=n, k=self.n_planned, r=r))
        self.dismiss()


class BriefingScreen(CloseMixin, ModalScreen[str | None]):
    """Resoconto sera: solo composizione di dati esistenti (zero rete)."""

    CSS = """
    #brief-box {
        width: 80;
        max-width: 95%;
        height: 90%;
    }
    #brief-scroll {
        height: 1fr;
    }
    #brief-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    #brief-buttons Button {
        width: 1fr;
        height: 3;
    }
    #brief-hint {
        height: auto;
        margin-top: 1;
    }
    #brief-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    .brief-line {
        height: auto;
        margin-bottom: 0;
    }
    .brief-head {
        height: auto;
        margin-top: 1;
        margin-bottom: 0;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Chiudi"),
        Binding("p", "print_brief", "Stampa", show=False),
    ]

    def __init__(
        self,
        all_todos: list[TodoItem],
        today: str | None = None,
        daily_goal: int = 0,
        on_print=None,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.daily_goal = max(0, int(daily_goal or 0))
        except (ValueError, TypeError):
            self.daily_goal = 0
        self.on_print = on_print

    def _done_on(self, day: str) -> list[TodoItem]:
        return _done_on_day(self.all_todos, day)

    def _pomo_on(self, day: str) -> int:
        return _pomo_on_day(self.all_todos, day)

    def _evening_lines(self) -> list[str]:
        done = self._done_on(self.today)
        left = [
            t
            for t in self.all_todos
            if t.state == "attivo" and t.planned_for == self.today
        ]
        pomo = self._pomo_on(self.today)
        if self.daily_goal > 0:
            filled = min(10, max(0, round(len(done) / self.daily_goal * 10)))
            bar = "█" * filled + "░" * (10 - filled)
            count = f"{len(done)}/{self.daily_goal} · {pomo} 🍅  {bar}"
        else:
            count = f"{len(done)} · {pomo} 🍅"
        lines = [T("brief_e_sec_done"), f"  {count}"]
        streak = _streak_days(_completed_by_date(self.all_todos), self.today)
        streak_txt = (
            T("stats_serie", n=streak) if streak else T("stats_serie_off")
        ).lstrip()
        lines.append("  " + streak_txt)
        lines.append(T("brief_e_sec_left"))
        if left:
            for t in left:
                lines.append(f"  • {_escape_markup(t.title)}")
        elif any((t.planned_for or "") == self.today for t in self.all_todos):
            lines.append("  " + T("brief_e_left_empty"))
        else:
            lines.append("  " + T("brief_e_left_never"))
        return lines

    def compose(self) -> ComposeResult:
        with Vertical(id="brief-box"):
            yield Label(
                f"[b]{T('brief_e_title', date=_format_date_it(self.today))}[/b]",
                id="brief-title",
            )
            with VerticalScroll(id="brief-scroll"):
                lines = self._evening_lines()
                first = True
                for line in lines:
                    yield Static(
                        line,
                        classes="brief-line" if first else "brief-head",
                    )
                    first = False
            yield Static(T("brief_e_hint"), id="brief-hint")
            with Horizontal(id="brief-buttons"):
                yield Button(T("brief_print"), id="brief-print", variant="default")
                yield Button(T("brief_goto"), id="brief-goto", variant="default")
                yield Button(T("ui_close_esc"), id="brief-close", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#brief-close", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "brief-close":
            self.dismiss()
        elif event.button.id == "brief-print":
            self._print()
        elif event.button.id == "brief-goto":
            self.dismiss("review")

    def action_print_brief(self) -> None:
        self._print()

    @classmethod
    def _plain(cls, line: str) -> str:
        return _strip_rich_tags(line)

    def _print(self) -> None:
        """Esporta il resoconto in Markdown (via callback dell'app)."""
        if self.on_print is None:
            return
        lines = self._evening_lines()
        text = "# " + T("brief_e_title", date=self.today) + "\n\n"
        text += "\n".join(self._plain(line) for line in lines) + "\n"
        try:
            path = self.on_print("evening", self.today, text)
        except Exception as exc:
            self.notify(T("n_exp_err", e=_escape_markup(str(exc))), severity="error")
            return
        self.notify(T("n_brief_printed", p=path))
