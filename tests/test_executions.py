"""Storage M2 .todo_executions.json: assente/vuoto/append/reload/corrotti.

Stessi principi degli altri file: atomic write sotto lock, validazione
tollerante, mai migrazioni manuali. Usa import di modulo (conftest ricarica
i moduli in place: le classi from-importate restano stale per isinstance).
"""

import json
import threading

import src.storage as st


def test_file_assente_e_vuoto():
    assert st.load_executions() == []
    st.EXECUTIONS_FILE.write_text("", encoding="utf-8")
    assert st.load_executions() == []


def test_append_e_reload():
    st.append_execution({"task_id": 1, "ended_at": "2026-09-10 10:00"})
    st.append_execution({"task_id": 2, "ended_at": "2026-09-10 11:00"})
    loaded = st.load_executions()
    assert [(e.task_id, e.ended_at) for e in loaded] == [
        (1, "2026-09-10 10:00"),
        (2, "2026-09-10 11:00"),
    ]
    raw = json.loads(st.EXECUTIONS_FILE.read_text(encoding="utf-8"))
    assert isinstance(raw, list) and len(raw) == 2


def test_append_idempotente_stessa_coppia():
    first = st.append_execution({"task_id": 5, "ended_at": "2026-09-10 10:00"})
    second = st.append_execution(dict(first.to_dict()))
    assert second == first
    assert len(st.load_executions()) == 1


def test_dati_corrotti_e_non_lista():
    st.EXECUTIONS_FILE.write_text("{spazzatura", encoding="utf-8")
    assert st.load_executions() == []
    assert st.EXECUTIONS_FILE.with_suffix(".corrotto.json").exists()
    st.EXECUTIONS_FILE.with_suffix(".corrotto.json").unlink()
    st.EXECUTIONS_FILE.write_text('{"a": 1}', encoding="utf-8")
    assert st.load_executions() == []


def test_voci_non_dict_ignorate_e_tolleranza():
    st.EXECUTIONS_FILE.write_text(
        json.dumps(["xx", 42, {"task_id": "zz"}, {"task_id": 3}]),
        encoding="utf-8",
    )
    loaded = st.load_executions()
    assert [e.task_id for e in loaded] == [None, 3]


def test_backward_compat_senza_file():
    # installazione esistente senza history: si comporta come prima
    assert not st.EXECUTIONS_FILE.exists()
    assert st.load_executions() == []


def test_locking_concorrenza_cross_thread():
    errors = []

    def worker(n):
        try:
            for i in range(10):
                st.append_execution(
                    {"task_id": n * 100 + i, "ended_at": "2026-09-10 10:00"}
                )
        except Exception as exc:  # noqa: BLE001 - il test deve riportare, non alzare
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(st.load_executions()) == 40


def test_cap_trim_dei_piu_vecchi():
    st.MAX_EXECUTIONS, old = 3, st.MAX_EXECUTIONS
    try:
        for i in range(1, 6):
            st.append_execution({"task_id": i, "ended_at": f"2026-09-10 1{i}:00"})
        assert [e.task_id for e in st.load_executions()] == [3, 4, 5]
    finally:
        st.MAX_EXECUTIONS = old
