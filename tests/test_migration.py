"""Migrazione legacy -> nuovi path: policy, idempotenza, fail-closed, HOME/LANG.

Come in test_paths, `_ORIG` cattura le funzioni canoniche prima del
monkeypatch per-test della fixture autouse `tmp_files`.
"""

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import carpediem.storage as st
from carpediem import crypto as crypto_mod

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
        "_write_atomic",
        "_write_bytes_locked",
    )
}

TASK = {
    "id": 1,
    "title": "Prova",
    "state": "attivo",
    "priority": "media",
}


def _use_dirs(monkeypatch, legacy, new):
    """Target nuovi in `new`, legacy cercato in `legacy` (via TASKO_HOME)."""
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
    ):
        monkeypatch.setattr(st, name, _ORIG[name])
    monkeypatch.delenv("CARPEDIEM_HOME", raising=False)
    monkeypatch.setenv("TASKO_HOME", str(legacy))
    # I target reali punterebbero a `legacy`: redirezionarli su `new`.
    monkeypatch.setattr(st, "config_dir", lambda: new)
    monkeypatch.setattr(st, "data_dir", lambda: new)
    monkeypatch.setattr(st, "base_dir", lambda: new)
    monkeypatch.setattr(st, "backup_dir", lambda: new / "backups")
    monkeypatch.setattr(st, "config_file", lambda: new / "config.json")
    monkeypatch.setattr(st, "todos_file", lambda: new / "todos.json")
    monkeypatch.setattr(st, "templates_file", lambda: new / "templates.json")
    monkeypatch.setattr(st, "pomodoro_file", lambda: new / "pomodoro.json")
    monkeypatch.setattr(st, "archive_file", lambda: new / "archive.json")
    monkeypatch.setattr(st, "executions_file", lambda: new / "executions.json")
    monkeypatch.setattr(st, "outlook_token_file", lambda: new / "outlook-token.json")
    monkeypatch.setattr(st, "home_override", lambda: new)


