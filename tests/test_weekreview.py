"""Weekly Review #51: execution-based, read-only, offline, aperta da W."""

from datetime import date, timedelta

import src.storage as st
from src.lang import T
from src.models import TaskExecution
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for


def _monday():
    d = date.today()
    return d - timedelta(days=d.weekday())


def _todos():
    monday = _monday().strftime("%Y-%m-%d")
    a = make_todo("A", todo_id=1, stima_pomo=2)
    a.done = True
    a.completed_at = monday + " 10:00"
    b = make_todo("B", todo_id=2, plan_skip=monday)
    return [a, b]


def _seed():
    monday = _monday().strftime("%Y-%m-%d")
    todos = _todos()
    st.save_todos_synced([t.to_dict() for t in todos], [])
    st.append_execution(
        TaskExecution(1, monday + " 09:00", monday + " 10:00", 60, 90, 2, True)
    )
    return make_app(todos)


def test_weekreview_dati_execution(tmp_files):
    async def t():
        app = _seed()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_week_review()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "WeekReviewScreen"
            txt = screen_texts(app.screen)
            assert T("wr_sec_perf") in txt
            assert T("wr_perf_row", est=60, act=90, acc=67, n=1, c="LOW") in txt
            assert T("wr_sec_days") in txt

    run(t())


def test_weekreview_offline_e_readonly(tmp_files):
    async def t():
        app = _seed()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            import hashlib

            before = hashlib.md5(st.DATA_FILE.read_bytes()).hexdigest()
            app.action_view_week_review()
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            after = hashlib.md5(st.DATA_FILE.read_bytes()).hexdigest()
            assert before == after
            assert len(st.load_executions()) == 1

    run(t())


def test_weekreview_w_apre_e_3_taglie(tmp_files):
    for size in ((120, 40), (80, 24), (70, 20)):
        _one(size)


def _one(size):
    async def t():
        app = _seed()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.press("W")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "WeekReviewScreen"
            )
            assert ok, size
            assert T("wr_legend") in screen_texts(app.screen), size
            await pilot.press("escape")
            await pilot.pause()

    run(t())


def test_weekreview_vincolo_no_import_network():
    import pathlib

    src = pathlib.Path("src/screens/views.py").read_text(encoding="utf-8")
    for banned in ("integrations", "urllib", "requests", "http"):
        assert banned not in src
