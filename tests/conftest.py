"""Fixture comuni: isolano TUTTI i file reali (mai ~/.todo_* nei test)."""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.app as app_module  # noqa: E402  (serve sys.path sopra)
import src.cli as cli_module  # noqa: E402
import src.commands as commands_module  # noqa: E402
import src.lang as lang  # noqa: E402
import src.main as main  # noqa: E402
import src.models as models  # noqa: E402
import src.screens as screens  # noqa: E402
import src.screens._shared as screens_shared  # noqa: E402
import src.screens.form as screens_form  # noqa: E402
import src.screens.menu as screens_menu  # noqa: E402
import src.screens.plan as screens_plan  # noqa: E402
import src.screens.system as screens_system  # noqa: E402
import src.screens.views as screens_views  # noqa: E402
import src.storage as storage  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _italian_module():
    """Ricarica i moduli con lingua italiana FORZATA (TASKO_LANG vince su
    config reale e locale di macchina): stringhe valutate all'import
    deterministiche ovunque. Ordine = dipendenze."""
    import importlib
    import os

    os.environ["TASKO_LANG"] = "it"
    lang.set_lang("it")
    for mod in (
        storage,
        screens_shared,
        screens_form,
        screens_views,
        screens_plan,
        screens_system,
        screens_menu,
        screens,
        commands_module,
        cli_module,
        app_module,
        main,
    ):
        importlib.reload(mod)
    lang.set_lang("it")
    yield
    lang.set_lang("it")
    os.environ.pop("TASKO_LANG", None)


def screen_texts(screen) -> str:
    """Testo di Static e Label, compatibile Textual 8.x (.content) e 3.x (.renderable)."""
    out = []
    seen = set()
    for w in list(screen.query("Static")) + list(screen.query("Label")):
        if id(w) in seen:
            continue
        seen.add(id(w))
        content = getattr(w, "content", None)
        if content is None:
            content = getattr(w, "renderable", "")
        out.append(str(content))
    return " ".join(out)


@pytest.fixture(autouse=True)
def tmp_files(tmp_path, monkeypatch):
    """AUTOUSE: redireziona ogni path su file temporanei (mai ~/.todo_* nei test)."""
    monkeypatch.setattr(storage, "DATA_FILE", tmp_path / "todo.json")
    monkeypatch.setattr(storage, "TEMPLATE_FILE", tmp_path / "templates.json")
    monkeypatch.setattr(storage, "POMODORO_FILE", tmp_path / "pomo.json")
    monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(storage, "ARCHIVE_FILE", tmp_path / "archive.json")
    monkeypatch.setattr(storage, "OUTLOOK_TOKEN_FILE", tmp_path / "outlook-token.json")
    monkeypatch.setattr(storage, "EXECUTIONS_FILE", tmp_path / "executions.json")
    monkeypatch.setattr(storage, "BACKUP_DIR", tmp_path / "backups")
    # Mirror su main (re-export di compatibilita' usati in qualche test).
    monkeypatch.setattr(main, "DATA_FILE", tmp_path / "todo.json")
    monkeypatch.setattr(main, "TEMPLATE_FILE", tmp_path / "templates.json")
    monkeypatch.setattr(main, "POMODORO_FILE", tmp_path / "pomo.json")
    monkeypatch.setattr(main, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(main, "ARCHIVE_FILE", tmp_path / "archive.json")
    monkeypatch.setattr(main, "EXECUTIONS_FILE", tmp_path / "executions.json")
    monkeypatch.setattr(main, "BACKUP_DIR", tmp_path / "backups")
    return tmp_path


@pytest.fixture()
def italian_lang():
    """Ripristina la lingua italiana dopo il test."""
    lang.set_lang("it")
    yield
    lang.set_lang("it")


def make_todo(title="T", todo_id=1, **kwargs):
    return models.TodoItem(title=title, todo_id=todo_id, **kwargs)


def make_app(todos):
    app = app_module.TodoApp()
    app.todos = list(todos)
    app.next_id = max((t.id or 0 for t in todos), default=0) + 1
    return app


def run(coro):
    """Esegue una coroutine con asyncio.run (helper comune ai test UI)."""
    return asyncio.run(coro)


async def wait_for(pilot, cond, tries: int = 40, delay: float | None = None):
    """Attende una condizione (runner CI lenti: pause fisse non bastano)."""
    for _ in range(tries):
        if delay is None:
            await pilot.pause()
        else:
            await pilot.pause(delay)
        if cond():
            return True
    return False
