"""Auth e fetch Outlook/Microsoft 365 (B2): unico punto di rete dell'integrazione.

Disegno sicurezza-max:
- public client MSAL, Device Code Flow (password/2FA mai viste da noi: solo
  nel browser Microsoft); niente client-secret (niente segreto da rubare);
- authority pinnata al tenant di config (`common` rifiutato in validazione),
  scope congelato `GRAPH_SCOPES`, endpoint solo `GRAPH_BASE_URL`;
- `verification_uri` del device flow validata (https + host Microsoft):
  anti-phishing, mai URL hardcodato;
- account binding: l'username del token deve coincidere con quello in
  config (se vuoto al primo login, si adotta quello autenticato);
- token-cache MSAL cifrata a riposo via storage (file 0600, mai backup/log);
- HTTP con sola stdlib `urllib` (nessuna nuova dipendenza oltre `msal`),
  timeout esplicito, errori mappati in codici (mai token negli errori).

Niente stato globale: `OutlookClient` riceve client/cache/http iniettabili
(i test usano doppi, mai rete/account reali). Le screen non importano mai
questo modulo: lo usa l'app via callback (come `on_window`).
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from src.integrations.outlook import (
    GRAPH_BASE_URL,
    GRAPH_SCOPES,
    LOGIN_AUTHORITY,
    parse_graph_events,
)
from src.storage import delete_outlook_token, load_outlook_token, save_outlook_token

HTTP_TIMEOUT = 15
CALENDAR_TOP = 50

#: Host accettati per la verification_uri del device flow (anti-phishing).
_VERIFICATION_HOSTS = ("login.microsoftonline.com", "microsoft.com", "aka.ms")


class OutlookError(Exception):
    """Errore integrazione con codice stabile per la UI (mai token dentro)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _check_verification_uri(uri: str) -> str:
    """Rifiuta verification_uri fuori allowlist (fail-closed)."""
    try:
        parts = urllib.parse.urlparse(uri)
    except Exception:
        raise OutlookError("bad_verification_uri", uri or "")
    if parts.scheme != "https" or parts.hostname not in _VERIFICATION_HOSTS:
        raise OutlookError("bad_verification_uri", parts.hostname or "")
    return uri


class OutlookClient:
    """Adapter autenticato: silent -> device flow -> fetch -> parse."""

    def __init__(self, cfg: dict, client=None, cache=None, http_get=None) -> None:
        self.cfg = dict(cfg)
        self._client = client
        self._cache = cache if cache is not None else self._new_cache()
        self._http_get = http_get or self._http_get_default
        stored = load_outlook_token()
        if stored and hasattr(self._cache, "deserialize"):
            try:
                self._cache.deserialize(stored)
            except Exception:
                pass

    @staticmethod
    def _new_cache():
        from msal import SerializableTokenCache  # type: ignore[import-untyped]

        return SerializableTokenCache()

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from msal import PublicClientApplication  # type: ignore[import-untyped]
        except ImportError:
            raise OutlookError("msal_missing")
        authority = LOGIN_AUTHORITY.format(tenant=self.cfg.get("tenant", ""))
        self._client = PublicClientApplication(
            str(self.cfg.get("client_id", "")),
            authority=authority,
            token_cache=self._cache,
        )
        return self._client

    def _account(self):
        """Account MSAL bound a config (None = nessun vincolo possibile)."""
        client = self._ensure_client()
        try:
            accounts = client.get_accounts() or []
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        want = str(self.cfg.get("account", "") or "").lower()
        if want:
            for acc in accounts:
                if str(acc.get("username", "")).lower() == want:
                    return acc
            return None
        return accounts[0] if len(accounts) == 1 else None

    def token_silent(self) -> tuple[str | None, str]:
        """(access_token|None, adopted_account): mai interattivo, mai solleva."""
        acc = self._account()
        if acc is None:
            return None, ""
        try:
            result = self._ensure_client().acquire_token_silent(
                list(GRAPH_SCOPES), account=acc
            )
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        if not result or "access_token" not in result:
            return None, ""
        username = str(
            (result.get("id_token_claims") or {}).get("preferred_username", "")
            or acc.get("username", "")
        )
        want = str(self.cfg.get("account", "") or "")
        if want and username.lower() != want.lower():
            raise OutlookError("account_mismatch", username)
        return result["access_token"], username

    def device_flow_start(self) -> dict:
        """Avvia il device flow: ritorna {uri, code} da mostrare all'utente."""
        client = self._ensure_client()
        try:
            flow = client.initiate_device_flow(scopes=list(GRAPH_SCOPES))
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        if "user_code" not in flow:
            raise OutlookError(
                "device_flow_refused", str(flow.get("error_description", ""))[:160]
            )
        uri = _check_verification_uri(str(flow.get("verification_uri", "")))
        return {"uri": uri, "code": str(flow.get("user_code", "")), "flow": flow}

    def device_flow_poll(self, flow: dict, timeout: float | None = None):
        """Attende la conferma nel browser; ritorna (token, username)."""
        client = self._ensure_client()
        try:
            if timeout is None:
                result = client.acquire_token_by_device_flow(flow)
            else:
                result = client.acquire_token_by_device_flow(flow, timeout=timeout)
        except Exception as exc:
            raise OutlookError("msal_error", str(exc)[:120])
        if not result or "access_token" not in result:
            raise OutlookError(
                "device_flow_failed", str((result or {}).get("error", ""))[:120]
            )
        username = str(
            (result.get("id_token_claims") or {}).get("preferred_username", "")
        )
        want = str(self.cfg.get("account", "") or "")
        if want and username.lower() != want.lower():
            raise OutlookError("account_mismatch", username)
        self.save_cache()
        return result["access_token"], username

    def save_cache(self) -> None:
        """Persiste la cache (cifrata 0600 via storage)."""
        try:
            blob = self._cache.serialize()
        except Exception as exc:
            raise OutlookError("cache_error", str(exc)[:120])
        save_outlook_token(blob)

    def fetch_day(self, token: str, day_s: str):
        """(eventi, allday, scartati) del giorno via calendarView."""
        from datetime import datetime, timedelta

        try:
            day = datetime.strptime(day_s, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise OutlookError("bad_day", day_s)
        lo = day.strftime("%Y-%m-%dT00:00:00")
        hi = (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
        query = urllib.parse.urlencode(
            {
                "startDateTime": lo,
                "endDateTime": hi,
                "$select": "subject,start,end,showAs,isAllDay",
                "$orderby": "start/dateTime",
                "$top": str(CALENDAR_TOP),
            }
        )
        url = f"{GRAPH_BASE_URL}/me/calendarview?{query}"
        try:
            payload = self._http_get(
                url, token, str(self.cfg.get("tz") or "Europe/Rome")
            )
        except OutlookError:
            raise
        except Exception as exc:
            raise OutlookError("network", str(exc)[:120])
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise OutlookError("bad_payload")
        return parse_graph_events(
            payload, day_s, tz=str(self.cfg.get("tz") or "Europe/Rome")
        )

    @staticmethod
    def _http_get_default(url: str, token: str, tz: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Prefer": f'outlook.timezone="{tz}"',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise OutlookError("unauthorized")
            if exc.code == 403:
                raise OutlookError("admin_consent")
            raise OutlookError(f"http_{exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OutlookError("network", str(exc)[:120])


def disconnect() -> None:
    """Disconnessione: cancella il token locale (revoca lato MS dai link in UI)."""
    delete_outlook_token()
