"""Validazione form password (estratto da TodoApp, E2): niente I/O/UI.

Il controllo sulla password corrente e' iniettato (`check_current`) per
tenere fuori crypto e storage: l'app passa `self._sec_current_ok`.
Le stringhe passano da `src.lang.T` (solo dati, come nel resto del dominio).
Nota: su lista vuota ritornano il messaggio "compila tutto" invece di
sollevare IndexError come faceva il metodo originale — i form passano
sempre il numero esatto di campi, quindi nessun percorso reale cambia.
"""

from collections.abc import Callable

from carpediem.lang import T

MIN_PASSWORD_LEN = 8


def valid_new(values: list[str]) -> str | None:
    """Errore i18n o None se la nuova password e' accettabile."""
    if any(not v for v in values):
        return T("n_sec_fill")
    new, repeat = values[-2], values[-1]
    if len(new) < MIN_PASSWORD_LEN:
        return T("n_sec_need8")
    if new != repeat:
        return T("n_sec_mismatch")
    return None


def valid_change(values: list[str], check_current: Callable[[str], bool]) -> str | None:
    if any(not v for v in values):
        return T("n_sec_fill")
    if not check_current(values[0]):
        return T("n_sec_badcurrent")
    return valid_new(values[1:])


def valid_disable(
    values: list[str], check_current: Callable[[str], bool]
) -> str | None:
    if any(not v for v in values):
        return T("n_sec_fill")
    if not check_current(values[0]):
        return T("n_sec_badcurrent")
    return None
