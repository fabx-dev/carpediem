"""Backup security (P1 §7): dir/file owner-only, token escluso, restore/rollback."""

import os
import stat
import zipfile

import carpediem.storage as m


def _posix() -> bool:
    return os.name == "posix"


def test_backup_creato_e_token_escluso(tmp_files):
    m.DATA_FILE.write_text("[]", encoding="utf-8")
    tok = m.OUTLOOK_TOKEN_FILE
    tok.write_text('{"cache": "segreto"}', encoding="utf-8")
    out = m.create_backup()
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "todos.json" in names
    assert not any("outlook" in n or "token" in n for n in names)
    assert tok.read_text(encoding="utf-8") == '{"cache": "segreto"}'


def test_backup_permission_attempt(tmp_files):
    m.DATA_FILE.write_text("[]", encoding="utf-8")
    out = m.create_backup()
    assert out.exists()
    assert m.BACKUP_DIR.exists()
    if not _posix():
        return  # Windows: l'attempt non deve rompere, niente asserzioni sui bit
    mode_dir = stat.S_IMODE(m.BACKUP_DIR.stat().st_mode)
    mode_file = stat.S_IMODE(out.stat().st_mode)
    assert mode_dir & 0o077 == 0, oct(mode_dir)
    assert mode_file & 0o077 == 0, oct(mode_file)


def test_restore_roundtrip(tmp_files):
    m.DATA_FILE.write_text('[{"id": 1}]', encoding="utf-8")
    snap = m.create_backup()
    m.DATA_FILE.write_text('[{"id": 2}]', encoding="utf-8")
    m.restore_snapshot(snap)
    assert '"id": 1' in m.DATA_FILE.read_text(encoding="utf-8")


def test_restore_corrotto_fallisce_sicuro(tmp_files):
    m.DATA_FILE.write_text('[{"id": 1}]', encoding="utf-8")
    bad = m.BACKUP_DIR / "tasko_20990101_000000.zip"
    m.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"non uno zip")
    try:
        m.restore_snapshot(bad)
    except OSError:
        pass
    else:
        raise AssertionError("restore di zip corrotto deve sollevare OSError")
    assert '"id": 1' in m.DATA_FILE.read_text(encoding="utf-8")


def test_crypto_derive_cache_documentata():
    # Guardrail: la cache KDF e' una decisione documentata (Opzione C),
    # non un dettaglio rimovibile per caso.
    import carpediem.crypto as c

    assert hasattr(c._derive, "cache_info")
    assert c._derive.cache_info().maxsize == 8
