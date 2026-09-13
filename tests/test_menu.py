"""Test menu per funzioni (m): voci a sinistra, sottomenu a destra, filtro."""

import src.commands as commands_module
import src.lang as lang_module
from src.lang import T
from tests.conftest import make_app, make_todo, run, screen_texts, wait_for


def test_struttura_quattro_categorie_e_action_esistenti(tmp_files):
    cats = commands_module.menu_categories()
    assert len(cats) == 4
    titoli = [c[0] for c in cats]
    assert T("menu_cat_day_t") in titoli
    assert T("menu_cat_sys_t") in titoli
    app = make_app([make_todo("A")])
    totale = 0
    for _ct, _ch, items in cats:
        assert len(items) >= 5
        for _t, _h, action, shortcut in items:
            assert callable(getattr(app, action, None)), action
            assert "[" not in (_t + (_h or "")), (_t, _h)
            if shortcut:
                assert "[" not in shortcut and "]" not in shortcut
            totale += 1
    assert totale >= 29


def test_menu_it_legacy_contiene_chiavi_storiche(tmp_files):
    names = [t for t, _, _ in commands_module.CarpeDiemMenuProvider.MENU_IT]
    actions = [a for _, _, a in commands_module.CarpeDiemMenuProvider.MENU_IT]
    assert "Impostazioni" in names and "Backup: crea ora" in names
    assert "Chiusura giornata" in names and "Salute progetti" in names
    assert "action_plan_day" in actions


