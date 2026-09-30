"""Equivalenza E4: src/import_csv == metodo originale di TodoApp."""

import src.import_csv as csv_mod
import src.storage as storage
from src.store import TodoStore
from tests.conftest import make_app

CSV = """id,title,priority,due,project,tags,note,stima_pomo,padre
1,Primo,alta,2026-10-01,work,"a;b",nota 1,2,
2,Secondo,bassa,,,,,,
3,Figlio,media,2026-10-02,,,nota 3,1,1
"""


def _write(path):
    path.write_text(CSV, encoding="utf-8")
    return str(path)


def _snapshot(store):
    out = []
    for t in sorted(store.all(), key=lambda x: x.id or 0):
        d = t.to_dict()
        d.pop("id", None)
        d.pop("created", None)
        out.append(d)
    return out


def test_equivalente_su_stessi_input(tmp_path):
    path = _write(tmp_path / "imp.csv")

    storage.DATA_FILE.unlink(missing_ok=True)
    store_mod = TodoStore.load()
    n_mod, sk_mod = csv_mod.import_csv_file(path, store_mod)
    snap_mod = _snapshot(store_mod)

    storage.DATA_FILE.unlink(missing_ok=True)
    app = make_app([])
    app.store = TodoStore.load()
    n_app, sk_app = app._import_csv_file(path)
    snap_app = _snapshot(app.store)

    assert (n_mod, sk_mod) == (n_app, sk_app) == (3, 0)
    assert snap_mod == snap_app


def test_idempotenza_identica(tmp_path):
    path = _write(tmp_path / "imp.csv")
    storage.DATA_FILE.unlink(missing_ok=True)
    store = TodoStore.load()
    assert csv_mod.import_csv_file(path, store) == (3, 0)
    assert csv_mod.import_csv_file(path, store) == (0, 3)
