"""Test obiettivi, sicurezza ed export CSV/Markdown."""

from datetime import datetime, timedelta

from textual.widgets import Input

import src.main as m
from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts


def _ds(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")


def test_goals_salva_obiettivi_in_config(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_edit_goals()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "GoalsScreen"
            app.screen.query_one("#goals-daily", Input).value = "7"
            app.screen.query_one("#goals-weekly", Input).value = "30"
            app.screen.query_one("#goals-pomo", Input).value = "10"
            await pilot.press("ctrl+enter")
            await pilot.pause()
            await pilot.pause()
            assert app.config["daily_goal"] == 7
            assert app.config["weekly_goal"] == 30
            assert app.config["pomo_daily_goal"] == 10
            assert m.load_config()["daily_goal"] == 7

    run(t())


def test_security_mostra_stato(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_security()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "SecurityScreen"
            txt = screen_texts(app.screen)
            assert T("sec_title") in txt
            await pilot.press("escape")
            await pilot.pause()

    run(t())


def test_export_csv_scrive_file(tmp_files, monkeypatch):
    async def t():
        app = make_app(
            [make_todo("A", project="casa", tags=["x"], due=_ds(1), stima_pomo=2)]
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_export_csv()
            await pilot.pause()

            files = sorted(
                (tmp_files / "CarpeDiem_screenshots").glob("carpediem_export_*.csv")
            )
            assert len(files) == 1
            content = files[0].read_text(encoding="utf-8")
            assert "A" in content and "casa" in content

    import src.app as app_module

    monkeypatch.setattr(app_module, "_home", lambda: tmp_files)
    run(t())


def test_export_stats_csv_e_markdown(tmp_files, monkeypatch):
    async def t():
        app = make_app([make_todo("A", done=True, completed_at=_ds(0) + " 10:00")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_export_stats_csv()
            app.action_export_data()
            await pilot.pause()
            out = tmp_files / "CarpeDiem_screenshots"
            assert len(sorted(out.glob("carpediem_stats_*.csv"))) == 1
            md = sorted(out.glob("carpediem_export_*.md"))
            assert len(md) == 1
            assert "A" in md[0].read_text(encoding="utf-8")

    import src.app as app_module

    monkeypatch.setattr(app_module, "_home", lambda: tmp_files)
    run(t())
