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


def test_export_import_roundtrip_identita(tmp_files, monkeypatch):
    """C2: source/external_id sopravvivono all'export: reimport = skip."""
    import src.app as app_module
    from tests.conftest import run

    async def t():
        app = make_app([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            n, _ = csv_mod.import_csv_file(
                _write_external(tmp_files / "in.csv"), app.store
            )
            assert n == 1
            app.action_export_csv()
            await pilot.pause()

    monkeypatch.setattr(app_module, "_home", lambda: tmp_files)
    run(t())
    exported = sorted(
        (tmp_files / "CarpeDiem_screenshots").glob("carpediem_export_*.csv")
    )
    assert len(exported) == 1
    header = exported[0].read_text(encoding="utf-8").splitlines()[0]
    assert "source" in header.split(",") and "external_id" in header.split(",")
    storage.DATA_FILE.unlink(missing_ok=True)
    store2 = TodoStore.load()
    n2, sk2 = csv_mod.import_csv_file(str(exported[0]), store2)
    assert (n2, sk2) == (1, 0)
    by = store2.by_external("todoist", "x1")
    assert by is not None
    n3, sk3 = csv_mod.import_csv_file(str(exported[0]), store2)
    assert (n3, sk3) == (0, 1)


def _write_external(path):
    path.write_text(
        "id,titolo,source,external_id\n7,Sette,todoist,x1\n", encoding="utf-8"
    )
    return str(path)
