"""Test persistenza: todos, template, config, pomodoro, archivio, backup."""

import json

import src.main as m
from tests.conftest import make_todo


def test_todos_roundtrip(tmp_files):
    todos = [
        m.TodoItem(title="A", todo_id=1, tags=["x"], project="lav"),
        m.TodoItem(title="B", parent_id=1, todo_id=2, pomodoros=2, stima_pomo=4),
    ]
    m._save_todos_plain(todos)
    back = m.load_todos()
    assert [t.title for t in back] == ["A", "B"]
    assert back[1].parent_id == 1 and back[1].stima_pomo == 4


def test_todos_file_corrotto(tmp_files):
    m.DATA_FILE.write_text("{{{rotto")
    assert m.load_todos() == []
    assert m.DATA_FILE.with_suffix(".corrotto.json").exists()


def test_templates_roundtrip_e_default(tmp_files):
    t = m.load_templates()
    assert "Viaggio" in t  # default italiani con lang it
    t["Mio"] = [{"title": "X", "priority": m.Priority.HIGH}]
    m.save_templates(t)
    back = m.load_templates()
    assert back["Mio"][0]["priority"] == m.Priority.HIGH


def test_config_roundtrip_e_fallback(tmp_files):
    m.save_config(
        {
            "theme": "textual-dark",
            "kanban_visible": False,
            "filter_state": "completati",
            "daily_goal": 7,
            "weekly_goal": 20,
            "pomo_daily_goal": 6,
            "lang": "en",
        }
    )
    cfg = m.load_config()
    assert cfg["theme"] == "textual-dark" and cfg["daily_goal"] == 7
    assert cfg["lang"] == "en"
    m.CONFIG_FILE.write_text("rotto{{{")
    assert m.load_config()["theme"] == "matrix"


def test_kanban_mode_roundtrip_e_legacy(tmp_files):
    m.save_config({"kanban_visible": True, "kanban_mode": "testo"})
    assert m.load_config()["kanban_mode"] == "testo"
    m.save_config({"kanban_visible": True, "kanban_mode": "bogus"})
    assert m.load_config()["kanban_mode"] == "grafico"
    m.CONFIG_FILE.write_text(json.dumps({"kanban_visible": False}))
    assert m.load_config()["kanban_mode"] == "nascosto"
    m.CONFIG_FILE.write_text(json.dumps({"kanban_visible": True}))
    assert m.load_config()["kanban_mode"] == "grafico"


def test_pomodoro_roundtrip_e_migrazione(tmp_files):
    m.save_pomodoro(
        {
            "default_minutes": 30,
            "short_minutes": 5,
            "long_minutes": 15,
            "long_every": 4,
            "cycle": 2,
            "session": {
                "task_id": 1,
                "phase": "short",
                "total_secs": 300,
                "end": None,
                "paused_secs": 120,
            },
        }
    )
    d = m.load_pomodoro()
    assert d["cycle"] == 2 and d["session"]["phase"] == "short"
    # file vecchio senza fase/ciclo
    m.POMODORO_FILE.write_text(
        json.dumps({"default_minutes": 30, "session": {"task_id": 1}})
    )
    d2 = m.load_pomodoro()
    assert d2["session"]["phase"] == "focus" and d2["cycle"] == 0


def test_archive_roundtrip(tmp_files):
    assert m.load_archive() == []
    m.save_archive([{"id": 1, "title": "A"}])
    assert m.load_archive() == [{"id": 1, "title": "A"}]


def test_backup_giro_completo(tmp_files):
    m.DATA_FILE.write_text(json.dumps([{"id": 1, "title": "A", "priority": "media"}]))
    p = m.create_backup()
    assert p.exists()
    info = m.snapshot_info(p)
    assert info["files"].get("todos") == 1
    m.DATA_FILE.write_text(json.dumps([{"id": 9, "title": "NUOVO"}]))
    m.restore_snapshot(p)
    assert json.loads(m.DATA_FILE.read_text())[0]["title"] == "A"


def test_backup_nomi_unici_e_concorrenti(tmp_files):
    """B4: backup ravvicinati non si sovrascrivono; sotto commit concorrenti
    ogni todos.json resta JSON valido."""
    import json as _json
    import threading
    import zipfile

    import src.main as m
    from src.store import TodoStore

    s = TodoStore.load()
    s.add(make_todo("A", todo_id=None))
    s.commit()
    p1 = m.create_backup()
    p2 = m.create_backup()
    assert p1 != p2 and p1.exists() and p2.exists()

    stop = threading.Event()

    def _churn():
        while not stop.is_set():
            st = TodoStore.load()
            st.add(make_todo("X", todo_id=None))
            try:
                st.commit()
            except OSError:
                pass

    th = threading.Thread(target=_churn)
    th.start()
    try:
        for _ in range(5):
            m.create_backup()
    finally:
        stop.set()
        th.join()
    for zp in m.list_snapshots():
        with zipfile.ZipFile(zp) as zf:
            if "todos.json" in zf.namelist():
                _json.loads(zf.read("todos.json"))  # non deve mai essere troncato


