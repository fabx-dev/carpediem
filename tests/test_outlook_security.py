"""Regression sicurezza Outlook (P1 §14): un refactor non deve allentarla.

Principi blindati: permessi stretti, tenant pinnato (mai common),
auth-code + PKCE, callback solo loopback, account binding, timeout,
token separato 0600 mai nei backup/log.
"""

import pathlib

import src.storage as storage
from src.integrations import outlook as o
from src.integrations import outlook_auth as oa


def test_scope_congelato():
    assert o.GRAPH_SCOPES == ("Calendars.Read",)


def test_endpoint_e_authority_pinnati():
    assert o.GRAPH_BASE_URL == "https://graph.microsoft.com/v1.0"
    assert "{tenant}" in o.LOGIN_AUTHORITY
    assert "common" not in o.LOGIN_AUTHORITY


def test_loopback_solo_ipv4_esplicito():
    assert oa.LOOPBACK_HOST == "127.0.0.1"
    assert oa.LOOPBACK_TIMEOUT >= 60


def test_token_escluso_dai_backup():
    names = [name for name, _path in storage._backup_sources()]
    assert "outlook" not in names and "token" not in names
    assert storage.OUTLOOK_TOKEN_FILE.name not in {
        p.name for _, p in storage._backup_sources()
    }


def test_common_rifiutato_in_validazione():
    bad = {"client_id": "x" * 36, "tenant": "common", "account": "", "tz": ""}
    assert storage._validate_outlook(bad) is None
    for t in ("consumers", "organizations"):
        assert storage._validate_outlook({"client_id": "x", "tenant": t}) is None


def test_account_binding_enforced():
    assert (
        storage._validate_outlook(
            {"client_id": "x", "tenant": "tid", "account": "not-an-email"}
        )
        is None
    )


def test_auth_uri_non_https_rifiutato():
    from tests.test_outlook_auth import CFG, FakeCache, FakeClient, FakeListener

    fake = FakeClient(auth_flow={"auth_uri": "http://evil/x"})
    client = oa.OutlookClient(
        dict(CFG), client=fake, cache=FakeCache(), listener_factory=FakeListener
    )
    try:
        client.authcode_start()
    except oa.OutlookError as exc:
        assert exc.code == "bad_auth_uri"
    else:
        raise AssertionError("auth_uri http deve essere rifiutato")


def test_screen_mai_rete_outlook():
    import re

    _import = re.compile(r"^\s*(import|from)\s+[\w.]*outlook_auth", re.M)
    _browser = re.compile(r"^\s*(import|from)\s+webbrowser", re.M)
    for path in sorted(pathlib.Path("src/screens").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        assert not _import.search(src), f"{path} importa il modulo di rete"
        assert not _browser.search(src), f"{path} apre il browser"
