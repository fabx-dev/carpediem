"""Sistema e analisi: goals, stats, tasti, impostazioni, archivio, restore, welcome, lock, password, security, salute. Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path

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
)

from src import crypto as _crypto
from src import domain as _domain
from src.lang import (
    T,
    days_short,
    key_sections,
    months,
)
from src.models import (
    HEALTH_CRIT_LATE,
    HEALTH_CRIT_RATIO,
    Priority,
    TodoItem,
    _due_date_part,
)
from src.screens._shared import (
    CloseMixin,
    _completed_by_date,
    _escape_markup,
    _pomodoros_by_date,
    _streak_days,
    outlook_error_text,
)
from src.storage import _backup_sources, snapshot_info


class GoalsScreen(ModalScreen[dict | None]):
    """Imposta obiettivi giornaliero/settimanale (0 = disattivato)."""

    CSS = """
    #goals-box {
        width: 52;
        max-width: 90%;
        height: 90%;
        max-height: 90%;
    }
    #goals-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #goals-hint {
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
    }
    #goals-box Input {
        margin-bottom: 1;
    }
    #goals-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+enter", "submit", "Salva", show=False),
        Binding("s", "submit", "Salva", show=False),
    ]

    def __init__(self, daily: int = 5, weekly: int = 25, pomo_daily: int = 8) -> None:
        super().__init__()
        self.daily = daily
        self.weekly = weekly
        self.pomo_daily = pomo_daily

    def compose(self) -> ComposeResult:
        with Vertical(id="goals-box"):
            yield Label(T("goals_title"), id="goals-title")
            # Campi in scroll + bottoni fissi: a 70x20 il box auto usciva
            # dal viewport e Salva/Annulla erano irraggiungibili.
            with VerticalScroll(id="goals-scroll"):
                yield Label(T("goals_hint"), id="goals-hint")
                yield Label(T("goals_daily"))
                yield Input(str(self.daily), id="goals-daily")
                yield Label(T("goals_weekly"))
                yield Input(str(self.weekly), id="goals-weekly")
                yield Label(T("goals_pomo"))
                yield Input(str(self.pomo_daily), id="goals-pomo")
            with Horizontal(id="goals-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="goals-save", variant="default")
                yield Button(T("form_cancel"), id="goals-cancel", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#goals-daily", Input).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "goals-cancel":
            self.dismiss(None)
        elif event.button.id == "goals-save":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        try:
            daily = int(self.query_one("#goals-daily", Input).value.strip() or 0)
            weekly = int(self.query_one("#goals-weekly", Input).value.strip() or 0)
            pomo = int(self.query_one("#goals-pomo", Input).value.strip() or 0)
        except (ValueError, TypeError):
            self.notify(T("n_goals_int"), severity="error")
            return
        if not (0 <= daily <= 100 and 0 <= weekly <= 500 and 0 <= pomo <= 100):
            self.notify(T("n_goals_range"), severity="error")
            return
        self.dismiss({"daily": daily, "weekly": weekly, "pomo_daily": pomo})


class StatsScreen(CloseMixin, ModalScreen[None]):
    """Screen to show productivity statistics."""

    CSS = """
    #stats-box {
        width: 58;
        max-width: 92%;
        height: 90%;
    }
    #stats-scroll {
        height: 1fr;
    }
    #stats-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #stats-section {
        height: auto;
        margin-bottom: 1;
    }
    .stats-line {
        height: auto;
        margin-bottom: 0;
    }
    .stats-caption {
        height: auto;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(
        self,
        all_todos: list[TodoItem],
        daily_goal: int = 5,
        weekly_goal: int = 25,
        pomo_goal: int = 8,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.daily_goal = daily_goal
        self.weekly_goal = weekly_goal
        self.pomo_goal = pomo_goal

    STATS_SPAN = 14

    def _completed_by_date(self) -> dict[str, int]:
        return _completed_by_date(self.all_todos)

    def _pomodoros_by_date(self) -> dict[str, int]:
        return _pomodoros_by_date(self.all_todos)

    def _count_in_range(self, start: date, end: date, by_date: dict[str, int]) -> int:
        count = 0
        d = start
        while d <= end:
            count += by_date.get(d.strftime("%Y-%m-%d"), 0)
            d += timedelta(days=1)
        return count

    def _series_14(self, by_date: dict[str, int]) -> tuple[list[int], list[str]]:
        today = datetime.now().date()
        values, labels = [], []
        for offset in range(self.STATS_SPAN - 1, -1, -1):
            d = today - timedelta(days=offset)
            date_str = d.strftime("%Y-%m-%d")
            values.append(by_date.get(date_str, 0))
            labels.append(date_str)
        return values, labels

    def _peak_caption(self, values: list[int], labels: list[str]) -> str:
        top = max(values) if values else 0
        if top <= 0:
            return T("stats_peak_none")
        day = labels[values.index(top)][8:10] + "/" + labels[values.index(top)][5:7]
        return T("stats_peak", n=top, d=day)

    def _axis_caption(self) -> str:
        today = datetime.now().date()
        start = today - timedelta(days=self.STATS_SPAN - 1)
        return T(
            "stats_axis", start=start.strftime("%d/%m"), today=today.strftime("%d/%m")
        )

    HEATMAP_WEEKS = 26
    HEATMAP_LEVELS = ("·", "░", "▒", "▓", "█")

    def _heatmap_26(self) -> str:
        """Heatmap 🍅 stile GitHub: 26 settimane x 7 giorni, oggi evidenziato."""
        today = datetime.now().date()
        monday_this = today - timedelta(days=today.weekday())
        start = monday_this - timedelta(weeks=self.HEATMAP_WEEKS - 1)
        pomo_by_date = self._pomodoros_by_date()
        grid: list[list[int]] = [[0] * self.HEATMAP_WEEKS for _ in range(7)]
        future: list[list[bool]] = [[False] * self.HEATMAP_WEEKS for _ in range(7)]
        for c in range(self.HEATMAP_WEEKS):
            for r in range(7):
                d = start + timedelta(days=c * 7 + r)
                if d > today:
                    future[r][c] = True
                    continue
                grid[r][c] = pomo_by_date.get(d.strftime("%Y-%m-%d"), 0)

        def cell(v: int) -> str:
            if v <= 0:
                return self.HEATMAP_LEVELS[0]
            if v == 1:
                return self.HEATMAP_LEVELS[1]
            if v <= 3:
                return self.HEATMAP_LEVELS[2]
            if v <= 5:
                return self.HEATMAP_LEVELS[3]
            return self.HEATMAP_LEVELS[4]

        month_row = [" "] * self.HEATMAP_WEEKS
        prev_month = -1
        for c in range(self.HEATMAP_WEEKS):
            m = (start + timedelta(days=c * 7)).month
            if m != prev_month:
                month_row[c] = months()[m][:1].lower()
                prev_month = m
        lines = ["    " + "".join(month_row)]
        for r in range(7):
            row = [f"{days_short()[r]} "]
            for c in range(self.HEATMAP_WEEKS):
                if future[r][c]:
                    row.append(" ")
                elif start + timedelta(days=c * 7 + r) == today:
                    row.append(f"[bold yellow]{cell(grid[r][c])}[/]")
                else:
                    row.append(cell(grid[r][c]))
            lines.append("".join(row))
        return "\n".join(lines)

    def _render_14_histogram(self, values: list[int], labels: list[str]) -> str:
        """Istogramma 14 colonne a larghezza fissa: barra + giorno sotto, oggi evidenziato."""
        mx = max(values) if values and max(values) > 0 else 1
        rows: list[str] = []
        for level in range(4, 0, -1):
            cells = []
            for i, v in enumerate(values):
                filled = "██" if v * 4 >= mx * level else "  "
                if i == len(values) - 1:
                    cells.append(f"[bold yellow]{filled}[/]")
                elif v == mx:
                    cells.append(f"[green]{filled}[/]")
                else:
                    cells.append(filled)
            rows.append(" ".join(cells))
        day_cells = []
        for i, lab in enumerate(labels):
            dd = lab[8:10]
            day_cells.append(f"[bold]{dd}[/]" if i == len(labels) - 1 else dd)
        rows.append(" ".join(day_cells))
        return "\n".join(rows)

    def _streak(self, by_date: dict[str, int]) -> int:
        """Giorni consecutivi con >=1 completamento (oggi o da ieri se oggi e' a zero)."""
        today = datetime.now().date().strftime("%Y-%m-%d")
        return _streak_days(by_date, today)

    def _goal_streaks(self, by_date: dict[str, int]) -> dict:
        """Streak attuali e massime vs obiettivi giornaliero/settimanale."""
        today = datetime.now().date()
        dg, wg = self.daily_goal, self.weekly_goal
        out = {"d_cur": 0, "d_max": 0, "w_cur": 0, "w_max": 0, "w_now": 0}
        if dg > 0:
            d = (
                today
                if by_date.get(today.strftime("%Y-%m-%d"), 0) >= dg
                else today - timedelta(days=1)
            )
            while by_date.get(d.strftime("%Y-%m-%d"), 0) >= dg:
                out["d_cur"] += 1
                d -= timedelta(days=1)
            if by_date:
                first = min(datetime.strptime(k, "%Y-%m-%d").date() for k in by_date)
                dd, run = first, 0
                while dd <= today:
                    if by_date.get(dd.strftime("%Y-%m-%d"), 0) >= dg:
                        run += 1
                        out["d_max"] = max(out["d_max"], run)
                    else:
                        run = 0
                    dd += timedelta(days=1)
        if wg > 0 and by_date:
            weeks: dict[tuple[int, int], int] = {}
            for k, v in by_date.items():
                try:
                    dt = datetime.strptime(k, "%Y-%m-%d").date()
                except ValueError:
                    continue
                wk = (dt.isocalendar()[0], dt.isocalendar()[1])
                weeks[wk] = weeks.get(wk, 0) + v
            cur_wk = (today.isocalendar()[0], today.isocalendar()[1])
            out["w_now"] = weeks.get(cur_wk, 0)
            wk = cur_wk if out["w_now"] >= wg else self._prev_week(cur_wk)
            while weeks.get(wk, 0) >= wg:
                out["w_cur"] += 1
                wk = self._prev_week(wk)
            run = 0
            for wk in sorted(weeks):
                if weeks[wk] >= wg:
                    run += 1
                    out["w_max"] = max(out["w_max"], run)
                else:
                    run = 0
        return out

    @staticmethod
    def _prev_week(wk: tuple[int, int]) -> tuple[int, int]:
        y, w = wk
        if w > 1:
            return (y, w - 1)
        prev_dec28 = datetime(y - 1, 12, 28).date()
        return (y - 1, prev_dec28.isocalendar()[1])

    @property
    def TIME_SLOTS(self) -> tuple[tuple[str, int, int], ...]:
        # property (non attributo di classe): T() va valutato a render-time,
        # altrimenti le fasce restano nella lingua di avvio dopo un cambio lingua.
        return (
            (T("slot_night"), 0, 6),
            (T("slot_morning"), 6, 12),
            (T("slot_afternoon"), 12, 18),
            (T("slot_evening"), 18, 24),
        )

    @staticmethod
    def _hour_of(ts: str) -> int | None:
        try:
            h = int(str(ts)[11:13])
            return h if 0 <= h <= 23 else None
        except (ValueError, TypeError, IndexError):
            return None

    def _slot_counts(self, days: int = 30) -> list[tuple[str, int, int]]:
        """(fascia, completati, pomodori) negli ultimi N giorni."""
        start = (datetime.now().date() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        comp = [0] * len(self.TIME_SLOTS)
        pomo = [0] * len(self.TIME_SLOTS)
        for t in self.all_todos:
            if t.completed_at and t.completed_at[:10] >= start:
                h = self._hour_of(t.completed_at)
                if h is not None:
                    for i, (_, lo, hi) in enumerate(self.TIME_SLOTS):
                        if lo <= h < hi:
                            comp[i] += 1
                            break
            for ts in getattr(t, "pomodoro_log", []) or []:
                if str(ts)[:10] >= start:
                    h = self._hour_of(str(ts))
                    if h is not None:
                        for i, (_, lo, hi) in enumerate(self.TIME_SLOTS):
                            if lo <= h < hi:
                                pomo[i] += 1
                                break
        return [
            (name, comp[i], pomo[i]) for i, (name, _, _) in enumerate(self.TIME_SLOTS)
        ]

    def _weekday_counts(self, weeks: int = 8) -> list[tuple[str, int, int]]:
        """(giorno Lun-Dom, completati, pomodori) nelle ultime N settimane."""
        start = (datetime.now().date() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        comp = [0] * 7
        pomo = [0] * 7
        for t in self.all_todos:
            if t.completed_at and t.completed_at[:10] >= start:
                try:
                    wd = (
                        datetime.strptime(t.completed_at[:10], "%Y-%m-%d")
                        .date()
                        .weekday()
                    )
                    comp[wd] += 1
                except ValueError:
                    pass
            for ts in getattr(t, "pomodoro_log", []) or []:
                if str(ts)[:10] >= start:
                    try:
                        wd = (
                            datetime.strptime(str(ts)[:10], "%Y-%m-%d").date().weekday()
                        )
                        pomo[wd] += 1
                    except ValueError:
                        pass
        return [(days_short()[i], comp[i], pomo[i]) for i in range(7)]

    def _punctuality(self) -> tuple[int, int, int]:
        """(puntuali, con scadenza, %) sui completati datati che avevano una scadenza."""
        on_time = total = 0
        for t in self.all_todos:
            if t.done and t.completed_at and t.due:
                total += 1
                if t.completed_at[:10] <= _due_date_part(t.due):
                    on_time += 1
        pct = round(on_time * 100 / total) if total else 0
        return on_time, total, pct

    def _project_breakdown(self, days: int = 7) -> list[tuple[str, int, int]]:
        """(progetto, completati, pomodori) negli ultimi N giorni, i migliori prima."""
        start = (datetime.now().date() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        comp: dict[str, int] = {}
        for t in self.all_todos:
            if t.completed_at and t.completed_at[:10] >= start:
                proj = t.project or "—"
                comp[proj] = comp.get(proj, 0) + 1
        pomo: dict[str, int] = {}
        for t in self.all_todos:
            for ts in getattr(t, "pomodoro_log", []) or []:
                if str(ts)[:10] >= start:
                    proj = t.project or "—"
                    pomo[proj] = pomo.get(proj, 0) + 1
        rows = [(p, comp.get(p, 0), pomo.get(p, 0)) for p in set(comp) | set(pomo)]
        rows.sort(key=lambda r: (r[1] + r[2], r[1]), reverse=True)
        return rows[:8]

    def compose(self) -> ComposeResult:
        by_date = self._completed_by_date()
        pomo_by_date = self._pomodoros_by_date()
        today = datetime.now().date()
        span_ago = today - timedelta(days=self.STATS_SPAN - 1)
        week_ago = today - timedelta(days=6)
        month_ago = today - timedelta(days=29)
        today_c = by_date.get(today.strftime("%Y-%m-%d"), 0)
        week_c = self._count_in_range(week_ago, today, by_date)
        month_c = self._count_in_range(month_ago, today, by_date)
        total_done = sum(1 for t in self.all_todos if t.done)
        dated_done = sum(by_date.values())
        undated_done = total_done - dated_done
        alta = sum(1 for t in self.all_todos if t.done and t.priority == Priority.HIGH)
        media = sum(
            1 for t in self.all_todos if t.done and t.priority == Priority.MEDIUM
        )
        bassa = sum(1 for t in self.all_todos if t.done and t.priority == Priority.LOW)
        pomo_today = pomo_by_date.get(today.strftime("%Y-%m-%d"), 0)
        pomo_14 = self._count_in_range(span_ago, today, pomo_by_date)
        pomo_total = sum(t.pomodoros for t in self.all_todos)
        pomo_dated = sum(pomo_by_date.values())
        pomo_undated = pomo_total - pomo_dated
        streak = self._streak(by_date)
        gs = self._goal_streaks(by_date)
        done_values, done_labels = self._series_14(by_date)
        pomo_values, _ = self._series_14(pomo_by_date)

        with Vertical(id="stats-box"):
            yield Label(T("stats_title"), id="stats-title")
            with VerticalScroll(id="stats-scroll"):
                if self.daily_goal > 0:
                    yield Static(
                        T(
                            "stats_goal_today",
                            done=today_c,
                            goal=self.daily_goal,
                            cur=gs["d_cur"],
                            mx=gs["d_max"],
                        ),
                        id="stats-section",
                    )
                else:
                    yield Static(T("stats_goal_off"), id="stats-section")
                if self.weekly_goal > 0:
                    yield Static(
                        T(
                            "stats_week",
                            now=gs["w_now"],
                            goal=self.weekly_goal,
                            cur=gs["w_cur"],
                            mx=gs["w_max"],
                        ),
                        classes="stats-line",
                    )
                yield Static(
                    T("stats_serie", n=streak) if streak else T("stats_serie_off"),
                    classes="stats-line",
                )
                yield Static(T("stats_today", n=today_c), classes="stats-line")
                yield Static(T("stats_7", n=week_c), classes="stats-line")
                yield Static(T("stats_30", n=month_c), classes="stats-line")
                yield Static(T("stats_tot", n=total_done), classes="stats-line")
                if undated_done:
                    yield Static(
                        T("stats_undated", n=undated_done), classes="stats-line"
                    )
                yield Static(
                    T("stats_prio", a=alta, m=media, b=bassa),
                    classes="stats-line",
                )
                proj_rows = self._project_breakdown(7)
                if proj_rows:
                    yield Label(T("stats_proj_t"), classes="stats-line")
                    for proj, nc, np in proj_rows:
                        yield Static(
                            f"  [blue]{_escape_markup(proj)}[/]: {nc} · {np}",
                            classes="stats-line",
                        )
                yield Label(T("stats_when_t"), classes="stats-line")
                slot_rows = {n: (c, p) for n, c, p in self._slot_counts(30)}
                for name, lo, hi in self.TIME_SLOTS:
                    sc, sp = slot_rows.get(name, (0, 0))
                    yield Static(
                        f"  {name} ({lo}-{hi}): {sc} · {sp}", classes="stats-line"
                    )
                yield Label(T("stats_wday_t"), classes="stats-line")
                for g, wc, wp in self._weekday_counts(8):
                    yield Static(f"  {g}: {wc} · {wp}", classes="stats-line")
                pt_on, pt_tot, pt_pct = self._punctuality()
                if pt_tot:
                    yield Static(
                        T("stats_punct", pct=pt_pct, ok=pt_on, tot=pt_tot),
                        classes="stats-line",
                    )
                pomo_goal_txt = (
                    f"{pomo_today}/{self.pomo_goal}"
                    if self.pomo_goal > 0
                    else str(pomo_today)
                )
                yield Static(
                    T("stats_pomo", t=pomo_goal_txt, f=pomo_14, tot=pomo_total),
                    classes="stats-line",
                )
                if pomo_undated > 0:
                    yield Static(
                        T("stats_undated", n=pomo_undated), classes="stats-line"
                    )
                calib = _domain.calibration_factor(self.all_todos)
                if calib is not None:
                    yield Static(
                        T(
                            "stats_calib",
                            f=f"x{calib:.1f}",
                            n=_domain.calibration_samples(self.all_todos),
                        ),
                        classes="stats-line",
                    )
                yield Label(T("stats_done14"), classes="stats-line")
                yield Static(
                    self._render_14_histogram(done_values, done_labels),
                    id="stats-hist-done",
                )
                yield Static(f" [dim]{self._axis_caption()}[/]", classes="stats-line")
                yield Static(
                    f" [dim]{self._peak_caption(done_values, done_labels)} · {T('stats_last_today')}[/]",
                    classes="stats-caption",
                )
                yield Label(T("stats_pomo14"), classes="stats-line")
                yield Static(
                    self._render_14_histogram(pomo_values, done_labels),
                    id="stats-hist-pomo",
                )
                yield Static(f" [dim]{self._axis_caption()}[/]", classes="stats-line")
                yield Static(
                    f" [dim]{self._peak_caption(pomo_values, done_labels)} · {T('stats_last_today')}[/]",
                    classes="stats-caption",
                )
                yield Label(T("stats_heat_t"), classes="stats-line")
                yield Static(self._heatmap_26(), id="stats-heatmap")
                yield Static(T("stats_heat_leg"), classes="stats-caption")
            yield Button(T("ui_close_esc"), id="stats-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stats-close":
            self.dismiss()

    def on_mount(self) -> None:
        try:
            self.query_one("#stats-close", Button).focus()
        except Exception:
            pass


class KeysScreen(CloseMixin, ModalScreen[None]):
    """Popup con tutte le combinazioni di tasti (voce Tasti del menu)."""

    CSS = """
    #keys-box {
        width: 66;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #keys-list {
        height: 1fr;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def compose(self) -> ComposeResult:
        with Vertical(id="keys-box"):
            yield Label(f"[b]{T('keys_title')}[/b]", id="keys-title")
            with VerticalScroll(id="keys-list"):
                for section, rows in key_sections():
                    yield Label(f"[b]{section}[/b]")
                    for key, desc in rows:
                        yield Static(f"  [b]{key}[/b]  {desc}")
            yield Button(f"{T('b_close')} [escape]", id="keys-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "keys-close":
            self.dismiss()

    def on_mount(self) -> None:
        try:
            self.query_one("#keys-close", Button).focus()
        except Exception:
            pass


class SettingsScreen(ModalScreen[dict | None]):
    """Impostazioni app: tema, vista, obiettivi, durate pomodoro."""

    CSS = """
    #set-box {
        width: 60;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #set-body {
        width: 100%;
        height: 1fr;
    }
    #set-body Input {
        margin-bottom: 1;
    }
    #set-body Label {
        margin-bottom: 0;
    }
    #set-buttons {
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

    def __init__(self, themes: list[str], current: dict) -> None:
        super().__init__()
        self.themes = themes
        self.current = dict(current)

    def compose(self) -> ComposeResult:
        filt = self.current.get("filter_state") or "tutti"
        with Vertical(id="set-box"):
            yield Label(T("set_title"), id="set-title")
            with VerticalScroll(id="set-body", can_focus=False):
                yield Label(T("set_theme"))
                yield Select(
                    [(t, t) for t in self.themes],
                    value=self.current.get("theme", "matrix"),
                    id="set-theme",
                )
                yield Label(T("set_lang"))
                yield Select(
                    [
                        (T("set_lang_auto"), "auto"),
                        ("Italiano", "it"),
                        ("English", "en"),
                    ],
                    value=self.current.get("lang", "auto"),
                    id="set-lang",
                )
                yield Label(T("set_kanban"))
                yield Select(
                    [(T("set_kanban_on"), True), (T("set_kanban_off"), False)],
                    value=bool(self.current.get("kanban_visible", True)),
                    id="set-kanban",
                )
                yield Label(T("set_filter"))
                yield Select(
                    [
                        (T("set_filter_attivo"), "attivo"),
                        (T("set_filter_sospeso"), "in_sospeso"),
                        (T("set_filter_completati"), "completati"),
                        (T("set_filter_tutti"), "tutti"),
                    ],
                    value=filt,
                    id="set-filter",
                )
                yield Label(T("set_daily"))
                yield Input(str(self.current.get("daily_goal", 5)), id="set-daily")
                yield Label(T("set_weekly"))
                yield Input(str(self.current.get("weekly_goal", 25)), id="set-weekly")
                yield Label(T("set_pomo"))
                yield Input(
                    str(self.current.get("pomo_daily_goal", 8)), id="set-pomo-goal"
                )
                yield Label(T("set_hours"))
                yield Input(str(self.current.get("day_hours", 6)), id="set-hours")
                yield Label(T("set_focus"))
                yield Input(str(self.current.get("focus_min", 25)), id="set-focus")
                yield Label(T("set_short"))
                yield Input(str(self.current.get("short_min", 5)), id="set-short")
                yield Label(T("set_long"))
                yield Input(str(self.current.get("long_min", 15)), id="set-long")
                yield Label(T("set_every"))
                yield Input(str(self.current.get("long_every", 4)), id="set-every")
                yield Label(T("set_reminder"))
                yield Input(
                    str(self.current.get("reminder_min", 10)), id="set-reminder"
                )
                yield Label(T("set_sounds"))
                yield Select(
                    [(T("set_yes"), True), (T("set_no"), False)],
                    value=bool(self.current.get("sounds", True)),
                    id="set-sounds",
                )
            with Horizontal(id="set-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="set-save", variant="default")
                yield Button(T("form_cancel"), id="set-cancel", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#set-theme", Select).focus()
        except Exception:
            pass
        # Il focus trascina lo scroll del layout provvisorio (stessa lezione
        # di Buongiorno): scroll_home differito dopo il relayout.
        self.call_after_refresh(self._scroll_top)

    def _scroll_top(self) -> None:
        try:
            self.query_one("#set-body").scroll_home(animate=False)
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "set-cancel":
            self.dismiss(None)
        elif event.button.id == "set-save":
            self._submit()

    def _num(self, vid: str, lo: int, hi: int) -> int | None:
        try:
            v = int(self.query_one(f"#{vid}", Input).value.strip() or 0)
        except (ValueError, TypeError):
            self.query_one(f"#{vid}", Input).focus()
            self.notify(T("n_set_num", lo=lo, hi=hi), severity="error")
            return None
        if not (lo <= v <= hi):
            self.query_one(f"#{vid}", Input).focus()
            self.notify(T("n_set_range", lo=lo, hi=hi), severity="error")
            return None
        return v

    def _submit(self) -> None:
        theme = self.query_one("#set-theme", Select).value
        kanban = self.query_one("#set-kanban", Select).value
        filt = self.query_one("#set-filter", Select).value
        lang = self.query_one("#set-lang", Select).value
        daily = self._num("set-daily", 0, 100)
        weekly = self._num("set-weekly", 0, 500)
        pomo = self._num("set-pomo-goal", 0, 100)
        hours = self._num("set-hours", 1, 16)
        focus = self._num("set-focus", 1, 180)
        short = self._num("set-short", 1, 60)
        longm = self._num("set-long", 1, 60)
        every = self._num("set-every", 2, 12)
        reminder = self._num("set-reminder", 0, 120)
        sounds = self.query_one("#set-sounds", Select).value
        if None in (daily, weekly, pomo, focus, short, longm, every, reminder, hours):
            return
        self.dismiss(
            {
                "theme": theme,
                "kanban_visible": bool(kanban),
                "filter_state": None if filt == "tutti" else filt,
                "daily_goal": daily,
                "weekly_goal": weekly,
                "pomo_daily_goal": pomo,
                "day_hours": hours,
                "focus_min": focus,
                "short_min": short,
                "long_min": longm,
                "long_every": every,
                "lang": lang if lang in ("auto", "it", "en") else "auto",
                "reminder_min": reminder,
                "sounds": bool(sounds),
            }
        )


class ArchiveScreen(ModalScreen[tuple | None]):
    """Archivio completati: ripristina singoli o tutti."""

    CSS = """
    #arc-box {
        width: 64;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #arc-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #arc-list Button {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-bottom: 1;
    }
    #arc-actions {
        width: 100%;
        height: 3;
    }
    #arc-actions Button {
        width: 1fr;
        min-width: 12;
        height: 3;
        margin: 0 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, archived: list[TodoItem]) -> None:
        super().__init__()
        self.archived = archived

    def compose(self) -> ComposeResult:
        with Vertical(id="arc-box"):
            yield Label(T("arc_title", n=len(self.archived)), id="arc-title")
            with VerticalScroll(id="arc-list"):
                if not self.archived:
                    yield Label(T("arc_empty"))
                for i, t in enumerate(self.archived):
                    when = (t.completed_at or "?")[:10]
                    proj = f" @{_escape_markup(t.project)}" if t.project else ""
                    yield Button(
                        f"#{t.id} {_escape_markup(t.title[:36])}{proj} ({when})",
                        id=f"arc-{i}",
                        variant="default",
                    )
            with Horizontal(id="arc-actions"):
                yield Button(T("arc_all"), id="arc-all", variant="default")
                yield Button(T("ui_close_esc"), id="arc-close", variant="default")

    def on_mount(self) -> None:
        try:
            first = self.query("#arc-list Button")
            (first.first() if first else self.query_one("#arc-close", Button)).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "arc-close":
            self.dismiss(None)
        elif bid == "arc-all":
            self.dismiss(("all", None))
        elif bid.startswith("arc-"):
            try:
                self.dismiss(("one", int(bid[len("arc-") :])))
            except ValueError:
                pass

    def action_close(self) -> None:
        self.dismiss(None)


class RestoreScreen(ModalScreen[str | None]):
    """Sceglie uno snapshot da ripristinare."""

    CSS = """
    #rst-box {
        width: 64;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #rst-list {
        height: 1fr;
        margin-bottom: 1;
    }
    #rst-list Button {
        width: 100%;
        min-width: 16;
        height: 3;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, snapshots: list[Path]) -> None:
        super().__init__()
        self.snapshots = snapshots

    def compose(self) -> ComposeResult:
        with Vertical(id="rst-box"):
            yield Label(T("rst_title"), id="rst-title")
            with VerticalScroll(id="rst-list"):
                if not self.snapshots:
                    yield Label(T("rst_empty"))
                for i, p in enumerate(self.snapshots):
                    info = snapshot_info(p)
                    files = info.get("files", {})
                    n = files.get("todos", "?")
                    kb = info.get("size", 0) // 1024
                    yield Button(
                        T("rst_row", created=info.get("created", "?"), n=n, kb=kb),
                        id=f"rst-{i}",
                        variant="default",
                    )
            yield Button(T("ui_close_esc"), id="rst-close", variant="default")

    def on_mount(self) -> None:
        try:
            first = self.query("#rst-list Button")
            (first.first() if first else self.query_one("#rst-close", Button)).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "rst-close":
            self.dismiss(None)
        elif bid.startswith("rst-"):
            try:
                self.dismiss(str(self.snapshots[int(bid[len("rst-") :])]))
            except (ValueError, IndexError):
                pass

    def action_close(self) -> None:
        self.dismiss(None)


class WelcomeScreen(ModalScreen[str | None]):
    """Benvenuto con scelta demo/vuoto (solo al primo avvio senza task)."""

    CSS = """
    #wel-box {
        width: 60;
        max-width: 92%;
        height: auto;
    }
    #wel-body {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        height: auto;
    }
    #wel-buttons {
        width: 100%;
        height: 3;
    }
    #wel-sec {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [Binding("escape", "empty", "Vuoto")]

    def compose(self) -> ComposeResult:
        with Vertical(id="wel-box"):
            yield Label(T("welcome_title"), id="wel-title")
            yield Label(T("welcome_body"), id="wel-body")
            with Horizontal(id="wel-buttons", classes="btn-row"):
                yield Button(T("welcome_demo"), id="wel-demo", variant="default")
                yield Button(T("welcome_empty"), id="wel-empty", variant="default")
            yield Label(
                T(
                    "welcome_sec_hint",
                    cat=T("menu_cat_sys_t"),
                    voce=T("menu_security_t"),
                ),
                id="wel-sec",
            )

    def on_mount(self) -> None:
        try:
            self.query_one("#wel-demo", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "wel-empty":
            self.dismiss("empty")
        elif event.button.id == "wel-demo":
            self.dismiss("demo")

    def action_empty(self) -> None:
        self.dismiss("empty")


class LockScreen(ModalScreen[bool]):
    """Blocco password all'avvio (solo se dati cifrati)."""

    CSS = """
    #lock-box {
        width: 52;
        max-width: 90%;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #lock-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
        height: auto;
    }
    #lock-hint {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
    }
    #lock-pw {
        margin-bottom: 1;
    }
    #lock-buttons {
        width: 100%;
        height: 3;
    }
    """

    BINDINGS = [Binding("escape", "abort", "Esci")]

    def compose(self) -> ComposeResult:
        with Vertical(id="lock-box"):
            yield Label("[b]🔒 CarpeDiem protetto[/b]", id="lock-title")
            yield Label(T("lock_hint"), id="lock-hint")
            yield Input(placeholder="Password", password=True, id="lock-pw")
            with Horizontal(id="lock-buttons", classes="btn-row"):
                yield Button(T("lock_open"), id="lock-ok", variant="default")
                yield Button(T("lock_exit"), id="lock-exit", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#lock-pw", Input).focus()
        except Exception:
            pass

    def action_abort(self) -> None:
        self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "lock-exit":
            self.dismiss(False)
        elif event.button.id == "lock-ok":
            self._submit()

    def _submit(self) -> None:
        pw_input = self.query_one("#lock-pw", Input)
        password = pw_input.value
        if not password:
            pw_input.focus()
            return
        ok = True
        for name, path in _backup_sources():
            if name == "config":
                continue
            try:
                if path.exists() and not _crypto.try_password(password, path):
                    ok = False
                    break
            except OSError:
                pass
        if not ok:
            pw_input.value = ""
            pw_input.disabled = True
            self.notify(T("n_lock_bad"), severity="error")
            self.set_timer(1.0, self._reenable)
            return
        _crypto.set_key(_crypto.encode_password(password))
        self.dismiss(True)

    def _reenable(self) -> None:
        try:
            pw_input = self.query_one("#lock-pw", Input)
            pw_input.disabled = False
            pw_input.focus()
        except Exception:
            pass


class PasswordScreen(ModalScreen[list[str] | None]):
    """Raccoglie 1-3 password (niente logica: valida il chiamante)."""

    CSS = """
    #pw-box {
        width: 52;
        max-width: 90%;
        height: auto;
    }
    #pw-box Input {
        margin-bottom: 1;
    }
    #pw-box Label {
        margin-bottom: 0;
    }
    #pw-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+enter", "submit", "Conferma", show=False),
        Binding("s", "submit", "Conferma", show=False),
    ]

    def __init__(self, title_key: str, fields: list[str], validate=None) -> None:
        super().__init__()
        self.title_key = title_key
        self.fields = fields
        self._validate = validate

    def compose(self) -> ComposeResult:
        with Vertical(id="pw-box"):
            yield Label(T(self.title_key), id="pw-title")
            with Vertical(id="pw-body"):
                for i, label_key in enumerate(self.fields):
                    yield Label(T(label_key))
                    yield Input(password=True, id=f"pw-{i}")
            with Horizontal(id="pw-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="pw-ok", variant="default")
                yield Button(T("form_cancel"), id="pw-cancel", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#pw-0", Input).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pw-cancel":
            self.dismiss(None)
        elif event.button.id == "pw-ok":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        try:
            values = [
                self.query_one(f"#pw-{i}", Input).value for i in range(len(self.fields))
            ]
        except Exception:
            return
        if self._validate is not None:
            err = self._validate(values)
            if err:
                self.notify(err, severity="error")
                try:
                    self.query_one("#pw-0", Input).focus()
                except Exception:
                    pass
                return
        self.dismiss(values)


class SecurityScreen(ModalScreen[str | None]):
    """Stato cifratura + azioni (dismiss 'enable'/'change'/'disable'/None)."""

    CSS = """
    #sec-box {
        width: 56;
        max-width: 92%;
        height: auto;
    }
    #sec-status {
        text-align: center;
        margin-bottom: 1;
        height: auto;
    }
    #sec-hint {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
    }
    #sec-buttons {
        width: 100%;
        height: auto;
    }
    #sec-buttons Button {
        width: 100%;
        min-width: 0;
        height: 3;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, enabled: bool) -> None:
        super().__init__()
        self.enabled = enabled

    def compose(self) -> ComposeResult:
        with Vertical(id="sec-box"):
            yield Label(T("sec_title"), id="sec-title")
            yield Label(T("sec_on") if self.enabled else T("sec_off"), id="sec-status")
            yield Label(T("sec_hint"), id="sec-hint")
            with Vertical(id="sec-buttons"):
                if self.enabled:
                    yield Button(T("sec_change"), id="sec-change", variant="default")
                    yield Button(T("sec_disable"), id="sec-disable", variant="default")
                else:
                    yield Button(T("sec_enable"), id="sec-enable", variant="default")
                yield Button(T("ui_close_esc"), id="sec-close", variant="default")

    def on_mount(self) -> None:
        try:
            first = self.query("#sec-buttons Button")
            if first:
                first.first().focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "sec-close":
            self.dismiss(None)
        elif bid in ("sec-enable", "sec-change", "sec-disable"):
            self.dismiss(bid[len("sec-") :])

    def action_close(self) -> None:
        self.dismiss(None)


