"""Paths standard per piattaforma + override HOME (packaging milestone).

I test ripristinano le funzioni canoniche originali (la fixture autouse
`tmp_files` le sostituisce con lambda su tmp): i riferimenti `_ORIG_*`
catturati all'import sono anteriori al monkeypatch per-test.
"""

import sys

import pytest

import carpediem.storage as st

_ORIG = {
    name: getattr(st, name)
    for name in (
        "config_dir",
        "data_dir",
        "base_dir",
        "backup_dir",
        "config_file",
        "todos_file",
        "templates_file",
        "pomodoro_file",
        "archive_file",
        "executions_file",
        "outlook_token_file",
        "home_override",
    )
}


@pytest.fixture()
def real_paths(monkeypatch):
    """Ripristina le funzioni path originali + env pulito (HOME isolata)."""
    for name, fn in _ORIG.items():
        monkeypatch.setattr(st, name, fn)
    for var in (
        "CARPEDIEM_HOME",
        "TASKO_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "APPDATA",
        "LOCALAPPDATA",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def _home(monkeypatch, tmp_path):
    # Path.home()/expanduser usano HOME su POSIX, USERPROFILE su Windows.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    return tmp_path / "home"


def test_linux_default(monkeypatch, tmp_path, real_paths):
    home = _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    assert st.config_dir() == home / ".config" / "carpediem"
    assert st.data_dir() == home / ".local" / "share" / "carpediem"
    assert st.backup_dir() == home / ".local" / "share" / "carpediem" / "backups"
    assert st.todos_file().name == "todos.json"
    assert st.config_file().name == "config.json"


def test_linux_xdg(monkeypatch, tmp_path, real_paths):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xc"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xd"))
    assert st.config_dir() == tmp_path / "xc" / "carpediem"
    assert st.data_dir() == tmp_path / "xd" / "carpediem"


def test_macos(monkeypatch, tmp_path, real_paths):
    home = _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    base = home / "Library" / "Application Support" / "CarpeDiem"
    assert st.config_dir() == base
    assert st.data_dir() == base
    assert st.backup_dir() == base / "backups"


def test_windows(monkeypatch, tmp_path, real_paths):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roam"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "loc"))
    assert st.config_dir() == tmp_path / "roam" / "CarpeDiem"
    assert st.data_dir() == tmp_path / "loc" / "CarpeDiem"
    assert st.backup_dir() == tmp_path / "loc" / "CarpeDiem" / "backups"


def test_windows_fallback_appdata(monkeypatch, tmp_path, real_paths):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roam"))
    assert st.data_dir() == tmp_path / "roam" / "CarpeDiem"


def test_carpediem_home_vince(monkeypatch, tmp_path, real_paths):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    new = tmp_path / "new"
    old = tmp_path / "old"
    monkeypatch.setenv("CARPEDIEM_HOME", str(new))
    monkeypatch.setenv("TASKO_HOME", str(old))
    assert st.home_override() == new
    assert st.data_dir() == new
    assert st.config_dir() == new


def test_tasko_home_legacy_funziona(monkeypatch, tmp_path, real_paths):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    old = tmp_path / "old"
    monkeypatch.setenv("TASKO_HOME", str(old))
    assert st.home_override() == old
    assert st.data_dir() == old
    assert st.todos_file() == old / "todos.json"


def test_home_vuota_come_unset(monkeypatch, tmp_path, real_paths):
    home = _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("CARPEDIEM_HOME", "   ")
    monkeypatch.setenv("TASKO_HOME", "")
    assert st.home_override() is None
    assert st.data_dir() == home / ".local" / "share" / "carpediem"


def test_home_expanduser(monkeypatch, tmp_path, real_paths):
    home = _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("CARPEDIEM_HOME", "~/migrati")
    assert st.home_override() == home / "migrati"


def test_nomi_file_nuovi(monkeypatch, tmp_path, real_paths):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("CARPEDIEM_HOME", str(tmp_path / "n"))
    names = [
        st.todos_file().name,
        st.config_file().name,
        st.templates_file().name,
        st.pomodoro_file().name,
        st.archive_file().name,
        st.executions_file().name,
        st.outlook_token_file().name,
    ]
    assert names == [
        "todos.json",
        "config.json",
        "templates.json",
        "pomodoro.json",
        "archive.json",
        "executions.json",
        "outlook-token.json",
    ]
    # Niente dotfile `.todo_*`, niente `Tasko`/`tasko_` nei nuovi nomi
    # ("todos.json" contiene "todo" come parola: il divieto riguarda i
    # nomi legacy puntati e il brand storico, non la parola comune).
    for n in names:
        assert not n.startswith(".todo")
        assert "tasko" not in n.lower()
        assert "Tasko" not in n
    assert st.backup_dir().name == "backups"


def test_fresh_non_crea_nulla(monkeypatch, tmp_path, real_paths):
    """I lettori non creano directory: fresh install resta pulita."""
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    st.load_config()
    st.load_todos()
    assert not (tmp_path / "home" / ".config").exists()
    assert not (tmp_path / "home" / ".local").exists()
