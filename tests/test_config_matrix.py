"""Matrice di validazione config (P1 §15): input invalido -> default/None,
mai stato persistito corrotto."""

import src.storage as m


def _roundtrip(cfg):
    m.save_config(cfg)
    return m.load_config()


def test_day_window_valida_e_limiti():
    good = {
        "date": "2026-09-30",
        "start": "09:00",
        "end": "18:00",
        "events": [{"start": "10:00", "end": "11:00", "title": "x"}],
    }
    assert m._validate_day_window(good)["events"] == good["events"]
    assert (
        m._validate_day_window({"date": "30-09-2026", "start": "09:00", "end": "10:00"})
        is None
    )
    assert (
        m._validate_day_window({"date": "2026-09-30", "start": "18:00", "end": "09:00"})
        is None
    )
    assert (
        m._validate_day_window({"date": "2026-09-30", "start": "25:00", "end": "26:00"})
        is None
    )
    assert (
        m._validate_day_window({"date": "2026-09-30", "start": "09:00", "end": "09:00"})
        is None
    )
    assert m._validate_day_window("non-un-dict") is None


def test_day_window_troppi_eventi_troncati():
    many = [{"start": "09:00", "end": "09:30", "title": f"e{i}"} for i in range(99)]
    out = m._validate_day_window(
        {"date": "2026-09-30", "start": "09:00", "end": "18:00", "events": many}
    )
    assert len(out["events"]) == m.MAX_DAY_EVENTS


def test_day_window_eventi_invalidi_scartati_singolarmente():
    out = m._validate_day_window(
        {
            "date": "2026-09-30",
            "start": "09:00",
            "end": "18:00",
            "events": [
                {"start": "10:00", "end": "11:00", "title": "ok"},
                {"start": "11:00", "end": "10:00", "title": "ko"},
                "spazzatura",
            ],
        }
    )
    assert [e["title"] for e in out["events"]] == ["ok"]


def test_outlook_malformato():
    assert m._validate_outlook(None) is None
    assert m._validate_outlook({}) is None
    assert m._validate_outlook({"client_id": "", "tenant": "t"}) is None
    assert m._validate_outlook({"client_id": "c", "tenant": "common"}) is None
    good = m._validate_outlook(
        {"client_id": "c", "tenant": "t", "account": "", "tz": "Nope/Zone"}
    )
    assert good["tz"] == "Europe/Rome"  # fallback, mai eccezione


def test_smart_lists_malformate():
    assert m._validate_smart_lists("no") == []
    assert m._validate_smart_lists([{"name": ""}]) == []
    assert (
        m._validate_smart_lists([{"name": "a", "state": "inesistente"}])[0]["state"]
        is None
    )
    dupes = [{"name": "A"}, {"name": "a"}]
    assert len(m._validate_smart_lists(dupes)) == 1
    assert (
        len(m._validate_smart_lists([{"name": f"n{i}"} for i in range(50)]))
        == m.MAX_SMART_LISTS
    )


def test_valori_estremi_clampati_e_roundtrip(tmp_files):
    cfg = m.load_config()
    cfg.update({"day_hours": 999, "daily_goal": -5, "day_window": {"bogus": True}})
    back = _roundtrip(cfg)
    assert back["day_hours"] == 6  # default: fuori range scartato
    assert back["daily_goal"] == 5
    assert back["day_window"] is None
    # roundtrip di tutte le chiavi default: nessuna chiave persa
    for key in m.DEFAULT_CONFIG:
        assert key in back
