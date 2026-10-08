"""Test i18n: parita catalogo, fallback, detect, resolve."""

import carpediem.lang as lang


def test_parita_chiavi(italian_lang):
    ki, ke = set(lang.STRINGS["it"]), set(lang.STRINGS["en"])
    assert ki == ke
    assert len(ki) > 200


def test_fallback_e_formato(italian_lang):
    assert lang.T("b_new") == "Nuovo"
    assert lang.T("chiave_inesistente") == "chiave_inesistente"
    assert lang.T("n_added", t="X") == "Todo 'X' aggiunto!"
    lang.set_lang("en")
    try:
        assert lang.T("b_new") == "New"
        assert lang.T("n_added", t="X") == "Todo 'X' added!"
    finally:
        lang.set_lang("it")


def test_key_sections(italian_lang):
    assert lang.key_sections()[0][0] == "TASK"
    lang.set_lang("en")
    try:
        assert lang.key_sections()[0][0] == "TASKS"
    finally:
        lang.set_lang("it")


def test_resolve():
    assert lang.resolve_lang("it") == "it"
    assert lang.resolve_lang("EN") == "en"
    assert lang.resolve_lang("auto") in ("it", "en")
    assert lang.resolve_lang("xxx") in ("it", "en")


def test_detect(monkeypatch):
    import locale as _locale

    monkeypatch.setattr(_locale, "getlocale", lambda: ("it_IT", "UTF-8"))
    monkeypatch.setenv("LC_ALL", "")
    monkeypatch.setenv("LANG", "")
    assert lang.detect_system_lang() == "it"
    monkeypatch.setattr(_locale, "getlocale", lambda: ("en_US", "UTF-8"))
    assert lang.detect_system_lang() == "en"
    monkeypatch.setattr(_locale, "getlocale", lambda: (None, None))
    assert lang.detect_system_lang() == "it"
    monkeypatch.setenv("LANG", "it_IT.UTF-8")
    assert lang.detect_system_lang() == "it"
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    monkeypatch.setattr(_locale, "getlocale", lambda: (None, None))
    assert lang.detect_system_lang() == "en"


def test_date_helpers(italian_lang):
    assert lang.format_date_long("2026-09-10") == "Giovedì 10 Settembre 2026"
    assert lang.format_date_long("nope") == "nope"
    assert lang.months()[9] == "Settembre"
    assert lang.days_short()[0] == "Lun"
    lang.set_lang("en")
    try:
        assert lang.format_date_long("2026-09-10") == "Thursday, September 10, 2026"
        assert lang.months()[9] == "September"
        assert lang.prio_letters() == {"alta": "H", "media": "M", "bassa": "L"}
        assert lang.prio_disp("alta") == "High"
        assert lang.rec_disp("nessuna") == "None"
    finally:
        lang.set_lang("it")
