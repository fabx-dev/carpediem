"""Validazione statica degli artifact di release (P0 §5).

Verifica che `pyproject.toml` dichiari correttamente ciò che PyPI
pubblicherà: nome, versione, entry-point, dipendenze runtime. Non compila
il package (quello lo fanno i job CI `build-smoke` e il gate di
`publish.yml` su wheel installata); qui si controlla che i metadati non
si rompano accidentalmente in un refactor.
"""

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_project_name():
    assert _pyproject()["project"]["name"] == "carpediem"


def test_version_present_and_shaped():
    import re

    version = _pyproject()["project"]["version"]
    assert re.match(r"^\d+\.\d+\.\d+$", version), version


def test_entry_point():
    scripts = _pyproject()["project"]["scripts"]
    assert scripts["carpediem"] == "src.main:main"
    import src.main as m

    assert callable(m.main)


def test_runtime_deps_declared():
    deps = _pyproject()["project"]["dependencies"]
    joined = " ".join(deps)
    for must in ("textual", "cryptography", "msal", "tzdata", "plotext"):
        assert must in joined


def test_readme_and_license_present():
    assert (ROOT / "README.md").exists()
    assert (ROOT / "LICENSE").exists()


def test_package_layout_matches_build():
    # Il Dockerfile e il build includono ./src: l'entry-point deve esistere.
    assert (ROOT / "src" / "main.py").exists()
    assert (ROOT / "src" / "__init__.py").exists()
