"""Phase 4 Step P4-1 — censimento vincoli (docs/planner-phase4-plan.md §2).

Un test nominato per regola, sul comportamento CORRENTE (zero produzione
toccata): H1-H9 hard (devono valere), S1-S5 soft (influenzano, non
vietano). Vocabolario eseguibile prima di qualunque refactor.
"""

from datetime import date, datetime

from src.planner import Planner
from src.planner.models import TimeWindow
from src.planner.replan import replan
from tests.conftest import make_todo

TODAY_S = "2026-09-10"
DAY = date(2026, 9, 10)


def _win(h1, m1, h2, m2):
    return TimeWindow(datetime(2026, 9, 10, h1, m1), datetime(2026, 9, 10, h2, m2))


def _ids(plan):
    return {it.todo_id for it in plan.items}


# --- H1/H2: esclusione silenziosa ---------------------------------------------


def test_h1_stato_non_attivo_invisibile():
    done = make_todo("D", todo_id=1)
    done.done = True
    paused = make_todo("P", todo_id=2)
    paused.paused = True
    plan = Planner([done, paused], today=TODAY_S, hours=6.0).propose()
    assert _ids(plan) == set()  # mai in nessuna sezione, senza motivo


def test_h2_id_none_invisibile():
    plan = Planner([make_todo("N", todo_id=None)], today=TODAY_S, hours=6.0).propose()
    assert _ids(plan) == set()


# --- H3: scarto spiegato -------------------------------------------------------


def test_h3_scartato_oggi_in_fondo_con_motivo():
    todos = [
        make_todo("S", todo_id=1, plan_skip=TODAY_S, stima_pomo=50),
        make_todo("A", todo_id=2),
        make_todo("B", todo_id=3),
    ]
    plan = Planner(todos, today=TODAY_S, hours=1.0).propose()
    by_id = {it.todo_id: it for it in plan.items}
    assert [it.todo_id for it in plan.skipped] == [1]
    assert ("plan_skipped", {}) in by_id[1].reasons
    # Fuori dal consumo di capacita': A e B entrano comunque (2/2 pomo).
    assert {it.todo_id for it in plan.planned} == {2, 3}


# --- H4: mai tagliati -----------------------------------------------------------


def test_h4_mandatory_e_pianificati_mai_tagliati():
    todos = [
        make_todo("Scad", todo_id=1, due="2026-09-01", stima_pomo=4),
        make_todo("Pian", todo_id=2, planned_for=TODAY_S, stima_pomo=4),
        make_todo("Altro", todo_id=3),
    ]
    plan = Planner(todos, today=TODAY_S, hours=0.5).propose()
    assert {it.todo_id for it in plan.planned} == {1, 2}
    assert [it.todo_id for it in plan.cut] == [3]
    assert plan.planned_pomo > plan.capacity_pomo  # sforamento rappresentato


# --- H5/H6: availability e busy --------------------------------------------------


def test_h5_fuori_availability_unscheduled():
    plan = Planner([make_todo("A", todo_id=1)], today=TODAY_S, hours=6.0).propose()
    s = Planner.schedule(plan, [_win(9, 0, 10, 0)], [_win(9, 0, 10, 0)])
    assert s.scheduled == () and [it.todo_id for it in s.unscheduled] == [1]


def test_h6_busy_mai_overlap():
    plan = Planner([make_todo("A", todo_id=1)], today=TODAY_S, hours=6.0).propose()
    s = Planner.schedule(plan, [_win(9, 0, 18, 0)], [_win(9, 0, 12, 0)])
    (slot,) = s.scheduled
    assert (slot.start.hour, slot.end.hour) == (12, 12) or slot.start.hour >= 12


# --- H7: deadline -----------------------------------------------------------------


def test_h7_scadenza_oggi_ora_vincola_collocazione():
    from src.planner.scheduler import deadlines_for

    todos = [make_todo("A", todo_id=1, due=f"{TODAY_S} 09:30", stima_pomo=2)]
    plan = Planner(todos, today=TODAY_S, hours=6.0).propose()
    s = Planner.schedule(plan, [_win(9, 0, 18, 0)], (), deadlines_for(todos))
    assert s.scheduled == ()  # 2 pomo (60min) non entrano entro le 09:30


# --- H8: clip al giorno --------------------------------------------------------------


def test_h8_finestre_clippate_al_giorno():
    plan = Planner([make_todo("A", todo_id=1)], today=TODAY_S, hours=6.0).propose()
    overnight = TimeWindow(datetime(2026, 9, 10, 22, 0), datetime(2026, 9, 11, 2, 0))
    s = Planner.schedule(plan, [overnight], ())
    (slot,) = s.scheduled
    assert slot.end <= datetime(2026, 9, 11, 0, 0)  # mai oltre mezzanotte
    assert s.availability == (
        TimeWindow(datetime(2026, 9, 10, 22, 0), datetime(2026, 9, 11, 0, 0)),
    )


# --- H9: replan senza passato -----------------------------------------------------------


def test_h9_replan_slot_passati_indisponibili():
    todos = [make_todo("A", todo_id=1, planned_for=TODAY_S, stima_pomo=2)]
    p = replan(
        todos, TODAY_S, 6.0, [_win(9, 0, 18, 0)], (), datetime(2026, 9, 10, 15, 0)
    )
    assert [(m.kind, m.new_start) for m in p.moves] == [("moved", "15:00")]


# --- S1-S5: merito influenza, non vieta ------------------------------------------------------


def test_s_merito_non_vieta():
    from src.models import Priority

    # S1: bassa priorita' comunque pianificata con capacita'.
    plan = Planner(
        [make_todo("L", todo_id=1, priority=Priority.LOW)], today=TODAY_S, hours=6.0
    ).propose()
    assert [it.todo_id for it in plan.planned] == [1]
    # S3: domani aggiunge ma non decide da solo; S4: planned bonus.
    a = Planner(
        [make_todo("T", todo_id=1, due="2026-09-11")], today=TODAY_S, hours=6.0
    ).propose()
    b = Planner(
        [make_todo("P", todo_id=1, planned_for=TODAY_S)], today=TODAY_S, hours=6.0
    ).propose()
    assert a.items[0].score == 30 + 10  # domani + media
    assert b.items[0].score == 10 + 5  # media + pianificato
    # S5: calibrazione annota senza cambiare il merito.
    e = make_todo("E", todo_id=1, stima_pomo=2)
    s_plain = Planner([e], today=TODAY_S, hours=6.0, factor=None).propose().to_legacy()
    s_cal = Planner([e], today=TODAY_S, hours=6.0, factor=2.0).propose().to_legacy()
    assert [s for _, s, _ in s_plain] == [s for _, s, _ in s_cal]
    assert any(k == "plan_calibrated" for _, _, rs in s_cal for k, _ in rs)
