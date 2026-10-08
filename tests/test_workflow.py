"""Workflow consigliato: voce menu Giornata + screen checklist."""

import carpediem.commands as commands_module
from carpediem.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts


def test_workflow_prima_voce_giornata_e_action(tmp_files):
    cats = commands_module.menu_categories()
    day = [c for c in cats if c[0] == T("menu_cat_day_t")][0]
    first = day[2][0]
    assert first[0] == T("menu_workflow_t")
    assert first[2] == "action_view_workflow"
    assert first[3] is None
    app = make_app([make_todo("A")])
    assert callable(getattr(app, "action_view_workflow", None))
    assert "[" not in (first[0] + (first[1] or ""))


def test_workflow_screen_mostra_cinque_sezioni(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_view_workflow()
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "WorkflowScreen"
            text = screen_texts(app.screen)
            assert T("workflow_title") in text
            assert T("workflow_intro") in text
            for i in range(1, 6):
                assert T(f"workflow_s{i}_t") in text
                assert T(f"workflow_s{i}_b") in text
            # rimando esplicito agli Obiettivi nella sezione settimana
            assert T("menu_goals_t") in text or "Obiettivi" in text or "Goals" in text
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "WorkflowScreen"

    run(t())
