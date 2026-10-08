"""Test modello TodoItem e helpers date/ricorrenze (no UI)."""

from datetime import datetime

import carpediem.main as m


def test_roundtrip_minimale():
    t = m.TodoItem(title="Ciao", todo_id=1)
    d = t.to_dict()
    t2 = m.TodoItem.from_dict(d)
    assert t2.title == "Ciao"
    assert t2.id == 1
    assert t2.state == "attivo"
    assert t2.pomodoro_log == []
    assert t2.stima_pomo == 0


def test_from_dict_tollerante():
    t = m.TodoItem.from_dict({"title": "", "priority": "boh", "parent_id": "x"})
    assert t.title == "Senza titolo"
    assert t.priority == m.Priority.MEDIUM
    assert t.parent_id is None


def test_stati():
    assert m.TodoItem(title="a", todo_id=1).state == "attivo"
    assert m.TodoItem(title="a", todo_id=1, paused=True).state == "in_sospeso"
    assert m.TodoItem(title="a", todo_id=1, done=True).state == "completato"


def test_normalize_due():
    assert m._normalize_due("oggi") == datetime.now().strftime("%Y-%m-%d")
    assert m._normalize_due("2026-1-5") == "2026-01-05"
    assert m._normalize_due("10/09/2026 9:00") == "2026-09-10 09:00"
    assert m._normalize_due("") == ""
    assert m._is_valid_due("2026-09-10 09:00")
    assert not m._is_valid_due("ieri")


def test_recurrence_next():
    assert m.Recurrence.DAILY.next_date("2026-01-31") == "2026-02-01"
    assert m.Recurrence.WEEKLY.next_date("2026-01-01") == "2026-01-08"
    assert m.Recurrence.MONTHLY.next_date("2026-01-31") == "2026-02-28"
    assert m.Recurrence.YEARLY.next_date("2024-02-29") == "2025-02-28"
    assert m.Recurrence.YEARLY.next_date("2026-09-10 09:00") == "2027-09-10 09:00"
    assert m.Recurrence.NONE.next_date("2026-09-10") == "2026-09-10"


def test_pomo_label():
    assert m._pomo_label(m.TodoItem(title="x", todo_id=1)) == ""
    assert m._pomo_label(m.TodoItem(title="x", todo_id=1, pomodoros=3)) == "🍅x3"
    assert (
        m._pomo_label(m.TodoItem(title="x", todo_id=1, pomodoros=2, stima_pomo=4))
        == "🍅2/4"
    )


def test_pomo_log_legacy():
    t = m.TodoItem.from_dict({"title": "V", "pomodoros": 2})
    assert t.pomodoro_log == [] and t.pomodoros == 2
    t2 = m.TodoItem.from_dict(
        {"title": "Z", "pomodoro_log": ["2026-09-01 10:00", 123, ""]}
    )
    assert t2.pomodoro_log == ["2026-09-01 10:00"]
