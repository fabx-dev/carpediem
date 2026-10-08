"""Pianificazione giornata: piano giorno, review, proposta smart, briefing sera. Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    SelectionList,
    Static,
    TextArea,
)

from src import domain
from src.lang import (
    T,
)
from src.models import (
    PRIORITY_ORDER,
    Priority,
    TodoItem,
    _due_date_part,
    _format_date_it,
    _pomo_label,
    _status,
)
from src.planner import (
    Planner,
    capacity,
    deadlines_for,
    diagnose,
    events_to_busy,
    explain,
)
from src.planner import feedback as planner_feedback
from src.planner import plan as plan_request
from src.planner.models import (
    DayPlan,
    FixedEvent,
    PlanItem,
    PlanningRequest,
    PlanningResult,
    ScheduledDayPlan,
    TimeWindow,
)
from src.planner.outcomes import OUT_ELIGIBLE, classify
from src.planner.phrases import phrase_for
from src.planner.replan import ADDED, DROPPED, KEPT, MOVED, replan
from src.planner.time_model import as_moment
from src.screens._shared import (
    CloseMixin,
    _completed_by_date,
    _done_on_day,
    _escape_markup,
    _hero_row,
    _pomo_on_day,
    _streak_days,
    _strip_rich_tags,
    outlook_error_text,
)


class PlanRow(ListItem):
    """Riga del piano con task_id e sezione tipizzati (niente setattr dinamici)."""

    def __init__(self, *args, task_id=None, section: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task_id = task_id
        self.section = section


_EVENT_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})(?:\s+(.*?))?\s*$")
_HHMM_RE = re.compile(r"^\d{1,2}:\d{2}$")


@dataclass
class OutlookHooks:
    """Seam Buongiorno <-> Outlook (implementato dall'app).

    Ogni hook ritorna dict (mai eccezioni oltre il seam): {"ok": True, ...}
    o {"ok": False, "code": ..., "detail": ...}. Tutti opzionali (None =
    feature disattivata). Le screen non importano mai outlook_auth (rete):
    lo usa solo l'app; qui solo callback + mapping errori condiviso.
    """

    fetch: object = None  # () -> risultato fetch del giorno
    state: object = None  # () -> {"config": dict|None, "has_token": bool}
    save: object = None  # (cfg) -> None (salva config validata)
    merge: object = None  # (patch) -> None (fonde chiavi, es. account)
    connect: object = None  # (cfg) -> {"ok", "uri", "browser_opened", "handle"}
    poll: object = None  # (handle) -> {"ok", "username"}
    cancel: object = None  # () -> None (chiude il listener loopback)
    unlink: object = None  # () -> None (disconnessione)


def merge_outlook_lines(existing: str, events) -> str:
    """Appende righe `HH:MM-HH:MM Titolo` non gia' presenti (match esatto).

    Puro e testabile senza DOM: i titoli vengono sanificati a riga singola,
    gli orari invalidi saltati. Dopo il fetch Outlook l'utente resta padrone
    della TextArea (mai replace, mai duplicati).
    """
    have = {ln.strip() for ln in (existing or "").splitlines() if ln.strip()}
    out = [(existing or "").rstrip()] if (existing or "").strip() else []
    for start, end, title in events or ():
        s, e = str(start or "").strip(), str(end or "").strip()
        if not _HHMM_RE.match(s) or not _HHMM_RE.match(e):
            continue
        name = " ".join(str(title or "").split())
        line = f"{s}-{e} {name}" if name else f"{s}-{e}"
        if line not in have:
            have.add(line)
            out.append(line)
    return "\n".join(out)


def parse_event_lines(text: str, day_s: str):
    """(eventi, righe_scartate): un FixedEvent per riga `HH:MM-HH:MM Titolo`.

    Puro (presentation): valida orari e ordinamento, mai scheduling. Titolo
    opzionale; righe vuote ignorate; righe invalide segnalate, non bloccanti.
    """
    events: list = []
    bad: list = []
    for raw in (text or "").splitlines():
        clean = raw.strip()
        if not clean:
            continue
        m = _EVENT_RE.match(raw)
        if not m:
            bad.append(clean)
            continue
        try:
            start = datetime.strptime(f"{day_s} {m.group(1)}", "%Y-%m-%d %H:%M")
            end = datetime.strptime(f"{day_s} {m.group(2)}", "%Y-%m-%d %H:%M")
        except ValueError:
            bad.append(clean)
            continue
        if end <= start:
            bad.append(clean)
            continue
        events.append(FixedEvent((m.group(3) or "").strip(), start, end))
    return events, bad


def day_window_parts(window: dict | None, day_s: str):
    """Conversione esplicita config `day_window` -> (start, end, [FixedEvent], [allday]).

    Gli eventi sono gia' campi separati nel config (mai stringhe da
    riparsare): qui si costruiscono i datetime del giorno e i FixedEvent.
    `allday` = titoli tutto-il-giorno (riga informativa, mai busy).
    None se finestra assente/invalida -> piano giorno solo task, nessun
    default di orari (la disponibilita' resta esplicita, Fase 4).
    """
    if not isinstance(window, dict):
        return None
    try:
        start = datetime.strptime(
            f"{day_s} {window.get('start', '')}", "%Y-%m-%d %H:%M"
        )
        end = datetime.strptime(f"{day_s} {window.get('end', '')}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    if end <= start:
        return None
    events: list[FixedEvent] = []
    raw = window.get("events")
    if isinstance(raw, list):
        for ev in raw:
            if not isinstance(ev, dict):
                continue
            try:
                es = datetime.strptime(
                    f"{day_s} {ev.get('start', '')}", "%Y-%m-%d %H:%M"
                )
                ee = datetime.strptime(f"{day_s} {ev.get('end', '')}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if ee <= es:
                continue
            events.append(FixedEvent(str(ev.get("title", "") or ""), es, ee))
    allday: list[str] = []
    raw_all = window.get("allday")
    if isinstance(raw_all, list):
        for name in raw_all:
            clean = str(name or "").strip()
            if clean:
                allday.append(clean[:120])
                if len(allday) >= 30:
                    break
    return start, end, events, allday


def build_planning_request(
    todos: list[TodoItem],
    today: str,
    hours: float,
    window: dict | None = None,
    now=None,
) -> PlanningRequest:
    """TodoItem/config app -> PlanningRequest (Phase 2, adapter app-owned).

    Unico punto dove il mondo applicativo entra nel core: normalizzazione
    task (via Request), ore -> pomodori (capacity.total, pura conversione),
    factor auto via domain (D2: l'auto-risoluzione vive QUI, mai nel path
    plan(request)), finestra -> availability/busy, contesto calibrazione.
    Puro sui dati passati (mai I/O): il commit resta al chiamante.
    `today` garbage -> giorno corrente (l'orologio appartiene al caller).
    `now` (F0, contratto v2): datetime vincolante per la clip al futuro —
    None = nessuna clip (legacy per i percorsi storici come l'execution).
    """
    try:
        day = datetime.strptime(str(today or "")[:10], "%Y-%m-%d").date()
        today_s = day.strftime("%Y-%m-%d")
    except ValueError:
        day = datetime.now().date()
        today_s = day.strftime("%Y-%m-%d")
    avail: list = []
    busy: tuple = ()
    parts = day_window_parts(window, today_s)
    if parts is not None:
        start, end, events, _allday = parts
        avail = [TimeWindow(start, end)]
        busy = events_to_busy(events)
    # as_moment (classi stdlib reali): freeze-proof contro il patch del nome
    # `datetime` nei test, accetta anche date (= mezzanotte).
    moment = as_moment(now)
    return PlanningRequest(
        day=day,
        tasks=tuple(todos or ()),
        capacity_pomo=capacity.total(hours),
        factor=domain.calibration_factor(list(todos or ())),
        availability=tuple(avail),
        busy=tuple(busy),
        now=moment,
        sample_count=domain.calibration_samples(list(todos or ())),
    )


def scheduled_for_today(
    todos: list[TodoItem],
    today: str,
    hours: float,
    window: dict | None,
    include_done: bool = False,
    now=None,
):
    """(ScheduledDayPlan, eventi, confermati) di oggi; (None, [], []) se vuoto.

    Unico punto di costruzione condiviso da Piano Giorno e Briefing: i
    PlanItem (score/stima/mandatory) arrivano dalla proposta del Planner
    filtrata sui SOLO confermati (planned_for == oggi) — nessuna seconda
    selezione — e lo slot dallo Scheduler. Senza finestra valida:
    ScheduledDayPlan degenere (tutti unscheduled, slot None) — lo
    scheduling vero richiede la finestra scritta da Buongiorno, mai
    orari inventati.

    `now` (F1): datetime vincolante — la finestra e' clippata a
    [max(start, now), end]; con end <= now degrada onestamente allo
    stesso degenere (solo task, zero timeline). None = nessuna clip
    (percorsi storici: execution lookup, briefing sera).

    include_done (briefing): include i confermati non attivi (es.
    completati) nel ritorno `planned` ma FUORI dal dayplan: lo Scheduler
    non colloca i non attivi per contratto (propose li esclude) e le loro
    righe esecutive derivano direttamente dal todo (slot None). Il
    completato-today e' individuato da completed_at (apply_state azzera
    planned_for al completamento: comportamento esistente).

    Quinto elemento `alternatives`: diagnostica Phase 6 calcolata su
    QUESTO dayplan/sched (sottoinsieme confermati), non sul piano intero —
    solo cosi' il Detail di una riga timed non contraddice la timeline
    visibile (un task puo' avere slot qui ed essere fuori nel piano
    completo per competizione con non-confermati). Senza finestra: (),
    nessuna pretesa sui blocchi (come plan_context senza window)."""
    if include_done:
        planned = [
            t
            for t in todos
            if t.planned_for == today
            or (t.state == "completato" and str(t.completed_at or "")[:10] == today)
        ]
    else:
        planned = [t for t in todos if t.planned_for == today and t.state == "attivo"]
    if not planned:
        return None, [], [], [], ()
    plan = plan_request(build_planning_request(todos, today, hours, None)).plan
    items_by_id = {it.todo_id: it for it in plan.items}
    attivi = [t for t in planned if t.state == "attivo"]
    ordered = [items_by_id[t.id] for t in attivi if t.id in items_by_id]
    ordered_ids = {it.todo_id for it in ordered}
    for t in attivi:  # ripiego per attivi senza PlanItem (id orfani)
        if t.id is not None and t.id not in ordered_ids:
            # Stessa policy del DayPlan (B4): stima calibrata, mai duplicata.
            ordered.append(
                PlanItem(t.id, 0, (), capacity.estimate(t, plan.factor), False)
            )
            ordered_ids.add(t.id)
    dayplan = DayPlan(
        plan.day,
        planned=tuple(ordered),
        capacity_pomo=plan.capacity_pomo,
        factor=plan.factor,
    )
    parts = day_window_parts(window, today)
    if parts is None:
        return ScheduledDayPlan(dayplan), [], [], planned, ()
    start, end, events, allday = parts
    moment = as_moment(now)
    if moment is not None:
        if end <= moment:
            # Finestra interamente trascorsa: stesso degenere onesto della
            # finestra assente (solo task, zero timeline, mai orari inventati).
            return ScheduledDayPlan(dayplan), [], [], planned, ()
        if start < moment:
            start = moment
    sched = Planner.schedule(
        dayplan,
        [TimeWindow(start, end)],
        busy=events_to_busy(events),
        deadlines=deadlines_for(todos),
        now=moment,
    )
    req = build_planning_request(todos, today, hours, window, now=moment)
    try:
        alts, _diags = diagnose(
            PlanningResult(request=req, plan=dayplan, scheduled=sched), events
        )
    except Exception:
        alts = ()
    return sched, events, allday, planned, alts


def _timeline_lines(
    sched: ScheduledDayPlan,
    events: list,
    shown: set,
    by_id: dict,
    bad_names: tuple = (),
    allday: tuple = (),
    alts: dict | None = None,
) -> list[str]:
    """Righe timeline: task schedulati + eventi fissi ordinati per inizio.

    Condivisa da Buongiorno e piano giorno (solo rendering, mai scheduling):
    task prima degli eventi a pari ora; eventi fuori availability esclusi;
    in coda gli unscheduled strutturali tra quelli richiesti (`shown`).
    `allday` = riga informativa tutto-il-giorno (mai busy, mai schedulata).
    `alts` (F5, {todo_id: PlanAlternative} da diagnose): la coda mostra la
    causa reale del mancato slot ("X (buco max 30m < 90m)"); senza, soli
    titoli come prima. Mai cause inventate: solo blocked_by osservati.
    """
    entries = []  # (start, order, line): task prima degli eventi a pari ora
    for s in sched.scheduled:
        if s.item.todo_id not in shown:
            continue
        t = by_id.get(s.item.todo_id)
        title = _escape_markup(t.title) if t else f"#{s.item.todo_id}"
        entries.append(
            (
                s.start,
                0,
                f"{s.start.strftime('%H:%M')}–{s.end.strftime('%H:%M')} {title}",
            )
        )
    for e in events:
        if not any(a.start < e.end and e.start < a.end for a in sched.availability):
            continue
        name = f" {_escape_markup(e.title)}" if e.title else ""
        entries.append(
            (
                e.start,
                1,
                f"{e.start.strftime('%H:%M')}–{e.end.strftime('%H:%M')} {T('planp_event_tag')}{name}",
            )
        )
    entries.sort(key=lambda en: (en[0], en[1]))
    lines = [line for _s, _o, line in entries]
    if bad_names:
        names = ", ".join(_escape_markup(b) for b in bad_names)
        lines.insert(0, T("planp_events_bad", t=names))
    if allday:
        names = ", ".join(_escape_markup(a) for a in allday)
        lines.insert(1 if bad_names else 0, T("planp_allday", t=names))
    tail = []
    pending: list[str] = []
    outside: list[str] = []
    cause_fn = None
    titles: dict = {}
    if alts is not None:
        try:
            from src.screens.views import _cause_text

            titles = {
                tid: t.title
                for tid, t in (by_id or {}).items()
                if tid is not None and t is not None
            }
            cause_fn = _cause_text
        except Exception:
            cause_fn = None
    for it in sched.unscheduled:
        if it.todo_id not in shown:
            continue
        t = by_id.get(it.todo_id)
        name = _escape_markup(t.title) if t else f"#{it.todo_id}"
        cause = None
        bucket = None
        if cause_fn is not None and alts is not None:
            try:
                alt = alts.get(it.todo_id)
                if alt is not None:
                    cause = cause_fn(alt.blocked_by, alt.detail, titles)
                    bucket = classify(alt.blocked_by)
            except Exception:
                cause = None
        label = f"{name} ({cause})" if cause else name
        if bucket == OUT_ELIGIBLE:
            pending.append(label)
        elif bucket is not None:
            outside.append(label)
        else:
            tail.append(label)
    if pending:
        lines.append(T("planp_slots_pending", t=", ".join(pending)))
    if outside:
        lines.append(T("planp_slots_outside", t=", ".join(outside)))
    if tail:
        lines.append(T("planp_slots_un", t=", ".join(tail)))
    return lines


class PlanListView(ListView):
    """Lista del piano: Enter apre il dettaglio (solo righe pianificate).

    ListView binda Enter a select_cursor (ombra i binding della screen) ed emette
    Selected anche al click: per questo Enter e' ribindato qui a un dispatch verso
    la screen, mentre il click resta invariato (sposta solo l'highlight, nessun
    handler Selected). La screen apre il Detail solo per la sezione "planned".
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
        max-height: 90%;
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
    #plan-rehint {
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
        hours: float = 6.0,
        window: dict | None = None,
        current_pomo=None,
        on_completed=None,
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
        # Getter del task corrente del timer (task_id | None): solo marker.
        self.current_pomo = current_pomo
        # Hook M2 (callback opaca, mai I/O qui: la screen non scrive su disco).
        self.on_completed = on_completed
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.hours = max(1.0, float(hours))
        except (ValueError, TypeError):
            self.hours = 6.0
        # Contesto operativo scritto da Buongiorno (orari + eventi fissi
        # strutturati). Assente/invalido = scheda solo task, senza timeline.
        self.window = window if isinstance(window, dict) else None

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
    def _row(
        t: TodoItem, marker: str, extra: str = "", prefix: str = "", duration: str = ""
    ) -> str:
        """Riga cockpit (#46): stato + ! solo se priorita' alta + slot/durata
        + titolo + scadenza + #id + pomodori. Mai analytics in riga."""
        plbl = _pomo_label(t)
        pomo = f" [red]{plbl}[/]" if plbl else ""
        prio = "[red]![/] " if t.priority == Priority.HIGH else ""
        dur = f" [green]({duration})[/]" if duration else ""
        return f"  [cyan]{marker}[/] {_status(t)} {prio}{prefix}{_escape_markup(t.title)}{extra}  [dim]#{t.id}[/]{pomo}{dur}"

    def _marker(self, tid, base: str) -> str:
        """Marker di riga: ▶ sul task corrente del Pomodoro, altrimenti base.

        Puramente presentazionale: il timer vive in app, qui solo il getter
        (task_id | None). Nessun timer -> nessun marker corrente."""
        try:
            cur = self.current_pomo() if callable(self.current_pomo) else None
        except Exception:
            cur = None
        return "▶" if cur is not None and cur == tid else base

    def _planned_children(
        self,
        sched: ScheduledDayPlan,
        events: list,
        planned: list[TodoItem],
        allday: tuple = (),
        alts: dict | None = None,
    ) -> list[ListItem]:
        """Righe operative della sezione pianificati, con timing in riga.

        Solo presentazione dei risultati gia' prodotti: Buongiorno decide
        cosa entra (planned_for), il Planner da' l'ordine di merito, lo
        Scheduler gli slot — qui nessuna seconda selezione/ordine.
        - riga informativa tutto-il-giorno (disabled, mai operativa);
        - task schedulati: PlanRow operative con prefisso orario, nell'ordine
          degli slot (first-fit = cronologico = merito);
        - eventi fissi: righe disabled informative, intercalati per orario
          (non sono task, non alterano l'ordine dei task);
        - task senza slot: operativi in coda in due sezioni (non inseriti
          per gara persa vs non entrano oggi per gap insufficiente, da
          `alts` di diagnose — mai dedotto qui); senza alt, terza coda
          onesta "senza orario".
        """
        scheduled_ids = {s.item.todo_id for s in sched.scheduled}
        by_id = {t.id: t for t in self.all_todos if t.id is not None}
        entries = []  # (start, task-prima-dell'evento, payload, prefix, minutes)
        for s in sched.scheduled:
            todo = by_id.get(s.item.todo_id)
            if todo is None:
                continue
            prefix = f"{s.start.strftime('%H:%M')}–{s.end.strftime('%H:%M')} "
            try:
                minutes = int((s.end - s.start).total_seconds() // 60)
            except Exception:
                minutes = 0
            entries.append((s.start, 0, todo, prefix, minutes))
        for e in events:
            if not any(a.start < e.end and e.start < a.end for a in sched.availability):
                continue
            entries.append((e.start, 1, e, "", 0))
        entries.sort(key=lambda en: (en[0], en[1]))
        rows: list[ListItem] = []
        if allday:
            names = ", ".join(_escape_markup(a) for a in allday)
            rows.append(
                ListItem(Label(f"  {T('planp_allday', t=names)}"), disabled=True)
            )
        for _st, _o, payload, prefix, minutes in entries:
            if isinstance(payload, FixedEvent):
                name = f" {_escape_markup(payload.title)}" if payload.title else ""
                label = (
                    f"{payload.start.strftime('%H:%M')}–{payload.end.strftime('%H:%M')}"
                    f" {T('planp_event_tag')}{name}"
                )
                rows.append(ListItem(Label(f"  {label}"), disabled=True))
            else:
                due = _due_date_part(payload.due)
                extra = T("plan_overdue_row", due=payload.due) if due else ""
                duration = f"{minutes}m" if minutes > 0 else ""
                rows.append(
                    PlanRow(
                        Label(
                            self._row(
                                payload,
                                self._marker(payload.id, "x"),
                                extra,
                                prefix,
                                duration,
                            )
                        ),
                        task_id=payload.id,
                        section="planned",
                    )
                )

        # Linee di divisione tra la parte con timing (slot + eventi) e le
        # code senza slot, una per outcome (non inseriti vs non entrano
        # oggi + ripiego onesto senza alt): solo con contenuto sopra, mai
        # linee orfane. Disabled come gli eventi: non operative.
        def _divider(key: str) -> ListItem:
            return ListItem(
                Label(f"  [dim]──── {T(key)} ────[/]"),
                disabled=True,
            )

        try:
            from src.screens.views import _cause_text as _plan_cause
        except Exception:
            _plan_cause = None
        titles = {t.id: t.title for t in self.all_todos if t.id is not None}
        pending_rows: list[ListItem] = []
        outside_rows: list[ListItem] = []
        unknown_rows: list[ListItem] = []
        tail_ids = [it.todo_id for it in sched.unscheduled]
        for tid in tail_ids:
            todo = by_id.get(tid)
            if todo is None:
                continue
            due = _due_date_part(todo.due)
            extra = T("plan_overdue_row", due=todo.due) if due else ""
            cause = None
            bucket = None
            if _plan_cause is not None and alts is not None:
                try:
                    alt = alts.get(tid)
                    if alt is not None:
                        cause = _plan_cause(alt.blocked_by, alt.detail, titles)
                        bucket = classify(alt.blocked_by)
                except Exception:
                    cause = None
            label = self._row(todo, self._marker(todo.id, "x"), extra)
            if cause:
                label = f"{label} ({cause})"
            row = PlanRow(
                Label(label),
                task_id=todo.id,
                section="planned",
            )
            if bucket == OUT_ELIGIBLE:
                pending_rows.append(row)
            elif bucket is not None:
                outside_rows.append(row)
            else:
                unknown_rows.append(row)
        # Difensivo: confermati mai coperti (es. id None) restano visibili.
        for t in planned:
            if t.id not in scheduled_ids and t.id not in tail_ids:
                due = _due_date_part(t.due)
                extra = T("plan_overdue_row", due=t.due) if due else ""
                unknown_rows.append(
                    PlanRow(
                        Label(self._row(t, self._marker(t.id, "x"), extra)),
                        task_id=t.id,
                        section="planned",
                    )
                )
        if rows and pending_rows:
            rows.append(_divider("plan_sec_pending"))
        rows.extend(pending_rows)
        if rows and outside_rows:
            rows.append(_divider("plan_sec_outside"))
        rows.extend(outside_rows)
        if rows and unknown_rows:
            rows.append(_divider("plan_sec_noslot"))
        rows.extend(unknown_rows)
        return rows

    def compose(self) -> ComposeResult:
        today_display = _format_date_it(self.today)
        with Vertical(id="plan-box"):
            yield Label(
                f"[b]{T('plan_title', date=today_display)}[/b]", id="plan-title"
            )
            # Contesto esecutivo di oggi: UNICA costruzione condivisa col
            # Briefing (confermati -> merito Planner -> slot Scheduler).
            # F1: clip a now — la scheda operativa non mostra slot passati.
            plan_now = datetime.now()
            sched, events, allday, planned, dalts = scheduled_for_today(
                self.all_todos, self.today, self.hours, self.window, now=plan_now
            )
            # Verita' slot della timeline visibile (per il Detail: etichetta
            # noslot e Blocco coerenti con le righe, mai col piano intero).
            self._diag_alts = {a.todo_id: a for a in dalts}
            due = self._due_today()
            overdue = self._overdue()
            upcoming = self._upcoming()
            unplanned = self._unplanned()
            load = ""
            if planned:
                load_f = sum(t.pomodoros for t in planned)
                load_s = sum(getattr(t, "stima_pomo", 0) or 0 for t in planned)
                load = T("plan_load", f=load_f, s=load_s) if load_s else ""
            # Finestra operativa di Buongiorno: solo con pianificati (mai
            # default di orari); le righe planned diventano timed operative.
            # F5: minuti liberi futuri (tempo) accanto alla finestra; il
            # carico in pomodori (capacita') resta in `load` — mai confusi.
            win_lbl = ""
            if sched is not None and sched.availability:
                win_lbl = T(
                    "plan_sec_window",
                    window=(
                        f"{sched.availability[0].start:%H:%M}"
                        f"–{sched.availability[0].end:%H:%M}"
                    ),
                )
                try:
                    from src.planner.time_model import residual

                    free_min = residual(sched.availability, sched.busy, plan_now)
                    win_lbl += f" · {T('plan_time_left', m=free_min)}"
                except Exception:
                    pass
            sections = [
                (
                    T("plan_sec_planned", win=win_lbl, load=load),
                    "planned",
                    planned,
                    "x",
                ),
                (T("plan_sec_due"), "due", due, "+"),
                (T("plan_sec_overdue"), "overdue", overdue, "+"),
                (T("plan_sec_upcoming"), "upcoming", upcoming, "+"),
                (T("plan_sec_unplanned"), "unplanned", unplanned, "+"),
            ]
            custom = (
                {
                    "planned": self._planned_children(
                        sched,
                        events,
                        planned,
                        tuple(allday),
                        alts=dict(self._diag_alts),
                    )
                }
                if sched is not None and sched.availability
                else {}
            )
            items = [t for _h, _k, todos, _m in sections for t in todos]
            if items:
                keep = getattr(self, "_keep_id", None)
                keep_section = getattr(self, "_keep_section", None)
                children = []
                found_keep: int | None = None
                first_in_section: int | None = None
                for header, kind, todos, marker in sections:
                    rows_kind = custom.get(kind)
                    if rows_kind is None:
                        if not todos:
                            continue
                        children.append(ListItem(Label(header), disabled=True))
                        for t in todos:
                            extra = (
                                T("plan_overdue_row", due=t.due)
                                if kind in ("planned", "due", "overdue", "upcoming")
                                and _due_date_part(t.due)
                                else ""
                            )
                            row = PlanRow(
                                Label(self._row(t, self._marker(t.id, marker), extra)),
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
                    else:
                        if not rows_kind:
                            continue
                        children.append(ListItem(Label(header), disabled=True))
                        for child in rows_kind:
                            tid = getattr(child, "task_id", None)
                            if found_keep is None and tid is not None and tid == keep:
                                found_keep = len(children)
                            if (
                                first_in_section is None
                                and keep_section is not None
                                and kind == keep_section
                            ):
                                first_in_section = len(children)
                            children.append(child)
                if found_keep is None:
                    found_keep = first_in_section
                initial = (
                    found_keep
                    if found_keep is not None
                    else next((i for i, c in enumerate(children) if not c.disabled), 0)
                )
                yield PlanListView(*children, id="plan-section", initial_index=initial)
            else:
                yield Static(T("plan_empty"))
            yield Static(T("plan_legend"), id="plan-legend")
            if sched is not None and sched.availability:
                yield Static(T("plan_replan_hint"), id="plan-rehint")
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
        """Enter: dettaglio solo se effettivamente pianificato oggi.

        Le sezioni due/overdue/upcoming/unplanned non sono in piano: aprirne
        il Detail mostrerebbe un contesto Why ricalcolato ("Pianificato
        oggi") incoerente con lo stato reale. Il gate riusa la sezione della
        riga + lo stesso predicato di _planned_todos (lettura di stato, mai
        logica di planning): niente scoring/scheduler duplicati.
        """
        tid, section = self._current()
        if tid is None or section != "planned":
            self.notify(T("n_plan_noop"), severity="warning")
            return
        todo = self._todo_by_id(tid)
        if todo is None or todo.planned_for != self.today or todo.state != "attivo":
            self.notify(T("n_plan_noop"), severity="warning")
            return
        # Import locale: evita dipendenze tra aree screen all'import.
        from src.screens.views import DetailScreen, plan_context

        _decisions, _plan_alts = plan_context(
            self.all_todos, self.today, self.hours, self.window, now=datetime.now()
        )
        # Le alternative della TIMELINE visibile vincono su quelle del piano
        # intero: un task con slot qui non deve mai dirsi senza orario.
        # (None = mai calcolate -> fallback; {} vuoto = nessun blocco.)
        _dalts = getattr(self, "_diag_alts", None)
        _alternatives = dict(_dalts) if _dalts is not None else _plan_alts
        self.app.push_screen(
            DetailScreen(
                todo,
                self.all_todos,
                today=self.today,
                hours=self.hours,
                decisions=_decisions,
                alternatives=_alternatives,
            ),
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
            if not self._ask_actual(tid, section):
                self._emit_completed(todo)

    def _emit_completed(self, todo) -> None:
        """M2: notifica il completamento al recorder (callback opaca).

        Mai I/O in screen: on_completed e' wirato dall'app. Mai solleva."""
        if todo is None or self.on_completed is None:
            return
        try:
            self.on_completed(todo)
        except Exception:
            pass

    def _ask_actual(self, tid, section: str | None) -> bool:
        """Chiede i pomodori reali dopo un completamento stimato.

        Ritorna True se la popup e' mostrata (l'execution si registra alla
        risposta), False se skippata (il chiamante registra subito)."""
        todo = self._todo_by_id(tid)
        if todo is None:
            return False
        try:
            stima = int(todo.stima_pomo or 0)
            actual = int(todo.actual_pomo or 0)
            counted = int(todo.pomodoros or 0)
        except (ValueError, TypeError):
            return False
        if stima <= 0 or actual > 0:
            return False
        from src.screens.form import ActualScreen

        def on_actual(result: int | None) -> None:
            if result is None:
                self._emit_completed(self._todo_by_id(tid))
                return
            target = self._todo_by_id(tid)
            if target is None:
                return
            domain.record_actual(target, result)
            self._refresh_keep(tid, section)
            d = result - stima
            sign = f"+{d}" if d > 0 else str(d)
            self.notify(T("n_actual_saved", a=result, s=stima, d=sign))
            self._emit_completed(target)

        self.app.push_screen(ActualScreen(todo.title, stima, counted), on_actual)
        return True

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
        extra = T("plan_overdue_row", due=due) if due else ""
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
        # Il focus sulla lista trascina lo scroll verso il fondo (come
        # Buongiorno prima del fix): si riapre in cima, differito perche'
        # il layout finisce dopo l'idle.
        self.call_after_refresh(self._scroll_top)

    def _scroll_top(self) -> None:
        try:
            self.query_one("#rev-scroll").scroll_home(animate=False)
        except Exception:
            pass

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


class ReplanPreviewScreen(CloseMixin, ModalScreen[None]):
    """Preview read-only del replan (#50, motore M4): s conferma, Esc niente."""

    CSS = """
    #rp-box {
        width: 100;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
    }
    #rp-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #rp-legend {
        height: auto;
    }
    #rp-buttons {
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
        on_apply,
        today: str | None = None,
        hours: float = 6.0,
        window: dict | None = None,
        now=None,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        # Commit fuori dalla screen (come on_change): qui solo preview.
        self.on_apply = on_apply
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.hours = max(1.0, float(hours))
        except (ValueError, TypeError):
            self.hours = 6.0
        self.window = window if isinstance(window, dict) else None
        self.now = as_moment(now) or datetime.now()

    def _proposal(self):
        """Proposta M4 su finestra odierna (lettura, mai scritture)."""
        parts = day_window_parts(self.window, self.today)
        avail: list = []
        busy: list = []
        if parts is not None:
            start, end, events, _allday = parts
            avail = [TimeWindow(start, end)]
            busy = events_to_busy(events)
        sched, _ev, _al, _pl, _alts = scheduled_for_today(
            self.all_todos, self.today, self.hours, self.window, now=self.now
        )
        return replan(
            self.all_todos,
            self.today,
            self.hours,
            avail,
            busy,
            self.now,
            current=sched,
        )

    def _section_lines(self, proposal) -> list[str]:
        by_id = {t.id: t for t in self.all_todos if t.id is not None}
        lines = []
        for kind in (KEPT, MOVED, DROPPED, ADDED):
            rows = [m for m in proposal.moves if m.kind == kind]
            if not rows:
                continue
            ref = phrase_for(kind, "replan")
            lines.append(f"[b]{T(ref.key, **ref.params)}[/b]")
            for m in rows:
                todo = by_id.get(m.todo_id)
                title = (
                    _escape_markup(todo.title) if todo is not None else f"#{m.todo_id}"
                )
                if (
                    kind == MOVED
                    and m.old_start is not None
                    and m.new_start is not None
                    and (m.old_start, m.old_end) != (m.new_start, m.new_end)
                ):
                    lines.append(
                        f"  {m.old_start}–{m.old_end or '?'} → "
                        f"{m.new_start}–{m.new_end or '?'} {title}"
                    )
                elif m.new_start is not None and kind != DROPPED:
                    lines.append(
                        T(
                            "cli_replan_row_slot",
                            s=m.new_start,
                            e=m.new_end or "?",
                            t=title,
                        )
                    )
                elif kind == MOVED and m.new_start is None and m.old_start is not None:
                    # B2: spostato senza nuovo slot (es. finestra esaurita) —
                    # mai reso come cambio di orario, mai solo il motivo.
                    if m.primary is not None:
                        key_p, params = m.primary
                        lines.append(
                            T(
                                "cli_replan_row_noslot_m",
                                t=title,
                                m=T(key_p, **params),
                            )
                        )
                    else:
                        lines.append(T("cli_replan_row_noslot", t=title))
                elif m.primary is not None:
                    key_p, params = m.primary
                    lines.append(T("cli_replan_row", t=title, m=T(key_p, **params)))
                else:
                    lines.append(f"  {title}")
        return lines

    def compose(self) -> ComposeResult:
        with Vertical(id="rp-box"):
            yield Label(
                T(
                    "rp_title",
                    date=_format_date_it(self.today),
                    now=self.now.strftime("%H:%M"),
                ),
                id="rp-title",
            )
            with VerticalScroll(id="rp-scroll"):
                proposal = self._proposal()
                lines = self._section_lines(proposal)
                if lines:
                    yield Static("\n".join(lines), id="rp-list")
                else:
                    yield Static(T("cli_replan_no_changes"), id="rp-list")
                yield Static(
                    T("cli_replan_residual", r=f"{proposal.residual_pomo:g}"),
                    id="rp-residual",
                )
            yield Static(T("rp_legend"), id="rp-legend")
            with Horizontal(id="rp-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="rp-confirm", variant="default")
                yield Button(T("form_cancel"), id="rp-close", variant="default")

    def on_mount(self) -> None:
        self.call_after_refresh(self._scroll_top)

    def _scroll_top(self) -> None:
        try:
            self.query_one("#rp-scroll").scroll_home(animate=False)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rp-close":
            self.dismiss()
        elif event.button.id == "rp-confirm":
            self._confirm()

    def action_confirm(self) -> None:
        self._confirm()

    def _confirm(self) -> None:
        proposal = self._proposal()
        added, dropped = domain.apply_replan(self.all_todos, proposal, self.today)
        self.on_apply(added, dropped)
        self.notify(T("cli_replan_applied", a=added, d=dropped))
        self.dismiss()


class PlanProposalScreen(CloseMixin, ModalScreen[None]):
    """Buongiorno: contesto di oggi + proposta da confermare (scrive planned_for)."""

    CSS = """
    #planp-box {
        width: 100;
        max-width: 95%;
        height: 90%;
        max-height: 90%;
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
    }
    #planp-start {
        height: auto;
        margin-bottom: 1;
    }
    #planp-slots {
        height: auto;
        margin-bottom: 1;
    }
    #planp-events {
        height: 5;
        margin-bottom: 1;
    }
    #planp-outlook {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    #planp-avail-row {
        height: 3;
        margin-bottom: 1;
    }
    #planp-avail-row Input {
        width: 14;
        height: 3;
    }
    #planp-avail-dash {
        width: auto;
        height: 3;
        padding: 1 1 0 1;
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
        # Niente binding `o` qui: o = pomodoro (home/piano giorno), qui solo bottone.
    ]

    def __init__(
        self,
        all_todos: list[TodoItem],
        on_change,
        today: str | None = None,
        hours: float = 6.0,
        on_window=None,
        outlook_hooks: OutlookHooks | None = None,
        prev_start: str | None = None,
        prev_end: str | None = None,
        prev_date: str | None = None,
        now=None,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.on_change = on_change
        # Ora del Buongiorno (F1): congelata all'apertura — il motore clippa
        # la finestra a [max(start, now), end], mai slot nel passato.
        self.now = as_moment(now) or datetime.now()
        # Contesto operativo (orari + eventi fissi): alla conferma va al piano
        # giorno via callback (le screen non salvano mai su disco).
        self.on_window = on_window
        # Seam Outlook (None = bottone inerte con hint, i test senza app
        # restano verificabili).
        self.outlook_hooks = outlook_hooks
        self.allday: list[str] = []
        self._outlook_busy = False
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.hours = max(1.0, float(hours))
        except (ValueError, TypeError):
            self.hours = 6.0
        self.plan = plan_request(
            build_planning_request(self.all_todos, self.today, self.hours, None)
        ).plan
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
        # Disponibilità: input utente esplicito (start/end), mai default.
        # day_hours resta la capacita' quantitativa, non working hours.
        # Eventi fissi: temporanei come gli orari, mai persistiti.
        # Prefill: solo gli orari dell'ultima finestra valida precedente
        # (mai eventi/allday di ieri); niente prefill = tutto come prima.
        self.prefill_date = (
            prev_date if (prev_start and prev_end and prev_date) else None
        )
        self.start_text = prev_start or ""
        self.end_text = prev_end or ""
        self.events_text = ""
        self.events: list = []
        self.events_bad: list = []
        self.sched: ScheduledDayPlan | None = None
        self._preview_plan: DayPlan | None = None
        self.slot_error: str | None = None
        self.window_start = None
        self.window_end = None
        self._refresh_sched()

    def _parse_time(self, value: str):
        """(ok, datetime|None): vuoto = (True, None), invalido = (False, None)."""
        clean = (value or "").strip()
        if not clean:
            return True, None
        try:
            return True, datetime.strptime(f"{self.today} {clean}", "%Y-%m-%d %H:%M")
        except ValueError:
            return False, None

    def _refresh_sched(self) -> None:
        """Ricalcola lo ScheduledDayPlan dall'input (solo rendering)."""
        self.slot_error = None
        self.sched = None
        self._preview_plan = None
        self.window_start = None
        self.window_end = None
        self.past_note: tuple | None = None
        ok_start, start = self._parse_time(self.start_text)
        ok_end, end = self._parse_time(self.end_text)
        if start is None and ok_start:
            return  # senza orari: nessuna finestra, hint base
        if not ok_start:
            self.slot_error = "planp_start_bad"
            return
        if not ok_end or end is None:
            self.slot_error = "planp_end_missing"
            return
        # end <= start (overnight compreso) non e' una finestra valida qui.
        if end <= start:
            self.slot_error = "planp_window_bad"
            return
        self.events, self.events_bad = parse_event_lines(self.events_text, self.today)
        self.window_start, self.window_end = start, end
        # Clip a now (F1): il passato non si schedula. La finestra originale
        # resta per il payload (l'utente ha scritto quelli); lo scheduling
        # usa il futuro e la preview mostra la fascia esclusa.
        eff_start = start
        if self.now is not None and start < self.now < end:
            eff_start = self.now
            self.past_note = (start, self.now)
        elif self.now is not None and end <= self.now:
            self.past_note = (start, end)
            return  # interamente trascorsa: solo task, zero timeline
        # La preview segue le X: solo i selezionati si schedulano (riallineati
        # sui buchi liberati); deselezionare tutto = nessuno slot, onesto.
        shown = self._shown_ids()
        items = [it for it in self.plan.items if it.todo_id in shown]
        sub = DayPlan(
            day=self.plan.day,
            planned=tuple(items),
            capacity_pomo=self.plan.capacity_pomo,
            factor=self.plan.factor,
        )
        self._preview_plan = sub
        self.sched = Planner.schedule(
            sub,
            [TimeWindow(eff_start, end)],
            busy=events_to_busy(self.events),
            deadlines=deadlines_for(self.all_todos),
            now=self.now,
        )

    def _window_payload(self) -> dict | None:
        """Payload strutturato per il config; None = nessuna finestra valida.

        Eventi gia' campi separati (niente stringhe da riparsare): la
        conversione config -> FixedEvent nel piano giorno e' esplicita
        (day_window_parts)."""
        if self.window_start is None or self.window_end is None:
            return None
        return {
            "date": self.today,
            "start": self.window_start.strftime("%H:%M"),
            "end": self.window_end.strftime("%H:%M"),
            "events": [
                {
                    "start": e.start.strftime("%H:%M"),
                    "end": e.end.strftime("%H:%M"),
                    "title": e.title,
                }
                for e in self.events
            ],
            "allday": list(self.allday),
        }

    def _slot_lines(self) -> str:
        """Timeline unita FixedEvent + ScheduledItem; solo rendering.

        Fonde gli eventi originali con gli slot (ordinamento display, mai
        scheduling); gli eventi fuori availability non si mostrano.
        Con clip a now (F1) la fascia esclusa e' mostrata per prima, mai
        slot fantasma nel passato. La coda senza orario (F5) mostra la causa
        reale da diagnose (blocked_by osservato sul sotto-piano visibile),
        mai cause inventate.
        """
        if self.slot_error is not None:
            return T(self.slot_error)
        lines: list[str] = []
        past = getattr(self, "past_note", None)
        if past is not None:
            s, e = past
            lines.append(
                T(
                    "planp_past",
                    s=s.strftime("%H:%M"),
                    e=e.strftime("%H:%M"),
                    n=self.now.strftime("%H:%M"),
                )
            )
        if self.sched is None:
            lines.append(T("planp_slots_none"))
            return "\n".join(lines)
        shown = self._shown_ids()
        rendered = _timeline_lines(
            self.sched,
            self.events,
            shown,
            self.by_id,
            tuple(self.events_bad),
            tuple(self.allday),
            self._preview_alts(),
        )
        lines.extend(rendered)
        return "\n".join(lines) if lines else T("planp_slots_none")

    def _preview_alts(self) -> dict:
        """{todo_id: PlanAlternative} della preview (F5, solo rendering).

        diagnose() sul sotto-DayPlan dei selezionati con lo sched visibile:
        stesse alternative che il Detail mostrerebbe per la timeline. Mai
        eccezioni verso il rendering (vuoto = sole titoli in coda).
        """
        try:
            preview = self._preview_plan
            if preview is None or self.sched is None:
                return {}
            req = build_planning_request(
                self.all_todos, self.today, self.hours, None, now=self.now
            )
            alts, _diags = diagnose(
                PlanningResult(request=req, plan=preview, scheduled=self.sched),
                self.events,
            )
            return {a.todo_id: a for a in alts}
        except Exception:
            return {}

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id not in ("planp-start", "planp-end"):
            return
        if event.input.id == "planp-start":
            self.start_text = event.value
        else:
            self.end_text = event.value
        self._update_slots()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        try:
            changed = event.text_area.id == "planp-events"
        except AttributeError:
            changed = False
        if not changed:
            return
        try:
            self.events_text = self.query_one("#planp-events", TextArea).text
        except Exception:
            return
        self._update_slots()

    def _shown_ids(self) -> set:
        """Id selezionati (preview segue le X); pre-mount = preselezionati."""
        try:
            return set(self.query_one("#planp-list", SelectionList).selected)
        except Exception:
            pass
        try:
            return {it.todo_id for it in self.rows if self._preselected(it.reasons)}
        except Exception:
            return set()

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        try:
            if event.selection_list.id != "planp-list":
                return
        except AttributeError:
            return
        self._update_slots()

    def _update_slots(self) -> None:
        self._refresh_sched()
        try:
            self.query_one("#planp-slots", Static).update(self._slot_lines())
        except Exception:
            pass

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
        extra = T("plan_overdue_row", due=due) if due else ""
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
                n_cut = sum(1 for it in self.rows if self._is_cut(it.reasons))
                n_skip = sum(1 for it in self.rows if self._is_skipped(it.reasons))
                yield Static(
                    T(
                        "planp_summary",
                        n=n_in,
                        m=self.n_planned,
                        t=n_cut,
                        r=n_skip,
                        h=int(self.hours),
                    ),
                    id="planp-summary",
                )
                # La proposta PRIMA degli input: e' il cuore della screen e a
                # 120x40 deve stare sopra il fold (disponibilita'/eventi/slot
                # seguono sotto; causa -> effetto resta leggibile scorrendo).
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
                yield Label(T("planp_avail"), id="planp-avail-label")
                if self.prefill_date:
                    yield Static(
                        T("planp_prefill", date=self.prefill_date),
                        id="planp-prefill",
                    )
                    if getattr(self, "past_note", None) is not None:
                        yield Static(
                            T(
                                "planp_prefill_past",
                                n=self.now.strftime("%H:%M"),
                            ),
                            id="planp-prefill-past",
                        )
                with Horizontal(id="planp-avail-row"):
                    yield Input(
                        value=self.start_text,
                        placeholder=T("planp_start_ph"),
                        id="planp-start",
                    )
                    yield Label("–", id="planp-avail-dash")
                    yield Input(
                        value=self.end_text,
                        placeholder=T("planp_end_ph"),
                        id="planp-end",
                    )
                yield Label(T("planp_events"), id="planp-events-label")
                yield TextArea(id="planp-events")
                yield Button(
                    T("planp_outlook_load"), id="planp-outlook", variant="default"
                )
                yield Static(self._slot_lines(), id="planp-slots")
            yield Static(T("planp_legend"), id="planp-legend")
            with Horizontal(id="planp-buttons", classes="btn-row"):
                yield Button(T("form_save"), id="planp-confirm", variant="default")
                yield Button(T("planp_goto_day"), id="planp-day", variant="default")
                yield Button(T("form_cancel"), id="planp-close", variant="default")

    def on_mount(self) -> None:
        # Focus sulla lista (s = salva ovunque: nei campi di testo i caratteri
        # sono consumati dall'input) ma scroll in cima: si vedono contesto,
        # proposta, disponibilita' ed eventi; quando si spunta, lo scroll segue
        # il cursore della lista. scroll_home differito: il layout finisce
        # dopo l'idle e il primo render riporterebbe lo scroll a meta'.
        try:
            self.query_one("#planp-list", SelectionList).focus()
        except Exception:
            try:
                self.query_one("#planp-confirm", Button).focus()
            except Exception:
                self.focus()
        self.call_after_refresh(self._scroll_top)

    def _scroll_top(self) -> None:
        try:
            self.query_one("#planp-scroll").scroll_home(animate=False)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "planp-close":
            self.dismiss()
        elif event.button.id == "planp-confirm":
            self._confirm()
        elif event.button.id == "planp-day":
            # Conferma e apri il piano giorno (l'app apre DailyPlan su "dayplan").
            self._confirm("dayplan")
        elif event.button.id == "planp-outlook":
            self._trigger_outlook_load()

    def action_confirm(self) -> None:
        self._confirm()

    def _trigger_outlook_load(self) -> None:
        """Bottone Outlook (solo bottone, mai tasto): fetch in thread."""
        try:
            asyncio.create_task(self.action_load_outlook())
        except RuntimeError:
            pass

    async def action_load_outlook(self) -> None:
        """Carica da Outlook: fetch (se configurato) o setup annullabile.

        Configurato -> compila la TextArea e basta; non configurato/token
        morto -> apre OutlookSetupScreen (Annulla = niente). Esc durante
        il fetch non scrive nulla (il merge avviene solo a fetch riuscito).
        """
        hooks = self.outlook_hooks
        fetch = getattr(hooks, "fetch", None) if hooks is not None else None
        if not callable(fetch):
            self.notify(T("outlook_err_generic", e="—"), severity="warning")
            return
        self._outlook_busy = True
        self._refresh_outlook_button()
        try:
            res = await asyncio.to_thread(fetch)
        except Exception as exc:
            res = {"ok": False, "code": "generic", "detail": str(exc)[:120]}
        self._outlook_busy = False
        if not self.is_mounted:
            return
        self._refresh_outlook_button()
        if not isinstance(res, dict) or not res.get("ok"):
            code = res.get("code", "generic") if isinstance(res, dict) else "generic"
            detail = res.get("detail", "") if isinstance(res, dict) else ""
            if code == "setup_needed":
                self._open_outlook_setup()
                return
            self.notify(outlook_error_text(code, detail), severity="error")
            return
        merge = getattr(hooks, "merge", None) if hooks is not None else None
        adopted = str(res.get("adopted") or "")
        if adopted and callable(merge):
            try:
                merge({"account": adopted})
            except Exception:
                pass
        events = res.get("events") or []
        new_text = merge_outlook_lines(self.events_text, events)
        for name in res.get("allday") or ():
            clean = " ".join(str(name or "").split())
            if clean and clean not in self.allday:
                self.allday.append(clean[:120])
        self.allday = self.allday[:30]
        if new_text != self.events_text:
            self.events_text = new_text
            try:
                self.query_one("#planp-events", TextArea).text = new_text
            except Exception:
                pass
        self._update_slots()
        n = len(events)
        names = list(res.get("allday") or [])
        s = len(res.get("skipped") or [])
        if not events and not names:
            self.notify(T("n_outlook_none"))
        else:
            self.notify(T("n_outlook_loaded", n=n, a=len(names), s=s))

    def _refresh_outlook_button(self) -> None:
        try:
            self.query_one("#planp-outlook", Button).disabled = self._outlook_busy
        except Exception:
            pass

    def _open_outlook_setup(self) -> None:
        """Setup annullabile quando manca la configurazione (o il token)."""
        hooks = self.outlook_hooks
        state = getattr(hooks, "state", None) if hooks is not None else None
        if not callable(state):
            self.notify(T("outlook_err_generic", e="—"), severity="warning")
            return
        try:
            current = state()
        except Exception:
            current = {"config": None, "has_token": False}
        if not isinstance(current, dict):
            current = {"config": None, "has_token": False}
        # Import locale: evita dipendenze tra aree screen all'import.
        from src.screens.system import OutlookSetupScreen

        self.app.push_screen(
            OutlookSetupScreen(
                current.get("config"), bool(current.get("has_token")), hooks
            ),
            self._on_setup_result,
        )

    def _on_setup_result(self, result) -> None:
        """Esito setup: Annulla/Esc (None) = niente; altrimenti salva+ricarica."""
        if not isinstance(result, dict):
            return
        hooks = self.outlook_hooks
        if result.get("disconnect"):
            unlink = getattr(hooks, "unlink", None) if hooks is not None else None
            if callable(unlink):
                try:
                    unlink()
                except Exception:
                    pass
            self.notify(T("n_outlook_off"))
            return
        cfg = result.get("config")
        if not isinstance(cfg, dict):
            return
        save = getattr(hooks, "save", None) if hooks is not None else None
        if callable(save):
            try:
                save(cfg)
            except Exception:
                pass
        self.notify(T("n_outlook_saved", a=cfg.get("account", "")))
        # Collegato ora -> carica subito (fetch diretto, senza ripassare dal setup).
        self._trigger_outlook_load()

    def _selected_ids(self) -> set:
        try:
            return set(self.query_one("#planp-list", SelectionList).selected)
        except Exception:
            return set()

    def _confirm(self, result: str | None = None) -> None:
        # Solo additivo: aggiunge i selezionati, non toglie mai i pianificati.
        selected = self._selected_ids()
        n, r = domain.proposal_plan(self.all_todos, selected, self.today)
        # La finestra (se valida) diventa contesto operativo del piano giorno;
        # None/invalida = senza orari (cancella lo stale di un giorno prima).
        # Esc non arriva qui: senza conferma nessuna scrittura.
        if self.on_window is not None:
            self.on_window(self._window_payload())
        self.on_change()
        self.notify(T("n_planp_saved", n=n, k=self.n_planned, r=r))
        self.dismiss(result)


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
        hours: float = 6.0,
        window: dict | None = None,
    ) -> None:
        super().__init__()
        self.all_todos = all_todos
        self.today = today or datetime.now().strftime("%Y-%m-%d")
        try:
            self.daily_goal = max(0, int(daily_goal or 0))
        except (ValueError, TypeError):
            self.daily_goal = 0
        self.on_print = on_print
        try:
            self.hours = max(1.0, float(hours))
        except (ValueError, TypeError):
            self.hours = 6.0
        # Finestra operativa scritta da Buongiorno (se ancora di oggi).
        self.window = window if isinstance(window, dict) else None

    def _done_on(self, day: str) -> list[TodoItem]:
        return _done_on_day(self.all_todos, day)

    def _pomo_on(self, day: str) -> int:
        return _pomo_on_day(self.all_todos, day)

    def _exec_lines(self) -> list[str]:
        """Sezione "pianificato vs eseguito": primo consumer reale di
        planner.feedback() sui confermati di oggi. Solo lettura — i dati
        (sessioni/actual/stato) sono gia' sui task, lo slot dallo
        Scheduler via scheduled_for_today (condivisa col piano giorno).
        Senza finestra: righe senza slot (slot None nel feedback)."""
        sched, _events, _allday, planned, _alts = scheduled_for_today(
            self.all_todos, self.today, self.hours, self.window, include_done=True
        )
        if sched is None:
            return []
        state_labels = {
            "attivo": T("state_attivo"),
            "in_sospeso": T("state_sospeso"),
            "completato": T("state_completato"),
        }
        todos_by_id = {t.id: t for t in self.all_todos if t.id is not None}
        lines = [T("brief_e_sec_exec")]
        # Attivi: feedback dello Scheduler (slot + esecuzione), ordine di merito.
        lines.extend(
            "  "
            + T(
                "brief_exec_row",
                slot=(
                    f"{fb.scheduled_start:%H:%M}–{fb.scheduled_end:%H:%M} "
                    if fb.scheduled_start and fb.scheduled_end
                    else ""
                ),
                t=_escape_markup(todos_by_id[fb.todo_id].title)
                if fb.todo_id in todos_by_id
                else f"#{fb.todo_id}",
                est=fb.estimate_pomo,
                done=fb.sessions,
                act=fb.actual_pomo,
                state=state_labels.get(todos_by_id[fb.todo_id].state, "")
                if fb.todo_id in todos_by_id
                else "",
            )
            for fb in planner_feedback(sched, self.all_todos)
        )
        # Non attivi (es. completati): fuori dallo Scheduler per contratto,
        # righe derivate direttamente dal todo (slot None; stima raw, il
        # fallback or-1 e' solo di pianificazione).
        for t in planned:
            if t.state == "attivo":
                continue
            lines.append(
                "  "
                + T(
                    "brief_exec_row",
                    slot="",
                    t=_escape_markup(t.title),
                    est=int(t.stima_pomo or 0),
                    done=int(t.pomodoros or 0),
                    act=int(t.actual_pomo or 0),
                    state=state_labels.get(t.state, ""),
                )
            )
        return lines

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
        lines.extend(self._exec_lines())
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
            with Horizontal(id="brief-buttons", classes="btn-row"):
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
