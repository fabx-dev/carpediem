"""Outcome nelle viste: G righe con causa, CLI speculare, cross-view uguale."""

from datetime import datetime

from src.lang import T as _T
from src.planner.models import TimeWindow
from src.planner.outcomes import OUT_ELIGIBLE, OUT_OUTSIDE, classify
from src.planner.replan import replan
from src.screens.plan import (
    PlanProposalScreen,
    ReplanPreviewScreen,
    scheduled_for_today,
)
from tests.conftest import make_todo

TODAY = "2026-10-08"


def at(h, m=0):
    return datetime(2026, 10, 8, h, m)


def window(start="09:00", end="09:30"):
    return {"date": TODAY, "start": start, "end": end, "events": []}


def test_g_added_fuori_disponibilita_con_causa():
    todos = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=1),
        make_todo("Big", todo_id=2, stima_pomo=3),
    ]
    screen = ReplanPreviewScreen(todos, lambda *a: None, TODAY, 6.0, window(), at(8))
    proposal = screen._proposal()
    by_id = {m.todo_id: m for m in proposal.moves}
    assert by_id[2].kind == "added" and by_id[2].new_start is None
    assert classify(by_id[2].alt.blocked_by) == OUT_OUTSIDE
    text = "\n".join(screen._section_lines(proposal))
    assert "Big" in text
    assert _T("replan_out_outside") in text  # non entra oggi
    assert _T("replan_out_eligible") not in text
    assert "90" in text and "30" in text  # numeri reali, mai inventati


def test_g_remaining_mostra_minuti():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=1)]
    screen = ReplanPreviewScreen(todos, lambda *a: None, TODAY, 6.0, window(), at(8))
    proposal = screen._proposal()
    assert proposal.remaining_min == 30
    assert _T("cli_replan_remaining", r=30)


def test_cli_outcome_e_remaining(tmp_files, capsys):
    import src.storage as st
    from src.cli import _cli_main
    from src.store import TodoStore

    today = datetime.now().strftime("%Y-%m-%d")
    store = TodoStore(
        [
            make_todo("A", todo_id=1, planned_for=today, stima_pomo=1),
            make_todo("Big", todo_id=2, stima_pomo=3),
        ]
    )
    store.commit()
    cfg = st.load_config()
    cfg["day_window"] = {
        "date": today,
        "start": "09:00",
        "end": "09:30",
        "events": [],
        "allday": [],
    }
    st.save_config(cfg)
    assert _cli_main(["replan", "--now", "08:00"]) == 0
    out = capsys.readouterr().out
    assert _T("replan_out_outside") in out  # Big non entra oggi
    assert "90" in out and "30" in out  # numeri reali
    assert _T("cli_replan_remaining", r=30) in out


def test_cross_view_stesso_outcome():
    """Buongiorno == P == G sulla classificazione, a parita' di stato."""
    confirmed = [
        make_todo("A", todo_id=1, planned_for=TODAY, stima_pomo=1),
        make_todo("B", todo_id=2, planned_for=TODAY, stima_pomo=1),
        make_todo("Big", todo_id=3, planned_for=TODAY, stima_pomo=3),
    ]
    candidates = [
        make_todo("A", todo_id=1, stima_pomo=1),
        make_todo("B", todo_id=2, stima_pomo=1),
        make_todo("Big", todo_id=3, stima_pomo=3),
    ]
    win = window()
    now = at(8)
    # P: scheduled_for_today sui confermati.
    sched, _ev, _al, _pl, dalts = scheduled_for_today(
        confirmed, TODAY, 6.0, win, now=now
    )
    dalts_by_id = {a.todo_id: a for a in dalts}
    p_out = {
        it.todo_id: classify(dalts_by_id[it.todo_id].blocked_by)
        for it in sched.unscheduled
    }
    assert set(p_out) == {2, 3}
    # Buongiorno: preview sugli stessi task come candidati (additiva).
    screen = PlanProposalScreen(candidates, lambda *a: None, TODAY, 6.0, now=now)
    screen.start_text, screen.end_text = "09:00", "09:30"
    screen._refresh_sched()
    b_alts = screen._preview_alts()
    # G: replan con current = sched di P.
    avail = [TimeWindow(at(9), at(9, 30))]
    proposal = replan(confirmed, TODAY, 6.0, avail, now=now, current=sched)
    g_out = {}
    for m in proposal.moves:
        if m.new_start is None and m.alt is not None:
            g_out[m.todo_id] = classify(m.alt.blocked_by)
    # B perde la gara con A in tutte le viste; Big e' fuori ovunque.
    assert p_out[2] == OUT_ELIGIBLE
    assert b_alts[2].blocked_by == "tasks"
    assert g_out[2] == OUT_ELIGIBLE
    assert p_out[3] == OUT_OUTSIDE
    assert classify(b_alts[3].blocked_by) == OUT_OUTSIDE
    assert g_out[3] == OUT_OUTSIDE
