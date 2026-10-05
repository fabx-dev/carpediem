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


def _norm_name(req: str) -> str:
    import re

    return (
        re.split(r"[<>=!~\s\[]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")
    )


def _spec_of(req: str) -> str:
    import re

    m = re.match(r"^[A-Za-z0-9_.\-]+(\[.*?\])?\s*(.*)$", req.strip())
    return (m.group(2) or "").strip()


def _pins(path: pathlib.Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        name, _, ver = line.partition("==")
        out[_norm_name(name)] = ver.strip()
    return out


def _satisfies(pin: str, spec: str) -> bool:
    """Pin esatto dentro l'intervallo (confronto numerico per parti)."""

    def parts(v: str) -> tuple:
        out = []
        for p in v.split("."):
            out.append(int(p) if p.isdigit() else p)
        return tuple(out)

    for clause in spec.split(","):
        clause = clause.strip()
        if not clause:
            continue
        for op in ("==", ">=", "<=", ">", "<", "~="):
            if clause.startswith(op):
                want = parts(clause[len(op) :].strip(" .*"))
                got = parts(pin)
                if op == "==" and not got[: len(want)] == want:
                    return False
                if op == ">=" and not got >= want:
                    return False
                if op == "<=" and not got <= want:
                    return False
                if op == ">" and not got > want:
                    return False
                if op == "<" and not got < want:
                    return False
                if op == "~=" and not (got >= want and got[0] == want[0]):
                    return False
                break
    return True


def test_deps_allineate_pyproject_requirements_lock():
    """C6: pyproject (build) e requirements.txt (CI) dichiarano lo stesso
    set con gli stessi intervalli; i pin del lock rispettano gli intervalli."""
    py = {(_norm_name(d), _spec_of(d)) for d in _pyproject()["project"]["dependencies"]}
    req_lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    req = {
        (_norm_name(line), _spec_of(line))
        for line in req_lines
        if line.strip() and not line.strip().startswith(("#", "-"))
    }
    assert {n for n, _ in py} == {n for n, _ in req}
    assert {s for _, s in py} == {s for _, s in req}
    lock = _pins(ROOT / "requirements.lock")
    for name, spec in py:
        assert name in lock, f"{name} senza pin nel lock"
        assert _satisfies(lock[name], spec), f"{name}=={lock[name]} fuori {spec}"


def test_readme_and_license_present():
    assert (ROOT / "README.md").exists()
    assert (ROOT / "LICENSE").exists()


def test_package_layout_matches_build():
    # Il Dockerfile e il build includono ./src: l'entry-point deve esistere.
    assert (ROOT / "src" / "main.py").exists()
    assert (ROOT / "src" / "__init__.py").exists()


def test_sdist_contiene_integrations():
    """C6: lo smoke CI importa 5 moduli ma mai integrations: se la sdist
    perdesse outlook_auth lo si scoprirebbe solo all'uso. Skip senza dist."""
    import tarfile

    dists = sorted((ROOT / "dist").glob("*.tar.gz"))
    if not dists:
        import pytest

        pytest.skip("nessuna sdist in dist/")
    with tarfile.open(dists[-1]) as tf:
        names = tf.getnames()
    assert any(n.endswith("src/integrations/outlook_auth.py") for n in names)
    assert any(n.endswith("src/integrations/outlook.py") for n in names)
