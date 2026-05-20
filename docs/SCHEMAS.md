# Hook JSON Schemas

The gate communicates with Claude Code and Codex CLI over their respective hook subsystems. This document defines the JSON shapes the gate reads and writes. Authoritative source: the SPR §3.3 "External interface requirements".

## Claude Stop event (stdin)

```json
{
  "session_id": "...",
  "transcript_path": "/home/<user>/.claude/projects/.../<session>.jsonl",
  "cwd": "/path/to/working/dir",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
```

The hook walks `transcript_path` from the most recent fresh user message forward. Each line of the transcript is a JSON record; the gate cares about `tool_use` and `tool_result` blocks.

## Codex Stop event (stdin)

```json
{
  "session_id": "...",
  "cwd": "/path/to/working/dir",
  "last_assistant_message": "...",
  "stop_hook_active": false
}
```

Note: no `transcript_path`. The gate reads the per-turn events log written by the PostToolUse hook.

## Codex PostToolUse event (stdin)

```json
{
  "session_id": "...",
  "tool_name": "Edit | Write | MultiEdit | NotebookEdit | apply_patch | Bash | exec_command",
  "tool_input": { /* tool-specific */ },
  "tool_response": {
    "is_error": false,
    "exit_code": 0,
    "content": "...",
    "output": "..."
  }
}
```

For `Edit` / `Write` / `MultiEdit` / `NotebookEdit`: `tool_input.file_path` is the edited file.
For `apply_patch`: `tool_input.input` (or `.patch` / `.body`) is the patch text. The gate parses lines matching `*** (Add|Update|Delete) File: <path>`.
For `Bash` / `exec_command`: `tool_input.command` is the shell command string.

## Codex UserPromptSubmit event (stdin)

```json
{
  "session_id": "...",
  "cwd": "/path/to/working/dir",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "..."
}
```

The gate uses `session_id` only; the prompt content is ignored.

## Block response (stdout)

```json
{
  "decision": "block",
  "reason": "Python evidence gate (codex-v1): this turn edited 1 Python file(s) (/tmp/foo.py) without successful ruff, mypy evidence after the last edit. Run uv run ruff check <changed_files> && uv run mypy <changed_files> and report the results before ending the turn. Override (owner only): export PYTHON_EVIDENCE_GATE=0."
}
```

The agent receives this and is required to continue the turn until it either runs the missing checks or invokes the override.

## Continue response (stdout)

For Codex: `{"continue": true}` on stdout, exit 0.
For Claude: empty stdout, exit 0.

## Per-turn events log (JSONL, Codex only)

Path: `/tmp/codex-python-evidence/<session_id>.jsonl`

```jsonl
{"type": "edit",  "idx": 0, "file_path": "/tmp/foo.py", "tool": "Edit", "source": "tool",  "ts": "2026-05-20T13:12:40Z"}
{"type": "edit",  "idx": 1, "file_path": "/tmp/bar.py", "tool": "Bash", "source": "bash",  "ts": "2026-05-20T13:12:40Z"}
{"type": "check", "idx": 2, "name": "ruff",  "ok": true, "ts": "2026-05-20T13:12:41Z"}
{"type": "check", "idx": 3, "name": "mypy",  "ok": true, "ts": "2026-05-20T13:12:41Z"}
{"type": "check", "idx": 4, "name": "pytest","ok": true, "ts": "2026-05-20T13:12:42Z"}
```

`idx` is monotonic per turn, assigned at append time. Failed checks (`ok: false`) are not appended; their absence is the failure signal.

## Audit log (JSONL, both agents)

Paths:
- `~/.claude/hooks/python_evidence_gate_audit.jsonl`
- `~/.codex/hooks/python_evidence_audit.jsonl`

```jsonl
{"event": "pass",         "session": "...", "py_edits": [...], "pytest_required": false, "ts": "...", "hook_version": "v2"}
{"event": "block",        "session": "...", "cwd": "...", "py_edits": [...], "missing": [...], "ts": "...", "hook_version": "v2"}
{"event": "override_env", "session": "...", "ts": "...", "hook_version": "v2"}
{"event": "turn_reset",   "turn_id": "...", "ts": "...", "hook_version": "codex-v1"}
{"event": "post_tool",    "turn_id": "...", "tool": "...", "py_files_edited": [...], "ts": "...", "hook_version": "codex-v1"}
```

No file content, command output, or environment values are ever written. Sufficient for forensic reconstruction of gate decisions; insufficient for re-running the agent's work.