def test_restore_fallito_lascia_tutto_intatto(tmp_files, monkeypatch):
    """B5: errore a meta' restore -> file gia' scritti ripristinati, altri mai toccati."""
    import json as _json

    import src.main as m
    import src.storage as s

    m.DATA_FILE.write_text(_json.dumps([{"id": 1, "title": "VECCHIO"}]))
    m.ARCHIVE_FILE.write_text(_json.dumps([{"id": 1, "title": "ARC-VECCHIO"}]))
    snap = m.create_backup()
    prima_todos = m.DATA_FILE.read_bytes()
    prima_arc = m.ARCHIVE_FILE.read_bytes()

    calls = {"n": 0}
    reale = s._write_bytes_locked

    def _flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("crash simulato")
        return reale(path, data)

    monkeypatch.setattr(s, "_write_bytes_locked", _flaky)
    try:
        m.restore_snapshot(snap)
    except OSError:
        pass
    else:
        raise AssertionError("doveva fallire")
    assert m.DATA_FILE.read_bytes() == prima_todos
    assert m.ARCHIVE_FILE.read_bytes() == prima_arc


def test_restore_entry_non_json_rifiutata(tmp_files):
    """B5: zip valido con entry non JSON -> OSError prima di toccare il disco."""
    import json as _json
    import zipfile

    import src.main as m

    m.DATA_FILE.write_text(_json.dumps([{"id": 1, "title": "VECCHIO"}]))
    bad = m.BACKUP_DIR / "tasko_20990101_000000.zip"
    m.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("todos.json", b"binario \xff non json")
        zf.writestr("manifest.json", "{}")
    try:
        m.restore_snapshot(bad)
    except OSError:
        pass
    else:
        raise AssertionError("doveva fallire")
    assert _json.loads(m.DATA_FILE.read_text())[0]["title"] == "VECCHIO"


def test_backup_corrotto_rifiutato(tmp_files):
    bad = m.BACKUP_DIR / "tasko_20990101_000000.zip"
    m.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"not a zip")
    try:
        m.restore_snapshot(bad)
    except OSError:
        pass
    else:
        raise AssertionError("doveva fallire")


def test_backup_retention(tmp_files, monkeypatch):
    from datetime import datetime as _dt

    import src.storage as s

    m.DATA_FILE.write_text("[]")

    class _FakeDT(_dt):
        _calls = 0

        @classmethod
        def now(cls, tz=None):
            cls._calls += 1
            return _dt(2099, 1, 1, 0, 0, cls._calls)

    monkeypatch.setattr(s, "datetime", _FakeDT)
    for _ in range(3):
        m.create_backup()
    m.prune_snapshots(keep=2)
    assert len(m.list_snapshots()) == 2


def test_config_roundtrip_tutte_le_chiavi(tmp_files):
    """Guardrail whitelist: ogni chiave DEFAULT_CONFIG sopravvive a save/load."""
    import src.storage as s

    cfg = s.load_config()
    for key in s.DEFAULT_CONFIG:
        assert key in cfg, key
    s.save_config(cfg)
    back = s.load_config()
    for key in s.DEFAULT_CONFIG:
        assert key in back, key
    # tag/progetto/ricerca restano volatili: mai persistiti in config
    raw = json.loads(s.CONFIG_FILE.read_text(encoding="utf-8"))
    assert "filter_tag" not in raw and "filter_project" not in raw
    assert "filter_search" not in raw


def test_smart_lists_validazione_e_roundtrip(tmp_files):
    import src.storage as s

    s.save_config(
        {
            **s.load_config(),
            "smart_lists": [
                {"name": "Lavoro", "state": "attivo", "tag": " Ufficio "},
                {"name": "lavoro"},  # duplicato case-insensitive -> scartato
                {"name": ""},  # senza nome -> scartato
                {"name": "Bogus", "state": "domani"},  # stato ignoto -> wildcard
                "non-dict",  # scartata
            ],
        }
    )
    back = s.load_config()["smart_lists"]
    assert [(e["name"], e["tag"], e["state"]) for e in back] == [
        ("Lavoro", "ufficio", "attivo"),
        ("Bogus", None, None),
    ]
    # file vecchio senza chiave -> []
    s.CONFIG_FILE.write_text(json.dumps({"theme": "matrix"}))
    assert s.load_config()["smart_lists"] == []


def test_actual_retrocompat_e_roundtrip(tmp_files):
    vecchio = {"id": 1, "title": "A", "priority": "media"}
    t = m.TodoItem.from_dict(vecchio)
    assert (t.actual_pomo, t.actual_minutes) == (0, 0)
    t.actual_pomo = 3
    t.actual_minutes = 75
    back = m.TodoItem.from_dict(t.to_dict())
    assert (back.actual_pomo, back.actual_minutes) == (3, 75)
    brutto = {"id": 2, "title": "B", "actual_pomo": -4, "actual_minutes": "xx"}
    t2 = m.TodoItem.from_dict(brutto)
    assert (t2.actual_pomo, t2.actual_minutes) == (0, 0)
