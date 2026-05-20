
## Python Tooling Loop

For Python work in any workspace, run the verification gate on changed files before reporting done:

1. `uv run ruff check --fix <changed_files>`
2. `uv run mypy <changed_files>`
3. `uv run pytest <related_test_files>`

Full suite only on explicit request. Type-annotate new function signatures. One test per new behavior. Do not refactor unrequested code.

If `pyproject.toml` is missing, scaffold once with `uv init`, `uv python pin 3.12`, then `uv add --dev ruff mypy pytest pytest-cov`. Lean config: ruff `select = ["E", "F", "I"]`, mypy default, pytest `addopts = "-ra --strict-markers"`.

Global binaries are available at `~/.local/bin/` (`uv`, `ruff`, `mypy`, `pytest`) for one-off checks outside a project. Inside a project, prefer `uv run` so the tools see the project interpreter and dependencies.

Tool output is mechanical verification, not final certification. Report changed files, checks run, and remaining risk.

An enforcement hook (`python_evidence_gate.py`) is active in this Claude install. It blocks Stop when any `.py` file was edited without successful ruff/mypy/(pytest) evidence running after the last edit. Override (owner only): `PYTHON_EVIDENCE_GATE=0`.
