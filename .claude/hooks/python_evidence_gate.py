#!/usr/bin/env python3
"""Stop hook v2: refuse turn end when Python files were edited this turn without
ruff/mypy/(pytest) evidence that ran successfully AFTER the edit.

v2 changes from v1
------------------
- Tokenized shell parsing via shlex. Tokens inside string literals, heredoc
  bodies, comments, and echo labels no longer count as invocations.
- Exit-code awareness: a check counts only if its tool_result.is_error is not
  True. Whole-pipeline granularity (chained `&&` failures void the chain).
- Order preservation: a check counts only if it ran AFTER the most recent .py
  edit in transcript order.
- Bash-side .py mutation detection: `> foo.py`, `>> foo.py`, `tee foo.py`,
  `sed -i ... foo.py` count as edits.
- `ruff format` no longer counts; doctrine requires `ruff check`.
- `uv run ruff --version` and other wrapped version/help calls correctly
  excluded after argv normalization.
- repo_has_tests skips .venv, node_modules, .git, __pycache__, .tox,
  dist, build, site-packages.

Contract
--------
- Reads Claude Code Stop event JSON on stdin.
- Walks transcript from the last fresh user message.
- Blocks Stop via {"decision": "block", "reason": "..."} on stdout when
  required evidence is missing.
- Loop-safe: stop_hook_active=True -> exit 0.
- Override: PYTHON_EVIDENCE_GATE=0 -> exit 0 (audit logged).
- Fail-open on internal error.
- Audit log: ~/.claude/hooks/python_evidence_gate_audit.jsonl
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

AUDIT_LOG = Path.home() / ".claude" / "hooks" / "python_evidence_gate_audit.jsonl"
HOOK_VERSION = "v2"

CONNECTORS = {";", "&&", "||", "|", "&"}
INSTALL_HEADS = {"pip", "pipx", "brew", "apt", "apt-get", "conda", "yum", "dnf"}
DISCOVERY_HEADS = {"command", "which", "type", "whereis", "whatis"}

UV_RUN_FLAGS_WITH_VALUE = {
    "--python", "-p", "--with", "--with-requirements", "--with-editable",
    "--project", "--directory", "--extra", "--no-extra", "--group",
    "--module", "-m", "--script", "--package",
}

PY_MUTATE_RE_LIST = [
    re.compile(r">>?\s*\"?([^\s|;&><\"]+\.py)\b"),
    re.compile(r"\btee\s+(?:-a\s+)?\"?([^\s|;&\"]+\.py)\b"),
    re.compile(r"\bsed\s+-i[^\s]*\s+.*?\"?([^\s|;&\"]+\.py)\b"),
]

HEREDOC_RE = re.compile(
    r"<<-?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1\s*\n.*?\n\s*\2(?:\s|$)",
    re.DOTALL,
)

TEST_SKIP_DIRS = {
    ".venv", "venv", "env", ".env", "node_modules", ".git", "__pycache__",
    ".tox", ".nox", "dist", "build", "site-packages", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".cache",
}


def audit(record: dict) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record["hook_version"] = HOOK_VERSION
        with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass


def strip_heredocs(command: str) -> str:
    """Remove heredoc bodies so their contents do not contribute tokens."""
    if "<<" not in command:
        return command
    out = command
    while True:
        new = HEREDOC_RE.sub("\n", out)
        if new == out:
            return new
        out = new


def normalize_separators(command: str) -> str:
    """Collapse line continuations and convert unquoted newlines to `;` so
    each shell statement on its own line becomes a separate segment."""
    command = re.sub(r"\\\n", " ", command)
    out: list[str] = []
    in_single = in_double = False
    escape = False
    for c in command:
        if escape:
            out.append(c)
            escape = False
            continue
        if c == "\\" and not in_single:
            escape = True
            out.append(c)
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            out.append(c)
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            out.append(c)
            continue
        if c == "\n" and not in_single and not in_double:
            out.append(";")
            continue
        out.append(c)
    return "".join(out)


def split_segments(command: str) -> list[list[str]]:
    """Tokenize a shell command into argv segments separated by `;`, `&&`,
    `||`, `|`, `&`. Heredoc bodies are stripped first. Unquoted newlines are
    treated as `;`. Quotes are respected."""
    if not command:
        return []
    stripped = normalize_separators(strip_heredocs(command))
    try:
        tokens = shlex.split(stripped, posix=True, comments=True)
    except ValueError:
        return []
    segments: list[list[str]] = []
    current: list[str] = []
    splitter = re.compile(r"(\&\&|\|\||;|\||\&)")
    for tok in tokens:
        parts = splitter.split(tok)
        for p in parts:
            if not p:
                continue
            if p in CONNECTORS:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(p)
    if current:
        segments.append(current)
    return segments


def normalize_argv(argv: list[str]) -> list[str]:
    """Strip wrappers: `env VAR=val ...`, `uv run [--flags] ...`,
    `python[3] -m MODULE ...` -> argv starting at the real command."""
    if not argv:
        return argv
    # env VAR=val ... wrappers
    while argv and argv[0] == "env":
        argv = argv[1:]
        while argv and "=" in argv[0] and not argv[0].startswith("-"):
            argv = argv[1:]
    if not argv:
        return argv
    # uv run [flags] CHECK ...
    if len(argv) >= 2 and argv[0] == "uv" and argv[1] == "run":
        i = 2
        while i < len(argv):
            tok = argv[i]
            if tok.startswith("--") or tok.startswith("-"):
                if "=" in tok:
                    i += 1
                elif tok in UV_RUN_FLAGS_WITH_VALUE:
                    i += 2
                else:
                    i += 1
            else:
                break
        argv = argv[i:]
    if not argv:
        return argv
    # python[3] -m MODULE ...
    if len(argv) >= 3 and argv[0] in ("python", "python3") and argv[1] == "-m":
        argv = argv[2:]
    return argv


def is_install_or_discovery(argv: list[str]) -> bool:
    if not argv:
        return True
    head = argv[0]
    if head in INSTALL_HEADS and len(argv) >= 2 and argv[1] in ("install", "add"):
        return True
    if head == "uv" and len(argv) >= 2 and argv[1] in ("add", "remove", "sync", "lock"):
        return True
    if (head == "uv" and len(argv) >= 3 and argv[1] == "tool"
            and argv[2] in ("install", "uninstall", "upgrade")):
        return True
    if (head == "uv" and len(argv) >= 3 and argv[1] == "pip"
            and argv[2] in ("install", "uninstall", "sync")):
        return True
    if head in DISCOVERY_HEADS:
        return True
    return False


def is_help_or_version(argv: list[str]) -> bool:
    return any(tok in ("--version", "--help", "-V", "-h") for tok in argv[1:])


def matches_check(argv: list[str], check: str) -> bool:
    """Return True if `argv` (raw, possibly with wrappers) is an invocation of
    `check`, not an install/discovery/help/version call."""
    if not argv:
        return False
    if is_install_or_discovery(argv):
        return False
    normalized = normalize_argv(list(argv))
    if not normalized:
        return False
    if is_install_or_discovery(normalized):
        return False
    if is_help_or_version(normalized):
        return False
    head = normalized[0]
    rest = normalized[1:]
    if head != check:
        if check == "mypy" and head == "dmypy":
            return True
        return False
    if check == "ruff":
        for tok in rest:
            if tok.startswith("-"):
                continue
            return tok == "check"
        return False
    return True


def detect_bash_py_edits(command: str) -> list[str]:
    """Return list of .py file paths the Bash command appears to mutate."""
    if not command:
        return []
    stripped = strip_heredocs(command)
    found: list[str] = []
    for rx in PY_MUTATE_RE_LIST:
        for m in rx.finditer(stripped):
            found.append(m.group(1))
    return found


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, dict):
                if isinstance(b.get("text"), str):
                    parts.append(b["text"])
                elif isinstance(b.get("content"), str):
                    parts.append(b["content"])
        return "\n".join(parts)
    return ""


def result_is_failure(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("is_error") is True:
        return True
    body = text_of(result.get("content"))
    return bool(re.match(r"\s*Exit code\s+\d+\b", body or ""))


def walk_turn(
    transcript_path: str,
) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, bool]]]:
    """Return two ordered lists, edit_events and check_events:
        edit_events: (file_path, index, source) where source in {tool, bash}
        check_events: (check_name, index, succeeded)
    """
    edits: list[tuple[str, int, str]] = []
    checks: list[tuple[str, int, bool]] = []
    if not transcript_path:
        return edits, checks
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except Exception:
        return edits, checks

    last_user_idx = -1
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        raw_msg = rec.get("message")
        msg = raw_msg if isinstance(raw_msg, dict) else {}
        role = msg.get("role") or rec.get("role") or rec.get("type")
        if role != "user":
            continue
        content = msg.get("content", rec.get("content"))
        if isinstance(content, list):
            blocks = [b for b in content if isinstance(b, dict)]
            if blocks and all(b.get("type") == "tool_result" for b in blocks):
                continue
        last_user_idx = i
    start = last_user_idx if last_user_idx >= 0 else 0

    pending_bash: dict[str, tuple[int, str]] = {}

    for i, raw in enumerate(lines[start:], start=start):
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        raw_msg = rec.get("message")
        msg = raw_msg if isinstance(raw_msg, dict) else {}
        content = msg.get("content", rec.get("content"))
        if not isinstance(content, list):
            continue
        for blk in content:
            if not isinstance(blk, dict):
                continue
            btype = blk.get("type")
            if btype == "tool_use":
                tool_name = blk.get("name") or ""
                raw_inp = blk.get("input")
                inp: dict = raw_inp if isinstance(raw_inp, dict) else {}
                tool_use_id = blk.get("id") or ""
                if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                    fp = inp.get("file_path") or inp.get("notebook_path") or ""
                    if isinstance(fp, str) and fp.endswith(".py"):
                        edits.append((fp, i, "tool"))
                elif tool_name == "Bash":
                    cmd = inp.get("command") or ""
                    if isinstance(cmd, str):
                        for fp in detect_bash_py_edits(cmd):
                            edits.append((fp, i, "bash"))
                        pending_bash[tool_use_id] = (i, cmd)
            elif btype == "tool_result":
                tool_use_id = blk.get("tool_use_id") or ""
                if tool_use_id not in pending_bash:
                    continue
                use_idx, cmd = pending_bash.pop(tool_use_id)
                failed = result_is_failure(blk)
                if failed:
                    continue
                for segment in split_segments(cmd):
                    for check_name in ("ruff", "mypy", "pytest"):
                        if matches_check(segment, check_name):
                            checks.append((check_name, use_idx, True))
    return edits, checks


def repo_has_tests(cwd: str) -> bool:
    try:
        root = Path(cwd or ".")
        if not root.exists():
            return False
        if (root / "tests").is_dir() or (root / "test").is_dir():
            return True
        py_toml = root / "pyproject.toml"
        if py_toml.is_file():
            try:
                txt = py_toml.read_text(encoding="utf-8", errors="ignore")
                if "[tool.pytest" in txt:
                    return True
            except Exception:
                pass
        scanned = 0
        max_depth = 4
        root_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - root_depth
            if depth > max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in TEST_SKIP_DIRS and not d.startswith(".")]
            for f in filenames:
                if f.startswith("test_") and f.endswith(".py"):
                    return True
                if f.endswith("_test.py"):
                    return True
                scanned += 1
                if scanned > 5000:
                    return False
    except Exception:
        pass
    return False


def main() -> int:
    payload: dict
    try:
        raw = sys.stdin.read()
        parsed = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    if not isinstance(parsed, dict):
        return 0
    payload = parsed
    if payload.get("stop_hook_active") is True:
        return 0

    if os.environ.get("PYTHON_EVIDENCE_GATE") == "0":
        audit({"event": "override_env", "session": payload.get("session_id")})
        return 0

    transcript = str(payload.get("transcript_path") or "")
    cwd = str(payload.get("cwd") or os.getcwd())

    edits, checks = walk_turn(transcript)
    if not edits:
        return 0

    last_edit_idx = max(idx for _, idx, _ in edits)
    has_ruff = any(name == "ruff" and idx > last_edit_idx and ok for name, idx, ok in checks)
    has_mypy = any(name == "mypy" and idx > last_edit_idx and ok for name, idx, ok in checks)
    has_pytest = any(name == "pytest" and idx > last_edit_idx and ok for name, idx, ok in checks)

    pytest_required = repo_has_tests(cwd)
    missing: list[str] = []
    if not has_ruff:
        missing.append("ruff")
    if not has_mypy:
        missing.append("mypy")
    if pytest_required and not has_pytest:
        missing.append("pytest")

    edited_files = sorted(set(fp for fp, _, _ in edits))
    bash_edits = sorted(set(fp for fp, _, src in edits if src == "bash"))

    if not missing:
        audit({
            "event": "pass",
            "session": payload.get("session_id"),
            "py_edits": edited_files,
            "bash_py_edits": bash_edits,
            "pytest_required": pytest_required,
        })
        return 0

    head = edited_files[:4]
    files_preview = ", ".join(head) + ("..." if len(edited_files) > 4 else "")
    suggest_cmd = " && ".join(
        f"uv run {m}{' check' if m == 'ruff' else ''} <changed_files>" for m in missing
    )
    notes: list[str] = []
    if pytest_required and "pytest" in missing:
        notes.append("Pytest is required because tests exist in this repo.")
    if bash_edits:
        notes.append(f"Bash-side .py mutations were also detected: {', '.join(bash_edits[:3])}.")
    notes.append("Checks must succeed (is_error=false) AND run after the most recent .py edit.")
    notes_str = " " + " ".join(notes) if notes else ""

    reason = (
        f"Python evidence gate v2: this turn edited {len(edited_files)} "
        f"Python file(s) ({files_preview}) without successful {', '.join(missing)} "
        f"evidence after the last edit. Run {suggest_cmd} and report the "
        f"results before ending the turn.{notes_str} "
        "Override (owner only): export PYTHON_EVIDENCE_GATE=0."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    audit({
        "event": "block",
        "session": payload.get("session_id"),
        "cwd": cwd,
        "py_edits": edited_files,
        "bash_py_edits": bash_edits,
        "missing": missing,
        "pytest_required": pytest_required,
        "last_edit_idx": last_edit_idx,
        "checks_seen": [{"name": n, "idx": i, "ok": ok} for n, i, ok in checks],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
