# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/) 1.1.0. Versioning: [SemVer](https://semver.org/) 2.0.0.

## [Unreleased]

### Added

- Initial public repository scaffolded from `SPR-python-evidence-gate.md` via `/spr-build`.
- `LICENSE` (MIT) and `README.md` with quickstart.
- `install.sh` (Linux / macOS) and `scripts/uninstall.sh`.
- `Makefile` with `install`, `verify`, `test`, `lint`, `type`, `uninstall`, `release` targets.
- `pyproject.toml` with lean ruff / mypy / pytest config.
- `.github/workflows/ci.yml` matrix (Ubuntu + macOS, Python 3.11 + 3.12) running ruff, mypy, pytest, shellcheck, gitleaks.
- Claude Code Stop hook at `.claude/hooks/python_evidence_gate.py` with 19-case test suite.
- Codex CLI two-phase hook trio at `.codex/hooks/` (`python_evidence_userprompt.py`, `python_evidence_postuse.py`, `python_evidence_stop.py`) plus the shared library `python_evidence_core.py`, with 26-case test suite.
- Doctrine snippets at `docs/doctrine.claude.md` and `docs/doctrine.codex.md` for append to `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`.
- Threat model at `docs/security/threat-model.md` (STRIDE per element, trust boundary explicit).
- Hook JSON schemas at `docs/SCHEMAS.md`.
- Windows install guide at `docs/WINDOWS.md` (WSL2 recommended; native PowerShell best-effort).
- Contributing guide at `docs/CONTRIBUTING.md`.
- SPR-python-evidence-gate.md (12k-word design doc) and SPR-python-evidence-gate.manifest.yaml (machine-readable manifest).

### Known limitations (v1)

- Per-turn (not per-file) check granularity.
- Whole-pipeline exit-code rule (a failing pytest inside a `ruff && mypy && pytest` chain voids all three).
- Notebooks (`.ipynb`) via `NotebookEdit` observed but not gated.
- Regex-based Bash mutation detection catches `>`, `>>`, `tee`, `sed -i`; exotic patterns not detected.
- Windows CI parity is deferred to v1.1.
