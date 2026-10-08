"""Equivalenza E3: src/radar.py == originali in app.py."""

import carpediem.app as app_module
import carpediem.radar as radar
from tests.conftest import make_todo


def test_geometria_equivalente():
    # Valori registrati pre-spostamento (il test girava verde sull'originale).
    assert [radar._radar_span(w) for w in (40, 70, 80, 120)] == [36, 64, 73, 110]
    for width in (40, 70, 80, 120):
        for col in (0, 3, width // 2, width - 1):
            assert radar._radar_day(col, width) == app_module._radar_day(col, width)
    todos = [
        make_todo("A", todo_id=1, due="2026-10-05"),
        make_todo("B", todo_id=2, due=""),
    ]
    for t in todos:
        assert radar._radar_horizon(t, "2026-09-30") == app_module._radar_horizon(
            t, "2026-09-30"
        )


def test_caption_equivalente():
    for data in (
        {"worst": [(1, -2)], "late": 1, "open_ok": 3, "nodate": 0},
        {"worst": [], "late": 0, "open_ok": 0, "nodate": 2},
    ):
        assert radar._radar_caption(data) == app_module.TodoApp._radar_caption(
            None, data
        )


def test_costanti_invariate():
    assert radar.RADAR_RED == app_module.RADAR_RED
    assert radar.RADAR_YELLOW == app_module.RADAR_YELLOW
    assert radar.RADAR_MARKER == app_module.RADAR_MARKER
    assert radar.RADAR_ROW_Y == app_module.RADAR_ROW_Y