def test_provider_palette_prefissa_categoria(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            prov = commands_module.CarpeDiemMenuProvider(app.screen)
            seen = [t for t, _, _ in prov._iter()]
            assert any("›" in s for s in seen), seen
            assert len(seen) == sum(
                len(c[2]) for c in commands_module.menu_categories()
            )

    run(t())


def test_m_apre_menu_e_ctrl_p_resta_palette(tmp_files):
    actions = {b.key: b.action for b in type(make_app([make_todo("A")])).BINDINGS}
    assert actions.get("m") == "open_menu"
    assert actions.get("ctrl+p") == "command_palette"
    assert type(make_app([make_todo("A")])).COMMAND_PALETTE_BINDING == "ctrl+p"


def _row_text(w):
    """Testo piano di una riga (version-proof: content su 8.x, renderable su 3.x)."""
    for attr in ("content", "renderable"):
        v = getattr(w, attr, None)
        if v is not None:
            return str(v)
    return ""


def _visible_texts(screen):
    out = []
    for w in screen.query("MenuRow"):
        try:
            if w.has_class("hidden"):
                continue
            parent_hidden = False
            p = w.parent
            while p is not None and p is not screen:
                if hasattr(p, "has_class") and p.has_class("hidden"):
                    parent_hidden = True
                    break
                p = getattr(p, "parent", None)
            if parent_hidden:
                continue
        except Exception:
            pass
        out.append(_row_text(w))
    return " ".join(out)


def _bar_cats(screen):
    return {
        w.id
        for w in screen.query("#menu-bar MenuRow")
        if (w.id or "").startswith("menu-cat-")
    }


def _visible_rows(screen, gi):
    try:
        return [
            w
            for w in screen.query(f"#menu-drop-{gi} MenuRow")
            if not w.has_class("hidden")
        ]
    except Exception:
        return []


def _open_idx(screen):
    return getattr(screen, "_open_idx", None)


async def _open_menu(pilot, app):
    await pilot.press("m")
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "MenuScreen"
    assert len(_bar_cats(app.screen)) == 4


def test_navigazione_categorie_voci_e_chiusura(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            # sinistra: solo le 4 voci; destra: primo sottomenu gia' aperto
            assert _open_idx(app.screen) == 0
            assert len(_visible_rows(app.screen, 0)) >= 5
            assert T("menu_review_t") in _visible_texts(app.screen)
            assert getattr(app.screen.focused, "id", None) == "menu-cat-0"
            # marcatore voce aperta + contatore
            assert "›" in screen_texts(app.screen)
            # click sulla voce aperta lo chiude (toggle), click su altra apre
            await pilot.click("#menu-cat-0")
            assert await wait_for(pilot, lambda: _open_idx(app.screen) is None)
            assert len(_bar_cats(app.screen)) == 4
            # altra voce: sottomenu con le sue voci
            await pilot.click("#menu-cat-1")
            assert await wait_for(pilot, lambda: _open_idx(app.screen) == 1)
            assert T("menu_cal_t") in screen_texts(app.screen)
            # esc chiude il sottomenu, resto nel menu
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "MenuScreen"
            assert _open_idx(app.screen) is None
            # esc chiude il menu
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "MenuScreen"

    run(t())


def test_tasto_chiudi_con_click(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            assert await wait_for(pilot, lambda: _open_idx(app.screen) == 0)
            await pilot.click("#menu-close")
            assert await wait_for(
                pilot, lambda: type(app.screen).__name__ != "MenuScreen"
            )

    run(t())


def test_scelta_voce_con_click(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        app.filter_search = "qualcosa"
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_open_menu()
            await pilot.pause()
            await pilot.pause()
            n_cat = len(commands_module.menu_categories())
            await pilot.click(f"#menu-cat-{n_cat - 1}")
            assert await wait_for(pilot, lambda: _open_idx(app.screen) == n_cat - 1)
            assert len(_visible_rows(app.screen, n_cat - 1)) >= 5
            target = f"#menu-item-{n_cat - 1}-2"
            assert T("menu_clearf_t") in screen_texts(app.screen)
            await pilot.click(target)
            assert await wait_for(
                pilot, lambda: type(app.screen).__name__ != "MenuScreen"
            )
            assert app.filter_search == "" and app.filter_tag is None

    run(t())


def test_frecce_ed_enter_da_tastiera(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        app.filter_search = "qualcosa"
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            assert getattr(app.screen.focused, "id", None) == "menu-cat-0"
            assert _open_idx(app.screen) == 0
            # giu/su scorrono le voci con anteprima del sottomenu a destra
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-cat-1"
            assert _open_idx(app.screen) == 1
            assert len(_visible_rows(app.screen, 1)) >= 5
            await pilot.press("up")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-cat-0"
            assert _open_idx(app.screen) == 0
            # destra entra nel sottomenu, su torna alla voce
            await pilot.press("right")
            await pilot.pause()
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-item-0-0"
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-item-0-1"
            await pilot.press("left")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-cat-0"
            # Enter sulla voce ENTRA (non chiude): resta nel menu
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "MenuScreen"
            assert _open_idx(app.screen) == 1
            assert getattr(app.screen.focused, "id", None) == "menu-item-1-0"
            # Enter sulla riga esegue (Mini-kanban, prima voce di Viste) e chiude il menu
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "Screen"

    run(t())


def test_enter_su_riga_esegue_action(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        app.filter_search = "qualcosa"
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            # giu fino a Sistema, destra, giu x2 = Pulisci filtri, enter
            await pilot.press("down")
            await pilot.press("down")
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-cat-3"
            await pilot.press("right")
            await pilot.pause()
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-item-3-0"
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-item-3-2"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "MenuScreen"
            assert app.filter_search == "" and app.filter_tag is None

    run(t())


def test_tasti_1_4_saltano_alle_categorie(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            await pilot.press("3")
            await pilot.pause()
            await pilot.pause()
            assert _open_idx(app.screen) == 2
            assert T("menu_backup_now_t") in screen_texts(app.screen)
            await pilot.press("1")
            await pilot.pause()
            await pilot.pause()
            assert _open_idx(app.screen) == 0

    run(t())


def test_righe_compatte_su_due_righe(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            assert await wait_for(pilot, lambda: _open_idx(app.screen) == 0)
            row = app.screen.query_one("#menu-item-0-0")
            assert row.region.height == 2, row.region
            txt = screen_texts(app.screen)
            assert T("menu_review_t") in txt
            # aiuto sulla seconda riga, in grigio: presente nel testo
            assert T("menu_review_h") in txt

    run(t())


def test_filtro_digitazione(tmp_files):
    async def _type(pilot, word):
        for ch in word:
            await pilot.press(ch)
            await pilot.pause()

    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            kanban_before = app.config.get("kanban_visible", True)
            await _type(pilot, "backup")
            assert await wait_for(
                pilot, lambda: T("menu_no_match") not in screen_texts(app.screen)
            )
            txt = _visible_texts(app.screen)
            # conteggio filtro visibile, solo Dati mostra risultati
            assert "backup" in screen_texts(app.screen).lower()
            assert T("menu_backup_now_t") in txt
            assert T("menu_cal_t") not in txt
            # i tasti digitati non hanno attivato i binding globali (b/c/k/p)
            assert type(app.screen).__name__ == "MenuScreen"
            assert app.config.get("kanban_visible", True) == kanban_before
            # giu va al primo risultato, enter lo esegue (backup: nessun modale)
            await pilot.press("down")
            await pilot.pause()
            assert getattr(app.screen.focused, "id", None) == "menu-item-2-0"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "MenuScreen"

    run(t())


def test_filtro_backspace_esc_e_nessun_risultato(tmp_files):
    async def t():
        app = make_app([make_todo("A")])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await _open_menu(pilot, app)
            for ch in "zzz":
                await pilot.press(ch)
                await pilot.pause()
            assert await wait_for(
                pilot, lambda: T("menu_no_match", q="zzz") in screen_texts(app.screen)
            )
            # backspace svuota un carattere alla volta
            await pilot.press("backspace")
            await pilot.pause()
            assert app.screen._filter == "zz"
            # esc svuota il filtro ma resta nel menu (torna al gruppo aperto)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "MenuScreen"
            assert app.screen._filter == ""
            assert T("menu_review_t") in screen_texts(app.screen)
            # esc chiude il sottomenu, poi il menu
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "MenuScreen"
            assert _open_idx(app.screen) is None
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ != "MenuScreen"

    run(t())


def test_nuove_chiavi_parita_it_en(tmp_files):
    for key in (
        "menu_cat_day_t",
        "menu_cat_views_t",
        "menu_cat_data_t",
        "menu_cat_sys_t",
        "menu_title",
        "menu_hint",
        "menu_pick",
        "menu_filter",
        "menu_no_match",
        "menu_dayplan_t",
        "menu_cal_t",
        "menu_week_t",
        "menu_kbmini_t",
        "menu_kbfull_t",
        "menu_stats_t",
        "menu_tpl_t",
        "menu_theme_t",
        "menu_keys_t",
        "menu_snap_t",
        "menu_refresh_t",
        "menu_quit_t",
    ):
        assert key in lang_module.STRINGS["it"], key
        assert key in lang_module.STRINGS["en"], key
