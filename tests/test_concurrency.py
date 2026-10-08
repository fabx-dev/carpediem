"""Test concorrenza CLI-TUI: lock, merge three-way, nessuna perdita di dati."""

import threading

import pytest

import carpediem.cli as cli_mod
import carpediem.main as m
import carpediem.storage as storage_mod
from carpediem.store import TodoStore
from tests.conftest import make_todo


def _titles():
    return sorted(t.title for t in TodoStore.load().all())


def test_interleaved_senza_perdite(tmp_files):
    tui = TodoStore.load()
    cli = TodoStore.load()
    tui.add(make_todo("TUI-1", todo_id=None))
    tui.commit()
    cli.add(make_todo("CLI-1", todo_id=None))
    cli.commit()
    assert _titles() == ["CLI-1", "TUI-1"]
    # modifiche incrociate su item diversi
    tui2 = TodoStore.load()
    cli2 = TodoStore.load()
    tui2.by_id(1).title = "TUI-1-mod"
    tui2.commit()
    cli2.by_id(2).notes = "nota cli"
    cli2.commit()
    back = {t.id: t for t in TodoStore.load().all()}
    assert back[1].title == "TUI-1-mod" and back[2].notes == "nota cli"


def test_stesso_id_nuovo_da_entrambi(tmp_files):
    a = TodoStore.load()
    b = TodoStore.load()
    a.add(make_todo("A", todo_id=None))
    b.add(make_todo("B", todo_id=None))
    a.commit()
    b.commit()  # il vecchio codice avrebbe perso "A"
    back = TodoStore.load().all()
    assert sorted(t.title for t in back) == ["A", "B"]
    assert len({t.id for t in back}) == 2


def test_merge_collisione_ids_puro():
    d = lambda i, t: {"id": i, "title": t}  # noqa: E731
    merged = storage_mod.merge_todo_dicts([], [d(5, "DISK")], [d(5, "OURS")])
    by_id = {x["id"]: x["title"] for x in merged}
    assert by_id[5] == "DISK" and "OURS" in by_id.values() and len(merged) == 2


def test_merge_collisione_figlio_segue_padre_nostro():
    """B3: figlio creato dal nostro lato dopo collisione id segue il padre
    riassegnato, non quello del disco che ha tenuto l'id."""
    disk = [{"id": 1, "title": "DISK-P"}]
    ours = [
        {"id": 1, "title": "OURS-P"},
        {"id": 2, "title": "OURS-C", "parent_id": 1},
    ]
    merged = storage_mod.merge_todo_dicts([], disk, ours)
    by_title = {x["title"]: x for x in merged}
    new_parent = by_title["OURS-P"]["id"]
    assert new_parent != 1
    assert by_title["OURS-C"]["parent_id"] == new_parent
    assert by_title["DISK-P"]["id"] == 1
    assert ours[1]["parent_id"] == 1  # input non mutato


def test_cancellato_da_uno_modificato_dall_altro(tmp_files):
    s0 = TodoStore([make_todo("X", todo_id=1)])
    s0.commit()
    editor = TodoStore.load()
    deleter = TodoStore.load()
    editor.by_id(1).title = "X-mod"
    editor.commit()
    deleter.remove_ids({1})
    deleter.commit()
    assert [t.title for t in TodoStore.load().all()] == ["X-mod"]


def test_modificato_da_entrambi_vince_chi_salva(tmp_files):
    s0 = TodoStore([make_todo("X", todo_id=1)])
    s0.commit()
    a = TodoStore.load()
    b = TodoStore.load()
    a.by_id(1).title = "A-last"
    a.commit()
    b.by_id(1).title = "B-last"
    b.commit()
    assert [t.title for t in TodoStore.load().all()] == ["B-last"]


def test_cancellazione_da_altro_processo_non_viene_risuscitata(tmp_files):
    s0 = TodoStore([make_todo("X", todo_id=1)])
    s0.commit()
    tui = TodoStore.load()
    deleter = TodoStore.load()
    deleter.remove_ids({1})
    deleter.commit()
    tui.add(make_todo("Nuovo", todo_id=None))
    tui.commit()
    assert [t.title for t in TodoStore.load().all()] == ["Nuovo"]


def test_item_senza_id_non_duplicati_dal_merge(tmp_files):
    import json

    import carpediem.main as m

    m.DATA_FILE.write_text(json.dumps([{"title": "L1"}, {"title": "L2"}]))
    s = TodoStore.load()
    s.commit()
    assert [t.title for t in TodoStore.load().all()] == ["L1", "L2"]


def test_cancellato_ma_modificato_da_noi_vince_la_modifica(tmp_files):
    s0 = TodoStore([make_todo("X", todo_id=1)])
    s0.commit()
    tui = TodoStore.load()
    deleter = TodoStore.load()
    deleter.remove_ids({1})
    deleter.commit()
    tui.by_id(1).title = "X-mod"
    tui.commit()
    assert [t.title for t in TodoStore.load().all()] == ["X-mod"]


def test_modifica_esterna_compare_in_memoria_e_non_viene_clobberata(tmp_files):
    s0 = TodoStore([make_todo("X", todo_id=1)])
    s0.commit()
    tui = TodoStore.load()
    cli = TodoStore.load()
    cli.by_id(1).title = "X-da-CLI"
    cli.commit()
    tui.commit()  # commit innocuo: la memoria deve riflettere il merged
    assert tui.by_id(1).title == "X-da-CLI"
    tui.by_id(1).notes = "nota tui"
    tui.commit()
    back = TodoStore.load().by_id(1)
    assert back.title == "X-da-CLI" and back.notes == "nota tui"


def test_lock_timeout_e_rilascio(tmp_files):
    with storage_mod._locked(m.DATA_FILE, timeout=5):
        with pytest.raises(storage_mod.StorageLocked):
            with storage_mod._locked(m.DATA_FILE, timeout=0.2):
                pass
    with storage_mod._locked(m.DATA_FILE, timeout=0.2):
        pass


def test_lock_contesa_tra_thread(tmp_files):
    """B7: holder in un altro thread -> StorageLocked, poi acquisibile al rilascio."""
    import threading

    libero = threading.Event()
    preso = threading.Event()

    def _holder():
        with storage_mod._locked(m.DATA_FILE, timeout=5):
            preso.set()
            assert libero.wait(timeout=5)

    th = threading.Thread(target=_holder)
    th.start()
    try:
        assert preso.wait(timeout=5)
        with pytest.raises(storage_mod.StorageLocked):
            with storage_mod._locked(m.DATA_FILE, timeout=0.15):
                pass
    finally:
        libero.set()
        th.join()
    with storage_mod._locked(m.DATA_FILE, timeout=2):
        pass
    # il lock usa solo il sidecar: acquisirlo non crea mai il file dati
    assert not m.DATA_FILE.exists()


def test_thread_senza_perdite(tmp_files):
    m._save_todos_plain([])
    errors = []

    def worker(n):
        try:
            for i in range(5):
                s = TodoStore.load()
                s.add(make_todo(f"T{n}-{i}", todo_id=None))
                s.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors
    back = TodoStore.load().all()
    assert len(back) == 20 and len({t.id for t in back}) == 20


def test_cli_e_tui_interleaved(tmp_files):
    tui = TodoStore.load()
    assert cli_mod._cli_main(["add", "Da CLI"]) == 0
    tui.add(make_todo("Da TUI", todo_id=None))
    tui.commit()
    assert cli_mod._cli_main(["done", "1"]) == 0
    back = {t.title: t for t in TodoStore.load().all()}
    assert set(back) == {"Da CLI", "Da TUI"} and back["Da CLI"].done
