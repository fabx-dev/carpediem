"""Test onboarding: demo data e welcome screen."""

from datetime import datetime

import src.main as m


def test_demo_validi():
    todos = m._demo_todos(1)
    assert len(todos) >= 5
    ids = [t.id for t in todos]
    assert len(ids) == len(set(ids))
    padre = next(t for t in todos if t.title.startswith("Preventivo"))
    figli = [t for t in todos if t.parent_id == padre.id]
    assert len(figli) == 2
    assert all(t.project == "acme" for t in [padre] + figli)
    assert any(t.done for t in todos)
    # date valide e relative a oggi
    today = datetime.now().date().strftime("%Y-%m-%d")
    assert any(t.due == today for t in todos)
    d = m.TodoItem.to_dict(padre)
    assert m.TodoItem.from_dict(d).title == padre.title


def test_welcome_demo_e_vuoto(tmp_files):
    import asyncio

    from tests.conftest import make_app

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "WelcomeScreen"
            await pilot.click(app.screen.query_one("#wel-demo"))
            await pilot.pause()
            await pilot.pause()
            assert len(app.todos) >= 5
            assert app.config["onboarded"] is True
            import json

            assert json.loads(m.CONFIG_FILE.read_text())["onboarded"] is True
            assert len(m.load_todos()) >= 5

    asyncio.run(t())

    async def t2():
        app = make_app([])
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.todos) == 0
            assert app.config["onboarded"] is True

    asyncio.run(t2())


def test_nessun_welcome_se_gia_visto(tmp_files):
    import asyncio
    import json

    from tests.conftest import make_app, make_todo

    m.CONFIG_FILE.write_text(json.dumps({"onboarded": True}))

    async def t():
        app = make_app([])
        assert app.config["onboarded"] is True
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "WelcomeScreen"

    asyncio.run(t())

    async def t2():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "WelcomeScreen"

    asyncio.run(t2())


def test_welcome_mostra_hint_cifratura(tmp_files):
    import asyncio

    from src.lang import T
    from tests.conftest import make_app, screen_texts

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "WelcomeScreen"
            hint = T(
                "welcome_sec_hint",
                cat=T("menu_cat_sys_t"),
                voce=T("menu_security_t"),
            )
            assert hint in screen_texts(app.screen)

    asyncio.run(t())
