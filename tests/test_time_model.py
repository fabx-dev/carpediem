"""F0 TimeModel: clip/fuse/residual/slack (puro, deterministico)."""

from datetime import datetime

from carpediem.planner.models import TimeWindow
from carpediem.planner.time_model import clip_future, fuse, residual, slack


def _w(s, e):
    return TimeWindow(datetime(2026, 10, 8, *s), datetime(2026, 10, 8, *e))


def _fmt(windows):
    return [(w.start.strftime("%H:%M"), w.end.strftime("%H:%M")) for w in windows]


def test_fuse_sovrapposti_e_contenuti():
    out = fuse([_w((9, 0), (12, 0)), _w((11, 0), (14, 0)), _w((10, 0), (11, 0))])
    assert _fmt(out) == [("09:00", "14:00")]


def test_fuse_contigui_e_duplicati():
    out = fuse([_w((9, 0), (10, 0)), _w((10, 0), (11, 0)), _w((9, 0), (10, 0))])
    assert _fmt(out) == [("09:00", "11:00")]


def test_fuse_multipli_e_giorni_diversi():
    nxt = TimeWindow(datetime(2026, 10, 9, 9, 0), datetime(2026, 10, 9, 10, 0))
    out = fuse([_w((14, 0), (15, 0)), _w((9, 0), (10, 0)), nxt])
    assert _fmt(out) == [("09:00", "10:00"), ("14:00", "15:00")] or len(out) == 3
    assert out[-1] == nxt


def test_fuse_scarti_invalido_e_overnight_valido():
    bad = TimeWindow(datetime(2026, 10, 8, 12, 0), datetime(2026, 10, 8, 12, 0))
    night = TimeWindow(datetime(2026, 10, 8, 22, 0), datetime(2026, 10, 9, 2, 0))
    out = fuse([bad, night, "garbage", None])
    assert out == [night]


def test_clip_future_taglia_passato():
    avail = [_w((9, 0), (18, 0))]
    now = datetime(2026, 10, 8, 15, 0)
    assert _fmt(clip_future(avail, now)) == [("15:00", "18:00")]


def test_clip_future_altro_giorno_vuoto_e_overnight_span():
    avail = [_w((9, 0), (18, 0))]
    assert clip_future(avail, datetime(2026, 10, 9, 10, 0)) == []
    night = [TimeWindow(datetime(2026, 10, 8, 22, 0), datetime(2026, 10, 9, 2, 0))]
    out = clip_future(night, datetime(2026, 10, 9, 0, 30))
    assert len(out) == 1 and out[0].start == datetime(2026, 10, 9, 0, 30)


def test_clip_future_none_nessuna_clip():
    avail = [_w((9, 0), (18, 0))]
    assert clip_future(avail, None) == avail


def test_residual_toglie_busy_e_passato():
    avail = [_w((9, 0), (18, 0))]
    busy = [_w((10, 0), (11, 0))]
    assert residual(avail, busy, datetime(2026, 10, 8, 9, 0)) == 8 * 60
    assert residual(avail, busy, datetime(2026, 10, 8, 15, 0)) == 3 * 60


def test_slack_canonico():
    deadline = datetime(2026, 10, 8, 18, 0)
    now = datetime(2026, 10, 8, 15, 0)
    assert slack(deadline, now, 60) == 120
    assert slack(deadline, now, 240) == -60
    assert slack(None, now, 60) is None
    assert slack(deadline, None, 60) is None


def test_plan_now_vincolante_niente_slot_passato():
    from datetime import date

    import carpediem.planner as p
    from carpediem.planner.models import PlanningRequest

    def task(tid):
        return p.TaskView(id=tid, state="attivo", estimate_pomo=2, created="2026-10-01")

    day = date(2026, 10, 8)
    avail = (TimeWindow(datetime(2026, 10, 8, 9, 0), datetime(2026, 10, 8, 18, 0)),)
    req_morning = PlanningRequest(
        day=day, tasks=(task(1),), capacity_pomo=12.0, availability=avail
    )
    req_late = PlanningRequest(
        day=day,
        tasks=(task(1),),
        capacity_pomo=12.0,
        availability=avail,
        now=datetime(2026, 10, 8, 15, 0),
    )
    early = p.plan(req_morning)
    late = p.plan(req_late)
    assert early.scheduled.scheduled[0].start == datetime(2026, 10, 8, 9, 0)
    assert late.scheduled.scheduled[0].start == datetime(2026, 10, 8, 15, 0)
    assert late.scheduled.availability == (
        TimeWindow(datetime(2026, 10, 8, 15, 0), datetime(2026, 10, 8, 18, 0)),
    )
    # Determinismo a parita' di request.
    again = p.plan(req_late)
    assert again.scheduled.scheduled[0].start == late.scheduled.scheduled[0].start


def test_replan_clip_wrapper_stessi_risultati():
    from carpediem.planner.replan import _clip_future

    avail = [_w((9, 0), (18, 0))]
    now = datetime(2026, 10, 8, 10, 30)
    assert _fmt(_clip_future(avail, now)) == [("10:30", "18:00")]
    assert _fmt(clip_future(avail, now)) == [("10:30", "18:00")]
