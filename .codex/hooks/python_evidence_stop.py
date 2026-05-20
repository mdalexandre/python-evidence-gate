#!/usr/bin/env python3
"""Stop hook: refuse turn end when the per-turn evidence log shows a .py
edit without successful ruff/mypy/(pytest) evidence after the last edit."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from python_evidence_core import (  # noqa: E402
    audit,
    evaluate,
    read_events,
    repo_has_tests,
    turn_id,
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("stop_hook_active") is True:
        print(json.dumps({"continue": True}))
        return 0
    if os.environ.get("PYTHON_EVIDENCE_GATE") == "0":
        audit({"event": "override_env", "turn_id": turn_id(payload)})
        print(json.dumps({"continue": True}))
        return 0

    tid = turn_id(payload)
    events = read_events(tid)
    if not events:
        return 0

    cwd = str(payload.get("cwd") or os.environ.get("CODEX_CWD") or os.getcwd())
    pytest_required = repo_has_tests(cwd)
    missing, edited_files, bash_edits, last_edit_idx = evaluate(events, pytest_required)

    if not edited_files:
        return 0

    if not missing:
        audit({"event": "pass", "turn_id": tid,
               "py_edits": edited_files, "pytest_required": pytest_required})
        return 0

    head = edited_files[:4]
    files_preview = ", ".join(head) + ("..." if len(edited_files) > 4 else "")
    suggest_cmd = " && ".join(
        f"uv run {m}{' check' if m == 'ruff' else ''} <changed_files>" for m in missing
    )
    notes = []
    if pytest_required and "pytest" in missing:
        notes.append("Pytest is required because tests exist in this repo.")
    if bash_edits:
        notes.append(f"Bash-side .py mutations were detected: {', '.join(bash_edits[:3])}.")
    notes.append("Checks must succeed AND run after the most recent .py edit.")
    notes_str = " " + " ".join(notes)
    reason = (
        f"Python evidence gate (codex-v1): this turn edited {len(edited_files)} "
        f"Python file(s) ({files_preview}) without successful {', '.join(missing)} "
        f"evidence after the last edit. Run {suggest_cmd} and report the results "
        f"before ending the turn.{notes_str} "
        "Override (owner only): export PYTHON_EVIDENCE_GATE=0."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    audit({"event": "block", "turn_id": tid, "cwd": cwd,
           "py_edits": edited_files, "bash_py_edits": bash_edits,
           "missing": missing, "pytest_required": pytest_required,
           "last_edit_idx": last_edit_idx})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