def _hashes(path):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def test_legacy_verso_nuovo(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    (legacy / ".todo_app.json").write_text(json.dumps([TASK]), encoding="utf-8")
    (legacy / ".todo_config.json").write_text(
        json.dumps({"lang": "it"}), encoding="utf-8"
    )
    _use_dirs(monkeypatch, legacy, new)
    report = st.migrate_legacy()
    assert "todos" in report["migrated"]
    assert "config" in report["migrated"]
    assert json.loads((new / "todos.json").read_text(encoding="utf-8")) == [TASK]
    # Legacy intatto.
    assert json.loads((legacy / ".todo_app.json").read_text(encoding="utf-8")) == [TASK]


def test_fresh_install(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    _use_dirs(monkeypatch, legacy, new)
    report = st.migrate_legacy()
    assert report["migrated"] == []
    assert report["backups"] == []
    assert not new.exists()


def test_target_esistente_non_sovrascritto(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    new.mkdir()
    (legacy / ".todo_app.json").write_text(json.dumps([TASK]), encoding="utf-8")
    (new / "todos.json").write_text(json.dumps([]), encoding="utf-8")
    _use_dirs(monkeypatch, legacy, new)
    report = st.migrate_legacy()
    assert "todos" in report["skipped_target_exists"]
    assert json.loads((new / "todos.json").read_text(encoding="utf-8")) == []


def test_idempotenza_hash(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    (legacy / ".todo_app.json").write_text(json.dumps([TASK]), encoding="utf-8")
    (legacy / ".todo_executions.json").write_text(
        json.dumps(
            [
                {
                    "task_id": 1,
                    "estimate_pomo": 2,
                    "actual_pomo": 2,
                    "ended_at": "2026-01-01 10:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    _use_dirs(monkeypatch, legacy, new)
    first = st.migrate_legacy()
    assert "todos" in first["migrated"]
    assert "executions" in first["migrated"]
    h1 = _hashes(new)
    second = st.migrate_legacy()
    assert second["migrated"] == []
    assert _hashes(new) == h1


def test_errore_write_nessuna_perdita(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    raw = json.dumps([TASK])
    (legacy / ".todo_app.json").write_text(raw, encoding="utf-8")
    _use_dirs(monkeypatch, legacy, new)

    def _boom(*a, **k):
        raise OSError("disco rotto")

    monkeypatch.setattr(st, "_write_atomic", _boom)
    report = st.migrate_legacy()
    assert any("todos" in e for e in report["skipped_error"])
    assert not (new / "todos.json").exists()
    assert (legacy / ".todo_app.json").read_text(encoding="utf-8") == raw


def test_file_cifrato_byte_identical(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    crypto_mod.set_key(crypto_mod.encode_password("segreta123"))
    try:
        enc = crypto_mod.protect_text(json.dumps([TASK]))
    finally:
        crypto_mod.set_key(None)
    (legacy / ".todo_app.json").write_text(enc, encoding="utf-8")
    _use_dirs(monkeypatch, legacy, new)
    report = st.migrate_legacy()
    assert "todos" in report["migrated"]
    assert (new / "todos.json").read_text(encoding="utf-8") == enc
    # Senza chiave: stesso fail-closed di prima (vuoto, niente backup .corrotto).
    assert st.load_todos() == []
    assert not list(new.glob("*.corrotto.json"))
    # Con chiave corretta: leggibile.
    crypto_mod.set_key(crypto_mod.encode_password("segreta123"))
    try:
        assert [t.title for t in st.load_todos()] == ["Prova"]
    finally:
        crypto_mod.set_key(None)


def test_legacy_corrotto_ignorato(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    (legacy / ".todo_app.json").write_text("non json {{{", encoding="utf-8")
    _use_dirs(monkeypatch, legacy, new)
    report = st.migrate_legacy()
    assert any("todos" in e for e in report["skipped_invalid"])
    assert not (new / "todos.json").exists()
    assert (legacy / ".todo_app.json").read_text(encoding="utf-8") == "non json {{{"


def test_backup_legacy_copiati_e_ripristinabili(tmp_path, monkeypatch):
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    zdir = legacy / "Tasko_backups"
    zdir.mkdir(parents=True)
    zpath = zdir / "tasko_20200101_000000_000000.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("todos.json", json.dumps([TASK]))
        zf.writestr("manifest.json", json.dumps({"app": "tasko"}))
    _use_dirs(monkeypatch, legacy, new)
    report = st.migrate_legacy()
    assert zpath.name in report["backups"]
    dest = new / "backups" / zpath.name
    assert dest.read_bytes() == zpath.read_bytes()
    # Manifest storico intatto e restore funzionante dal migrato.
    with zipfile.ZipFile(dest) as zf:
        assert json.loads(zf.read("manifest.json"))["app"] == "tasko"
    st.restore_snapshot(dest)
    assert [t.title for t in st.load_todos()] == ["Prova"]


def test_nessun_nuovo_path_legacy(tmp_path, monkeypatch):
    """Dopo fresh + scritture reali, nessun nome `.todo_*`/`*tasko*`/`Tasko*`."""
    legacy, new = tmp_path / "legacy", tmp_path / "new"
    legacy.mkdir()
    _use_dirs(monkeypatch, legacy, new)
    st.migrate_legacy()
    from carpediem.models import TodoItem

    st._save_todos_plain([TodoItem(title="A", todo_id=1)])
    st.save_config(st.load_config())
    out = st.create_backup()
    assert out.name.startswith("carpediem_")
    for p in list(new.rglob("*")) + list((new / "backups").rglob("*")):
        assert not p.name.startswith(".todo"), p
        assert "tasko" not in p.name.lower(), p
        assert "Tasko" not in p.name, p


def test_carpediem_home_precede_tasko_home(tmp_path, monkeypatch):
    for name in _ORIG:
        if name not in ("_write_atomic", "_write_bytes_locked"):
            monkeypatch.setattr(st, name, _ORIG[name])
    monkeypatch.setenv("CARPEDIEM_HOME", str(tmp_path / "new"))
    monkeypatch.setenv("TASKO_HOME", str(tmp_path / "old"))
    assert st.home_override() == tmp_path / "new"
    assert st.data_dir() == tmp_path / "new"


def test_tasko_home_legacy_compatibile(tmp_path, monkeypatch):
    for name in _ORIG:
        if name not in ("_write_atomic", "_write_bytes_locked"):
            monkeypatch.setattr(st, name, _ORIG[name])
    monkeypatch.delenv("CARPEDIEM_HOME", raising=False)
    monkeypatch.setenv("TASKO_HOME", str(tmp_path / "old"))
    assert st.home_override() == tmp_path / "old"
    assert st.todos_file() == tmp_path / "old" / "todos.json"


def test_carpediem_home_stessa_dir_legacy(tmp_path, monkeypatch):
    """Var rinominata, stessa dir: i dotfile legacy migrano dentro la dir."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".todo_app.json").write_text(json.dumps([TASK]), encoding="utf-8")
    for name in _ORIG:
        if name not in ("_write_atomic", "_write_bytes_locked"):
            monkeypatch.setattr(st, name, _ORIG[name])
    monkeypatch.setenv("CARPEDIEM_HOME", str(home))
    monkeypatch.delenv("TASKO_HOME", raising=False)
    report = st.migrate_legacy()
    assert "todos" in report["migrated"]
    assert json.loads((home / "todos.json").read_text(encoding="utf-8")) == [TASK]


def test_override_non_tocca_home_reale(tmp_path, monkeypatch):
    """Con override attivo la home reale non viene mai letta per la migrazione."""
    for name in _ORIG:
        if name not in ("_write_atomic", "_write_bytes_locked"):
            monkeypatch.setattr(st, name, _ORIG[name])
    monkeypatch.setenv("CARPEDIEM_HOME", str(tmp_path / "new"))
    monkeypatch.delenv("TASKO_HOME", raising=False)
    assert st._legacy_candidate_bases() == [tmp_path / "new"]


def test_lang_precedenza(tmp_path, monkeypatch):
    import carpediem.main as main_mod

    monkeypatch.delenv("CARPEDIEM_HOME", raising=False)
    monkeypatch.delenv("TASKO_HOME", raising=False)
    try:
        monkeypatch.setenv("CARPEDIEM_LANG", "en")
        monkeypatch.setenv("TASKO_LANG", "it")
        assert main_mod._apply_startup_lang() == "en"
        monkeypatch.delenv("CARPEDIEM_LANG", raising=False)
        assert main_mod._apply_startup_lang() == "it"
    finally:
        monkeypatch.delenv("CARPEDIEM_LANG", raising=False)
        monkeypatch.delenv("TASKO_LANG", raising=False)
        main_mod._apply_startup_lang()


def test_tasko_lang_legacy(tmp_path, monkeypatch):
    import carpediem.main as main_mod

    monkeypatch.delenv("CARPEDIEM_LANG", raising=False)
    monkeypatch.delenv("TASKO_HOME", raising=False)
    monkeypatch.delenv("CARPEDIEM_HOME", raising=False)
    try:
        monkeypatch.setenv("TASKO_LANG", "it")
        assert main_mod._apply_startup_lang() == "it"
    finally:
        monkeypatch.delenv("TASKO_LANG", raising=False)
        main_mod._apply_startup_lang()


def test_cli_subprocess_migra(tmp_path):
    """Wiring: `python -m carpediem.main` migra prima di operare."""
    root = Path(__file__).resolve().parent.parent
    home = tmp_path / "home"
    home.mkdir()
    (home / ".todo_app.json").write_text(json.dumps([TASK]), encoding="utf-8")
    env = dict(
        os.environ,
        CARPEDIEM_HOME=str(home),
        PYTHONPATH=str(root / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    # TASKO_* fuori per provare il solo nuovo nome.
    env.pop("TASKO_HOME", None)
    env.pop("TASKO_LANG", None)
    env.pop("CARPEDIEM_LANG", None)
    r = subprocess.run(
        [sys.executable, "-m", "carpediem.main", "list", "--porcelain"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert (home / "todos.json").exists()
    assert "Prova" in r.stdout
