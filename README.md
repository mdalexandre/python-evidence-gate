# Python Evidence Gate for AI Coding Agents

> Refuse to let your AI agent mark Python work "done" without running ruff, mypy, and pytest with successful exit and proper ordering against the edits.

[![CI](https://github.com/mdalexandre/python-evidence-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/mdalexandre/python-evidence-gate/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What this does

A pair of hook installations, one for **Claude Code**, one for **Codex CLI**, that watch every tool call the agent makes during a turn and:

1. Record every `.py` file the agent edits (via `Edit` / `Write` / `MultiEdit` / `NotebookEdit`, via `apply_patch`, or via shell `> foo.py` / `tee foo.py` / `sed -i foo.py`).
2. Record every **successful** `ruff check`, `mypy`, or `pytest` invocation that ran **after** the last `.py` edit.
3. At the end of the turn, **block** the agent's Stop if any required evidence is missing.

The agent receives a structured `{"decision":"block","reason":"..."}` from the hook subsystem and is forced to either run the missing checks or invoke the owner-only override `PYTHON_EVIDENCE_GATE=0`.

## The problem this solves

AI coding agents write Python that *looks* correct but often is not. Type signatures hallucinated, unused imports accumulated, edge cases untested. The standard advice is "tell the agent to run ruff/mypy/pytest". That advice is a doctrine, not an enforcement: an agent told to run checks can still skip them, or run them before the edit, or run a failing chain and report success, or hide a missing check in a long final message.

This project adds the missing enforcement layer.

## Who this is for

Developers using Claude Code, Codex CLI, or both, who have been burned by AI-introduced silent bugs and want a hard guarantee that mechanical verification ran before the agent can say "done". The gate is the **agent's** guardrail, not the user's.

## Quickstart

```bash
# Linux / macOS one-liner
curl -fsSL https://raw.githubusercontent.com/mdalexandre/python-evidence-gate/main/install.sh | bash

# Verify
~/.claude/hooks/python_evidence_gate.py < /dev/null  # exit 0 (no transcript yet)
~/.codex/hooks/python_evidence_stop.py  < /dev/null  # exit 0
```

The installer:

1. Installs `uv` if missing (via the official Astral installer).
2. Runs `uv tool install ruff mypy` (no-op if already installed).
3. Detects which agent CLIs are installed (`~/.claude/settings.json`, `~/.codex/hooks.json`) and installs only the relevant hooks.
4. Backs up every modified config file with a timestamped `.bak-pre-python-evidence-<ts>` sibling.
5. Appends the doctrine section to `~/.claude/CLAUDE.md` and/or `~/.codex/AGENTS.md` (idempotent via grep check).
6. Runs the test suite once to verify the install.

For Windows, [`docs/WINDOWS.md`](docs/WINDOWS.md) covers the WSL2 path (recommended) and the native PowerShell path (best-effort).

## How it works

### Claude Code (single-phase)

The Claude Stop event ships `transcript_path` in stdin. A single Stop hook walks the JSONL transcript from the last fresh user message, collects `.py` edits and successful ruff/mypy/pytest invocations, then evaluates: any missing check → block.

### Codex CLI (two-phase)

The Codex Stop event ships only `last_assistant_message`, so single-phase walking is impossible. Instead, three hooks coordinate via a per-turn events log at `/tmp/codex-python-evidence/<session_id>.jsonl`:

- **`UserPromptSubmit`**: deletes the prior log so each fresh prompt starts clean.
- **`PostToolUse`**: appends `edit` events (for `.py` edits) and `check` events (for successful ruff/mypy/pytest) as they happen.
- **`Stop`**: reads the log and applies the same gate logic.

Both architectures honor the same rules:

- **Order preservation**: a check counts only if it ran *after* the last `.py` edit.
- **Exit-code awareness**: a check counts only if `tool_result.is_error` is not true and the content has no `Exit code N` prefix.
- **Pytest only when tests exist**: required iff `tests/` / `test/` dir exists, or `[tool.pytest…]` in `pyproject.toml`, or any `test_*.py` / `*_test.py` within depth 4.
- **`ruff check`, not `ruff format`**: the doctrine requires `check`. Bare `ruff` and `ruff format` do not satisfy the gate.

## Per-project scaffold

For each new Python project where you want a fresh ruff/mypy/pytest config in `pyproject.toml`:

```bash
uv init
uv python pin 3.12
uv add --dev ruff mypy pytest pytest-cov
```

Then append the lean config block from [`docs/pyproject.example.toml`](docs/pyproject.example.toml) to your `pyproject.toml`.

## Override

For emergencies or owner-judgment scenarios where you want to bypass the gate for one session:

```bash
export PYTHON_EVIDENCE_GATE=0
```

Every override is recorded in the audit log (`~/.claude/hooks/python_evidence_gate_audit.jsonl` or `~/.codex/hooks/python_evidence_audit.jsonl`) with event type `override_env`.

To permanently disable, remove the gate's entry from `~/.claude/settings.json` or `~/.codex/hooks.json`. The install script writes timestamped backups for clean rollback.

## Tests

```bash
# Claude side
pytest .claude/hooks/tests/test_python_evidence_gate.py -v

# Codex side
pytest .codex/hooks/tests/test_python_evidence.py -v
```

Expected: **19 passed** on the Claude suite, **26 passed** on the Codex suite, **45 total**. All under 1 second.

## Architecture, threat model, contributing

- [`SPR-python-evidence-gate.md`](SPR-python-evidence-gate.md) is the authoritative design spec (9 chapters, 12k words). Read it before submitting non-trivial PRs.
- [`docs/SCHEMAS.md`](docs/SCHEMAS.md) documents the JSON contracts for both agents' hook stdin/stdout.
- [`docs/security/threat-model.md`](docs/security/threat-model.md) covers the STRIDE analysis and trust boundary.
- [`docs/WINDOWS.md`](docs/WINDOWS.md) covers Windows install paths.
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) covers how to submit a PR, sign-off, and what CI will check.

## License

MIT. See [`LICENSE`](LICENSE).