class OutlookSetupScreen(ModalScreen[dict | None]):
    """Collega il calendario Outlook (registrazione Entra propria).

    Dumb come le altre form-screen: la rete/auth resta nei callback `hooks`
    (stesso seam di Buongiorno), qui solo stati form -> codice -> attesa.
    Ritorna {"config": {...}} collegato, {"disconnect": True} scollegato,
    None se annullato (Esc in qualunque momento, niente scritture).
    """

    CSS = """
    #outlook-box {
        width: 64;
        max-width: 94%;
        height: 90%;
        max-height: 90%;
    }
    #outlook-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #outlook-hint {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #outlook-scroll Input {
        margin-bottom: 1;
    }
    #outlook-status {
        height: auto;
        margin-top: 1;
    }
    #outlook-code {
        height: auto;
        margin-top: 1;
    }
    #outlook-code.hidden {
        display: none;
    }
    #outlook-buttons {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Annulla"),
        Binding("ctrl+enter", "submit", "Collega", show=False),
        Binding("s", "submit", "Collega", show=False),
    ]

    def __init__(
        self,
        current: dict | None,
        has_token: bool = False,
        hooks=None,
    ) -> None:
        super().__init__()
        self.current = dict(current) if isinstance(current, dict) else {}
        self.has_token = bool(has_token)
        self.hooks = hooks
        self._waiting = False
        self._flow = None

    def compose(self) -> ComposeResult:
        with Vertical(id="outlook-box"):
            yield Label(T("outlook_title"), id="outlook-title")
            with VerticalScroll(id="outlook-scroll"):
                yield Label(T("outlook_hint"), id="outlook-hint")
                yield Label(T("outlook_client"))
                yield Input(
                    str(self.current.get("client_id", "") or ""), id="outlook-client"
                )
                yield Label(T("outlook_tenant"))
                yield Input(
                    str(self.current.get("tenant", "") or ""), id="outlook-tenant"
                )
                yield Label(T("outlook_account"))
                yield Input(
                    str(self.current.get("account", "") or ""), id="outlook-account"
                )
                yield Label(T("outlook_tz"))
                yield Input(
                    str(self.current.get("tz", "") or "Europe/Rome"), id="outlook-tz"
                )
                yield Static("", id="outlook-status")
                yield Static("", id="outlook-code", classes="hidden")
            with Horizontal(id="outlook-buttons", classes="btn-row"):
                yield Button(
                    T("outlook_connect"), id="outlook-connect", variant="default"
                )
                if self.has_token:
                    yield Button(
                        T("outlook_disconnect"),
                        id="outlook-disconnect",
                        variant="default",
                    )
                yield Button(T("form_cancel"), id="outlook-cancel", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#outlook-client", Input).focus()
        except Exception:
            pass

    def action_cancel(self) -> None:
        self._waiting = False
        self.dismiss(None)

    def action_submit(self) -> None:
        try:
            asyncio.create_task(self._do_connect())
        except RuntimeError:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "outlook-cancel":
            self.action_cancel()
        elif bid == "outlook-connect":
            self.action_submit()
        elif bid == "outlook-disconnect":
            unlink = (
                getattr(self.hooks, "unlink", None) if self.hooks is not None else None
            )
            if callable(unlink):
                try:
                    unlink()
                except Exception:
                    pass
            self._waiting = False
            self.dismiss({"disconnect": True})

    def _read_form(self) -> dict | None:
        """Config validata o None (errore gia' mostrato nello status)."""
        try:
            client_id = self.query_one("#outlook-client", Input).value.strip()
            tenant = self.query_one("#outlook-tenant", Input).value.strip()
            account = self.query_one("#outlook-account", Input).value.strip()
            tz = self.query_one("#outlook-tz", Input).value.strip() or "Europe/Rome"
        except Exception:
            return None
        if (
            not client_id
            or not tenant
            or tenant.lower() in ("common", "consumers", "organizations")
            or (account and "@" not in account)
        ):
            self._status(T("outlook_bad_form"))
            return None
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(tz)
        except Exception:
            tz = "Europe/Rome"
        return {
            "client_id": client_id[:128],
            "tenant": tenant[:128],
            "account": account[:254],
            "tz": tz,
        }

    def _status(self, text: str) -> None:
        try:
            self.query_one("#outlook-status", Static).update(text)
        except Exception:
            pass

    def _show_code(self, uri: str, code: str) -> None:
        try:
            widget = self.query_one("#outlook-code", Static)
            widget.update(T("outlook_code", uri=uri, code=code))
            widget.remove_class("hidden")
        except Exception:
            pass

    def _hide_code(self) -> None:
        try:
            widget = self.query_one("#outlook-code", Static)
            widget.update("")
            widget.add_class("hidden")
        except Exception:
            pass

    async def _do_connect(self) -> None:
        """Form -> device flow (thread) -> attesa conferma -> dismiss."""
        hooks = self.hooks
        connect = getattr(hooks, "connect", None) if hooks is not None else None
        if not callable(connect):
            self._status(T("outlook_err_generic", e="—"))
            return
        cfg = self._read_form()
        if cfg is None:
            return
        try:
            started = await asyncio.to_thread(connect, cfg)
        except Exception as exc:
            started = {"ok": False, "code": "generic", "detail": str(exc)[:120]}
        if (
            not self.is_mounted
            or not isinstance(started, dict)
            or not started.get("ok")
        ):
            if not self.is_mounted:
                return
            code = (
                started.get("code", "generic")
                if isinstance(started, dict)
                else "generic"
            )
            detail = started.get("detail", "") if isinstance(started, dict) else ""
            self._status(outlook_error_text(code, detail))
            return
        self._flow = started.get("flow")
        self._show_code(str(started.get("uri", "")), str(started.get("code", "")))
        self._status(T("outlook_wait"))
        self._waiting = True
        poll = getattr(hooks, "poll", None) if hooks is not None else None
        if not callable(poll):
            self._waiting = False
            self._status(T("outlook_err_generic", e="—"))
            return
        try:
            result = await asyncio.to_thread(poll, self._flow)
        except Exception as exc:
            result = {"ok": False, "code": "generic", "detail": str(exc)[:120]}
        self._waiting = False
        if not self.is_mounted:
            return
        if not isinstance(result, dict) or not result.get("ok"):
            code = (
                result.get("code", "generic") if isinstance(result, dict) else "generic"
            )
            detail = result.get("detail", "") if isinstance(result, dict) else ""
            self._status(outlook_error_text(code, detail))
            self._hide_code()
            return
        username = str(result.get("username", "") or cfg.get("account", ""))
        cfg["account"] = username
        self.dismiss({"config": cfg})


class HealthScreen(CloseMixin, ModalScreen[None]):
    """Salute progetti: avanzamento, ritardi, momentum, verdetto."""

    CSS = """
    #hea-box {
        width: 64;
        max-width: 92%;
        height: 90%;
        max-height: 90%;
    }
    #hea-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 0;
        height: auto;
    }
    #hea-hint {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
    }
    #hea-list {
        height: 1fr;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "close", "Chiudi")]

    def __init__(self, all_todos: list[TodoItem]) -> None:
        super().__init__()
        self.all_todos = all_todos

    def _rows(self) -> list[tuple]:
        """(progetto, verdetto, colore, fatti, tot, ritardo, momentum7). Peggiori prima."""
        today = datetime.now().date()
        today_s = today.strftime("%Y-%m-%d")
        w0 = (today - timedelta(days=6)).strftime("%Y-%m-%d")
        w1 = (today - timedelta(days=13)).strftime("%Y-%m-%d")
        agg: dict[str, dict] = {}

        def bucket(proj: str) -> dict:
            return agg.setdefault(
                proj, {"tot": 0, "done": 0, "late": 0, "now": 0, "prev": 0}
            )

        for t in self.all_todos:
            if t.is_subtask or not t.project:
                continue
            if t.done:
                a = bucket(t.project)
                a["tot"] += 1
                a["done"] += 1
                d = (t.completed_at or "")[:10]
                if w0 <= d <= today_s:
                    a["now"] += 1
                elif w1 <= d < w0:
                    a["prev"] += 1
            elif t.state != "completato":
                a = bucket(t.project)
                a["tot"] += 1
                if _due_date_part(t.due) and _due_date_part(t.due) < today_s:
                    a["late"] += 1
        out = []
        for proj, a in agg.items():
            if a["tot"] <= 0:
                continue
            ratio = a["done"] / a["tot"]
            if a["late"] >= HEALTH_CRIT_LATE or (
                ratio < HEALTH_CRIT_RATIO and a["late"] > 0
            ):
                verdict, color, rank = T("health_crit"), "red", 0
            elif a["late"] > 0 or (a["now"] - a["prev"]) < 0:
                verdict, color, rank = T("health_risk"), "yellow", 1
            else:
                verdict, color, rank = T("health_ok"), "green", 2
            out.append(
                (
                    rank,
                    proj,
                    verdict,
                    color,
                    a["done"],
                    a["tot"],
                    a["late"],
                    a["now"] - a["prev"],
                )
            )
        out.sort(key=lambda r: (r[0], r[1]))
        return [(p, v, c, d, t, ll, mm) for _, p, v, c, d, t, ll, mm in out]

    def compose(self) -> ComposeResult:
        with Vertical(id="hea-box"):
            yield Label(T("health_title"), id="hea-title")
            yield Label(T("health_hint"), id="hea-hint")
            with VerticalScroll(id="hea-list"):
                rows = self._rows()
                if not rows:
                    yield Label(T("health_empty"))
                for proj, verdict, color, done, tot, late, mom in rows:
                    sign = "+" if mom > 0 else ""
                    yield Label(f"[{color}][b]{verdict}[/b][/] {_escape_markup(proj)}")
                    yield Static(
                        T(
                            "health_row",
                            done=done,
                            tot=tot,
                            late=late,
                            mom=f"{sign}{mom}",
                        )
                    )
            yield Button(T("ui_close_esc"), id="hea-close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hea-close":
            self.dismiss()

    def on_mount(self) -> None:
        try:
            self.query_one("#hea-close", Button).focus()
        except Exception:
            pass
