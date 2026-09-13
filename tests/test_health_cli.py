"""Test salute progetti e CLI (TASKO_HOME isolata)."""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta

import src.main as m
from tests.conftest import make_app, make_todo, screen_texts


def _ds(offset: int) -> str:
    """Giorni nel passato (per completamenti e scadenze vecchie)."""
    return (datetime.now().date() - timedelta(days=offset)).strftime("%Y-%m-%d")


def _fut(days: int) -> str:
    """Giorni nel futuro (per scadenze a venire)."""
    return (datetime.now().date() + timedelta(days=days)).strftime("%Y-%m-%d")


def test_verdetti():
    old = [
        # CRITICO: 3 in ritardo
        make_todo("c1", project="crit", due=_ds(5), todo_id=1),
        make_todo("c2", project="crit", due=_ds(5), todo_id=2),
        make_todo("c3", project="crit", due=_ds(5), todo_id=3),
        # CRITICO: ratio bassa con ritardo (1/4, 1 late)
        make_todo("r1", project="ratio", due=_ds(2), todo_id=4),
        make_todo("r2", project="ratio", due=_fut(10), todo_id=5),
        make_todo(
            "r3", project="ratio", done=True, completed_at=_ds(0) + " 10:00", todo_id=6
        ),
        make_todo("r4", project="ratio", due=_fut(10), todo_id=7),
        make_todo("r5", project="ratio", due=_fut(10), todo_id=14),
        # A RISCHIO: 1 in ritardo, ratio alta
        make_todo("k1", project="risk", due=_ds(1), todo_id=8),
        make_todo("k2", project="risk", due=_fut(10), todo_id=9),
        make_todo(
            "k3", project="risk", done=True, completed_at=_ds(0) + " 10:00", todo_id=10
        ),
        make_todo(
            "k4", project="risk", done=True, completed_at=_ds(0) + " 10:00", todo_id=11
        ),
        # OK: tutto avanti
        make_todo("o1", project="ok", due=_fut(10), todo_id=12),
        # senza progetto: ignorato
        make_todo("np", due=_ds(5), todo_id=13),
    ]
    scr = m.HealthScreen(old)
    rows = {p: (v, d, t, ll) for p, v, _, d, t, ll, _ in scr._rows()}
    assert rows["crit"][0] == "CRITICO", rows["crit"]
    assert rows["ratio"][0] == "CRITICO", rows["ratio"]
    assert rows["risk"][0] == "A RISCHIO", rows["risk"]
    assert rows["ok"][0] == "OK", rows["ok"]
    assert "—" not in rows and all("np" not in str(r) for r in rows.values())
    # peggiori prima
    order = [p for p, _, _, _, _, _, _ in scr._rows()]
    assert order.index("crit") < order.index("risk") < order.index("ok")


def test_health_ui(tmp_files):
    async def t():
        app = make_app([make_todo("A", project="acme", due=_ds(3))])
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "HealthScreen"
            content = screen_texts(app.screen)
            assert "CRITICO" in content or "A RISCHIO" in content, content
            await pilot.press("escape")
            await pilot.pause()
            from src.main import CarpeDiemMenuProvider

            assert "Salute progetti" in [t for t, _, _ in CarpeDiemMenuProvider.MENU_IT]

    asyncio.run(t())


def _cli(args, home):
    from pathlib import Path as _P

    env = dict(os.environ, TASKO_HOME=str(home))
    return subprocess.run(
        [sys.executable, "-m", "src.main", *args],
        cwd=str(_P(__file__).resolve().parent.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_giro_completo(tmp_path):
    home = tmp_path / "home"
    r = _cli(
        [
            "add",
            "Chiamare Anna",
            "--due",
            "oggi",
            "--priority",
            "alta",
            "--project",
            "casa",
            "--tags",
            "a,b",
        ],
        home=home,
    )
    assert r.returncode == 0, r.stderr
    tid = int(r.stdout.strip())
    r = _cli(["list", "--porcelain"], home=home)
    assert r.returncode == 0
    assert f"{tid}|attivo|alta|" in r.stdout, r.stdout
    r = _cli(["list", "--state", "completato"], home=home)
    assert r.stdout.strip() == ""
    r = _cli(["show", str(tid)], home=home)
    assert "Chiamare Anna" in r.stdout and "casa" in r.stdout
    r = _cli(["done", str(tid)], home=home)
    assert r.returncode == 0
    r = _cli(["list", "--state", "done"], home=home)
    assert str(tid) in r.stdout
    r = _cli(["done", "9999"], home=home)
    assert r.returncode == 1 and "non trovato" in r.stderr
    r = _cli(["add", "X", "--due", "mai"], home=home)
    assert r.returncode == 2


def test_health_layout_terminale_piccolo(tmp_files):
    """La cornice contiene lista + Chiudi anche a terminale piccolo (niente overflow)."""

    async def t():
        todos = [
            make_todo(f"T{i}", todo_id=i, project=f"p{i % 8}", due=_ds(5))
            for i in range(1, 25)
        ]
        for size in ((120, 40), (80, 24), (70, 20)):
            app = make_app(todos)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                app.action_view_health()
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "HealthScreen"
                box = app.screen.query_one("#hea-box").region
                close = app.screen.query_one("#hea-close").region
                lst = app.screen.query_one("#hea-list").region
                for name, reg in (("close", close), ("list", lst)):
                    assert reg.y >= box.y, (size, name, reg, box)
                    assert reg.y + reg.height <= box.y + box.height, (
                        size,
                        name,
                        reg,
                        box,
                    )

    asyncio.run(t())
