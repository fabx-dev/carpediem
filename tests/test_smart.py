"""Smart list salvate: salva/applica/sgancia/elimina + layout (isolati)."""

import asyncio

from textual.widgets import Button, Input

import src.domain as domain
from tests.conftest import make_app, make_todo, screen_texts, wait_for


def _todos():
    return [
        make_todo("A-casa", todo_id=1, tags=["casa"]),
        make_todo("B-lavoro", todo_id=2, tags=["lavoro"], project="uff"),
        make_todo("C-libero", todo_id=3),
    ]


def test_salva_attuale_e_riapplica(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_filter_by_tag()  # ciclo: tutti -> casa
            assert app.filter_tag == "casa"
            app.action_open_smart_lists()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "SmartListScreen"
            await pilot.click("#smart-name")
            await pilot.pause()
            for ch in "Serale":
                await pilot.press(ch)
            await pilot.pause()
            assert app.screen.query_one("#smart-name", Input).value == "Serale"
            await pilot.click("#smart-save")
            ok = await wait_for(
                pilot, lambda: len(app.config.get("smart_lists", [])) == 1
            )
            assert ok
            assert app.config["smart_lists"][0]["name"] == "Serale"
            assert app.active_smart == "Serale"
            # Sgancio manuale: f tocca lo stato -> smart resta salvata
            await pilot.press("escape")
            await pilot.pause()
            app.action_filter_todos()
            await pilot.pause()
            assert app.active_smart is None
            assert len(app.config["smart_lists"]) == 1
            # Riapplica dalla screen: solo A-casa in tabella
            app.action_open_smart_lists()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#smart-apply-0")
            ok = await wait_for(pilot, lambda: app.active_smart == "Serale")
            assert ok
            titles = [t.title for t in app._filtered_todos()]
            assert titles == ["A-casa"]

    asyncio.run(t())


def test_elimina_da_screen(tmp_files):
    async def t():
        app = make_app(_todos())
        app.config["smart_lists"] = [
            {"name": "Una", "state": None, "tag": None, "project": None, "search": None}
        ]
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_smart_lists()
            await pilot.pause()
            await pilot.pause()
            await pilot.click("#smart-del-0")
            ok = await wait_for(
                pilot, lambda: app.config.get("smart_lists", ["x"]) == []
            )
            assert ok
            import src.lang as lang_module

            texts = screen_texts(app.screen)
            assert "Una" not in texts
            assert lang_module.T("smart_empty") in texts
            assert type(app.screen).__name__ == "SmartListScreen"  # resta aperta

    asyncio.run(t())


def test_duplicati_e_limite_e_nome_vuoto():
    assert domain.validate_smart_name("  ", [], 10)[0] is False
    base = [
        {"name": "Casa", "state": None, "tag": None, "project": None, "search": None}
    ]
    ok, key, _p = domain.validate_smart_name("casa", base, 10)  # dup insensitive
    assert not ok and key == "n_smart_dup"
    piena = [
        {"name": f"L{i}", "state": None, "tag": None, "project": None, "search": None}
        for i in range(10)
    ]
    ok, key, _p = domain.validate_smart_name("Undicesima", piena, 10)
    assert not ok and key == "n_smart_full"
    ok, _k, p = domain.validate_smart_name("  Nuova ", base, 10)
    assert ok and p == {"n": "Nuova"}


def test_empty_state_e_snapshot(tmp_files):
    async def t():
        app = make_app(_todos())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_smart_lists()
            await pilot.pause()
            await pilot.pause()
            import src.lang as lang_module

            assert lang_module.T("smart_empty") in screen_texts(app.screen)

    asyncio.run(t())


def test_menu_e_palette_offrono_smart(tmp_files):
    import tests.conftest as conftest

    actions = [
        action
        for _ct, _ch, items in conftest.commands_module.menu_categories()
        for _t, _h, action, _sc in items
    ]
    assert "action_open_smart_lists" in actions


def test_layout_terminale_piccolo(tmp_files):
    async def t():
        for size in ((120, 40), (80, 24), (70, 20)):
            app = make_app(_todos())
            app.config["smart_lists"] = [
                {
                    "name": f"L{i}",
                    "state": "attivo",
                    "tag": "casa",
                    "project": None,
                    "search": None,
                }
                for i in range(3)
            ]
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_open_smart_lists()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "SmartListScreen"
                box = app.screen.query_one("#smart-box").region
                for wid in ("#smart-save", "#smart-close"):
                    reg = app.screen.query_one(wid, Button).region
                    assert reg.y >= box.y, (size, wid, reg, box)
                    assert reg.y + reg.height <= box.y + box.height, (
                        size,
                        wid,
                        reg,
                        box,
                    )

    asyncio.run(t())
