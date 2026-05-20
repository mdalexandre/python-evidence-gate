#!/usr/bin/env python3
"""PostToolUse hook: append .py edit events and successful ruff/mypy/pytest
invocation events to the per-turn Python evidence log.

Codex tool naming handled:
  - Edit, Write, MultiEdit, NotebookEdit (from the Claude bridge or direct)
  - apply_patch (Codex native edit tool; patch body parsed for .py paths)
  - Bash, exec_command (both treated as shell)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from python_evidence_core import (  # noqa: E402
    append_event,
    audit,
    detect_apply_patch_py_edits,
    detect_bash_py_edits,
    matches_check,
    read_events,
    result_is_failure,
    split_segments,
    turn_id,
)

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "exec_command"}
PATCH_TOOLS = {"apply_patch"}


def main() -> int:
    if os.environ.get("PYTHON_EVIDENCE_GATE") == "0":
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = str(payload.get("tool_name") or "")
    raw_inp = payload.get("tool_input")
    tool_input: dict = raw_inp if isinstance(raw_inp, dict) else {}
    tool_response = payload.get("tool_response")
    if tool_response is None:
        tool_response = payload.get("tool_output")
    tid = turn_id(payload)
    idx = len(read_events(tid))

    py_files_edited: list[str] = []
    if tool_name in EDIT_TOOLS:
        fp = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if isinstance(fp, str) and fp.endswith(".py"):
            py_files_edited.append(fp)
            append_event(tid, {"type": "edit", "idx": idx, "file_path": fp,
                               "tool": tool_name, "source": "tool"})
            idx += 1
    elif tool_name in PATCH_TOOLS:
        patch_body = (tool_input.get("input") or tool_input.get("patch")
                      or tool_input.get("body") or "")
        if isinstance(patch_body, str):
            for fp in detect_apply_patch_py_edits(patch_body):
                py_files_edited.append(fp)
                append_event(tid, {"type": "edit", "idx": idx, "file_path": fp,
                                   "tool": tool_name, "source": "patch"})
                idx += 1
    elif tool_name in SHELL_TOOLS:
        cmd = tool_input.get("command") or tool_input.get("cmd") or ""
        if isinstance(cmd, list):
            cmd = " ".join(str(p) for p in cmd)
        if isinstance(cmd, str) and cmd:
            for fp in detect_bash_py_edits(cmd):
                py_files_edited.append(fp)
                append_event(tid, {"type": "edit", "idx": idx, "file_path": fp,
                                   "tool": tool_name, "source": "bash"})
                idx += 1
            failed = result_is_failure(tool_response)
            if not failed:
                for segment in split_segments(cmd):
                    for check_name in ("ruff", "mypy", "pytest"):
                        if matches_check(segment, check_name):
                            append_event(tid, {"type": "check", "idx": idx,
                                               "name": check_name, "ok": True})
                            idx += 1

    audit({"event": "post_tool", "turn_id": tid, "tool": tool_name,
           "py_files_edited": py_files_edited})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
