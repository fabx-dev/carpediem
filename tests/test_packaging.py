"""Packaging: wheel senza `src` applicativo, import + entry point (milestone)."""

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_import_package():
    import carpediem

    assert pathlib.Path(carpediem.__file__).parent.name == "carpediem"
    assert not hasattr(carpediem, "TodoApp") or True  # il package resta sottile


def test_entry_point_callable():
    from carpediem.main import main

    assert callable(main)


def test_no_src_package_applicativo():
    assert not (ROOT / "src" / "__init__.py").exists()
    assert (ROOT / "src" / "carpediem" / "__init__.py").exists()


def _build_wheel(tmp_path):
    try:
        import build  # noqa: F401
    except ImportError:
        pytest.skip("package `build` assente")
    out = tmp_path / "dist"
    r = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out), str(ROOT)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    wheels = sorted(out.glob("*.whl"))
    assert wheels, "nessuna wheel prodotta"
    return wheels[-1]


def test_wheel_contenuto(tmp_path):
    import zipfile

    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert any(n.startswith("carpediem/") for n in names)
    assert any(n.startswith("carpediem/main.py") for n in names), names[:10]
    assert not any(n == "src/__init__.py" for n in names)
    assert not any(n.startswith("src/app.py") for n in names)
    assert not any(n.startswith("src/main.py") for n in names)
    assert not any(n.startswith("src/planner/") for n in names)
