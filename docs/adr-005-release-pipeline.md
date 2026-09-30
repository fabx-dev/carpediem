# ADR-005 — Release pipeline con gate sullo stesso SHA

- Stato: accettato (hardening 2026-09-30).
- Contesto: `publish.yml` pubblicava su `release: published` senza rieseguire
  la CI sul tag (release → publish senza verifica).
- Decisione: workflow unico di release — job `gate` (ruff + format + mypy +
  pytest sullo stesso `ref` della release), poi `build` (wheel + sdist +
  smoke da wheel installata in venv pulito), poi publish; `publish-pypi`
  dietro `environment: pypi`. Il dispatch manuale verso PyPI passa per lo
  stesso gate. Lock deterministico in `requirements.lock` (policy in
  `requirements.txt`). Dettagli in `docs/release.md` e
  `docs/dependencies.md`.
