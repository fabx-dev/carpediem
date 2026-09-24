"""#53 Shortcut consistency: inventario binding, G/W, s/Esc coerenti."""

import src.app as app_mod
import src.screens.plan as plan_mod
import src.screens.views as views_mod
from tests.conftest import make_app, make_todo, run, wait_for


def _bindings():
    return list(app_mod.TodoApp.BINDINGS)


def test_keys_uniche_e_g_w_presenti():
    keys = [b.key for b in _bindings()]
    assert len(keys) == len(set(keys)), f"duplicati: {keys}"
    actions = {b.key: b.action for b in _bindings()}
    assert actions["G"] == "view_replan"
    assert actions["W"] == "view_week_review"
    # G e W sono maiuscole distinte da g/w (convenzione)
    assert "g" in actions and actions["g"] != actions["G"]
    assert "w" in actions and actions["w"] != actions["W"]


def test_azioni_binding_esistono():
    methods = dir(app_mod.TodoApp)
    for b in _bindings():
        assert f"action_{b.action}" in methods, b.action


def test_s_conferma_su_review_e_replan():
    for screen in (plan_mod.ReviewScreen, plan_mod.ReplanPreviewScreen):
        bindings = {b.key: b.action for b in screen.BINDINGS}
        assert bindings.get("s") == "confirm", screen.__name__
        assert bindings.get("escape") == "close", screen.__name__


def test_esc_chiude_detail_senza_crash():
    async def t():
        app = make_app([make_todo("A", todo_id=1)])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            ok = await wait_for(
                pilot, lambda: type(app.screen).__name__ == "DetailScreen"
            )
            assert ok
            assert views_mod.DetailScreen.BINDINGS[0].key == "escape"
            await pilot.press("escape")
            await pilot.pause()

    run(t())
