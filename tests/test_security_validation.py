"""Equivalenza E2: src/security_validation == metodi originali di TodoApp."""

import src.security_validation as sv
from tests.conftest import make_app


def _app():
    return make_app([])


def test_new_equivalente():
    app = _app()
    for values in (
        ["", ""],
        ["abcdefgh", "x"],
        ["abc", "abc"],
        ["abcdefgh", "abcdefgh"],
    ):
        assert app._pw_valid_new(list(values)) == sv.valid_new(list(values))


def test_change_e_disable_equivalenti(tmp_files):
    app = _app()
    # Stesso check che il wrapper inietta: equivalenza esatta.
    check = app._sec_current_ok
    for values in (
        ["", "x", "y"],
        ["sbagliata", "abcdefgh", "abcdefgh"],
        ["giusta", "abc", "abc"],
        ["giusta", "abcdefgh", "abcdefgh"],
        ["giusta", "abcdefgh", "diversa"],
    ):
        assert app._pw_valid_change(list(values)) == sv.valid_change(
            list(values), check
        )
        assert app._pw_valid_disable(list(values)) == sv.valid_disable(
            list(values), check
        )


def test_regole():
    assert sv.valid_new(["abcdefgh", "abcdefgh"]) is None
    assert sv.valid_new(["abc", "abc"]) is not None
    assert sv.valid_new(["abcdefgh", "x"]) is not None
    assert sv.valid_change(["ok", "abcdefgh", "abcdefgh"], lambda _p: True) is None
    assert sv.valid_change(["ko", "abcdefgh", "abcdefgh"], lambda _p: False) is not None
    assert sv.valid_disable(["ok"], lambda _p: True) is None
