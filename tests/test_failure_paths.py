"""Test percorsi di failure: corrotto, lock, snapshot parziali, disco corrotto in merge."""

import json
import zipfile

import pytest

import src.main as m
from src import crypto as crypto_mod
from src.store import TodoStore
from tests.conftest import make_todo


@pytest.fixture()
def unlocked():
    crypto_mod.set_key(None)
    yield
    crypto_mod.set_key(None)


def test_store_su_file_corrotto(tmp_files):
    m.DATA_FILE.write_text("{{{rotto")
    prima = m.DATA_FILE.read_bytes()
    s = TodoStore.load()
    assert s.all() == []
    assert m.DATA_FILE.with_suffix(".corrotto.json").exists()
    # fail-closed: commit su disco corrotto solleva, primary intatto
    import src.storage as st

    s.add(make_todo("Nuovo", todo_id=None))
    with pytest.raises(st.StorageUnreadable):
        s.commit()
    assert m.DATA_FILE.read_bytes() == prima


def test_envelope_bloccato_niente_backup(tmp_files, unlocked):
    crypto_mod.set_key(crypto_mod.encode_password("segreta12"))
    m._save_todos_plain([make_todo("Segreto", todo_id=1)])
    crypto_mod.set_key(None)
    assert m.load_todos() == []
    assert not m.DATA_FILE.with_suffix(".corrotto.json").exists()


def test_envelope_chiave_errata_niente_backup(tmp_files, unlocked):
    # Decisione Phase 1: decrypt failure non e' evidenza di corruzione.
    crypto_mod.set_key(crypto_mod.encode_password("segreta12"))
    m._save_todos_plain([make_todo("Segreto", todo_id=1)])
    crypto_mod.set_key(crypto_mod.encode_password("sbagliata"))
    assert m.load_todos() == []
    assert not m.DATA_FILE.with_suffix(".corrotto.json").exists()


def _zip_snapshot(path, entries: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_restore_fa_backup_preventivo(tmp_files):
    m._save_todos_plain([make_todo("Attuale", todo_id=1)])
    zpath = m.BACKUP_DIR / "tasko_20990101_000000.zip"
    _zip_snapshot(
        zpath,
        {
            "todos.json": json.dumps([{"id": 9, "title": "Ripristinato"}]),
            "manifest.json": json.dumps({"app": "tasko", "created": "x", "files": {}}),
        },
    )
    m.restore_snapshot(zpath)
    assert [t.title for t in m.load_todos()] == ["Ripristinato"]
    # lo stato precedente e' conservato in uno snapshot di rollback
    assert len(m.list_snapshots()) == 2
    rollback = [p for p in m.list_snapshots() if p.name != "tasko_20990101_000000.zip"]
    assert len(rollback) == 1
    with zipfile.ZipFile(rollback[0]) as zf:
        assert "Attuale" in zf.read("todos.json").decode("utf-8")


def test_snapshot_parziale_ripristina_solo_presenti(tmp_files):
    m._save_todos_plain([make_todo("A", todo_id=1)])
    m.save_config({**m.load_config(), "daily_goal": 7})
    zpath = m.BACKUP_DIR / "tasko_20990101_000000.zip"
    _zip_snapshot(
        zpath,
        {
            "todos.json": json.dumps(
                [{"id": 9, "title": "VECCHIO", "priority": "media"}]
            ),
            "manifest.json": json.dumps({"app": "tasko", "created": "x", "files": {}}),
        },
    )
    m.restore_snapshot(zpath)
    assert [t.title for t in m.load_todos()] == ["VECCHIO"]
    assert m.load_config()["daily_goal"] == 7  # config intatta


def test_snapshot_con_todos_corrotto(tmp_files):
    # B5: entry non JSON rifiutata PRIMA di scrivere: OSError, disco intatto.
    m._save_todos_plain([make_todo("Attuale", todo_id=1)])
    zpath = m.BACKUP_DIR / "tasko_20990101_000000.zip"
    _zip_snapshot(
        zpath,
        {
            "todos.json": "rotto{{{",
            "manifest.json": json.dumps({"app": "tasko", "created": "x", "files": {}}),
        },
    )
    try:
        m.restore_snapshot(zpath)
    except OSError:
        pass
    else:
        raise AssertionError("doveva fallire")
    assert [t.title for t in m.load_todos()] == ["Attuale"]


def test_merge_con_disco_corrotto(tmp_files):
    import src.storage as st

    m.DATA_FILE.write_text("{{{")
    prima = m.DATA_FILE.read_bytes()
    s = TodoStore([make_todo("Mio", todo_id=None)])
    with pytest.raises(st.StorageUnreadable):
        s.commit()  # disco corrotto: mai trattato come vuoto
    assert m.DATA_FILE.read_bytes() == prima


def test_voci_non_dict_ignorate(tmp_files):
    m.DATA_FILE.write_text(
        json.dumps([{"id": 1, "title": "Ok", "priority": "media"}, 42, "xx", None])
    )
    assert [t.title for t in m.load_todos()] == ["Ok"]


def test_contenuto_non_lista(tmp_files):
    m.DATA_FILE.write_text(json.dumps({"id": 1}))
    assert m.load_todos() == []
