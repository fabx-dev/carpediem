"""Storage/concurrency hardening (P1 §9): casi reali senza toccare il motore."""

import threading

import carpediem.storage as m
from carpediem.store import TodoStore
from tests.conftest import make_todo


def test_concurrent_writers_entrambi_sopravvivono(tmp_files):
    a = TodoStore.load()
    b = TodoStore.load()
    a.add(make_todo("A", todo_id=None))
    b.add(make_todo("B", todo_id=None))
    t1 = threading.Thread(target=a.commit)
    t2 = threading.Thread(target=b.commit)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    titles = sorted(t.title for t in TodoStore.load().all())
    assert titles == ["A", "B"]


def test_conflicting_changes_last_saver_wins(tmp_files):
    seed = TodoStore.load()
    seed.add(make_todo("base", todo_id=None))
    seed.commit()
    a = TodoStore.load()
    b = TodoStore.load()
    a.by_id(1).title = "primo"
    b.by_id(1).title = "secondo"
    a.commit()
    b.commit()  # chi salva per ultimo vince (semantica documentata)
    assert TodoStore.load().by_id(1).title == "secondo"


def test_corrupted_json_comportamento_sicuro(tmp_files):
    m.DATA_FILE.write_text("{ non json", encoding="utf-8")
    assert TodoStore.load().all() == []
    assert m.DATA_FILE.with_suffix(".corrotto.json").exists()


def test_restore_failure_stato_intatto(tmp_files):
    m.DATA_FILE.write_text('[{"id": 1, "title": "vivo"}]', encoding="utf-8")
    try:
        m.restore_snapshot(m.BACKUP_DIR / "inesistente.zip")
    except OSError:
        pass
    else:
        raise AssertionError("restore di snapshot assente deve sollevare OSError")
    assert "vivo" in m.DATA_FILE.read_text(encoding="utf-8")


def test_merge_last_saver_wins_via_store(tmp_files):
    s = TodoStore.load()
    s.add(make_todo("v1", todo_id=None))
    s.commit()
    late = TodoStore.load()
    early = TodoStore.load()
    early.by_id(1).title = "early"
    early.commit()
    late.by_id(1).title = "late"
    late.commit()
    assert TodoStore.load().by_id(1).title == "late"
