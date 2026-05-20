"""Shared core for the Codex Python evidence gate.

Two-phase enforcement on Codex (which has no transcript_path on Stop):
  - UserPromptSubmit hook resets the per-turn events log.
  - PostToolUse hook appends edit/check events to the events log.
  - Stop hook reads the events log and applies the v2 gate.

This module is the shared library; the three hook entry points live alongside.

Public API
----------
- HOOK_VERSION, AUDIT_LOG, EVENTS_DIR, TURN_BOUNDARY_FILE
- turn_id(payload) -> str
- session_events_path(turn_id) -> Path
- audit(record)
- split_segments(command) -> list[list[str]]
- matches_check(argv, check) -> bool
- detect_bash_py_edits(command) -> list[str]
- detect_apply_patch_py_edits(patch_body) -> list[str]
- result_is_failure(tool_response) -> bool
- repo_has_tests(cwd) -> bool
- evaluate(events, pytest_required) -> (missing, edited_files, bash_edits, last_edit_idx)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import time
from pathlib import Path

HOOK_VERSION = "codex-v1"
AUDIT_LOG = Path.home() / ".codex" / "hooks" / "python_evidence_audit.jsonl"
EVENTS_DIR = Path("/tmp/codex-python-evidence")

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

APPLY_PATCH_FILE_RE = re.compile(
    r"^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(\S+)$", re.MULTILINE
)

HEREDOC_RE = re.compile(
    r"<<-?\s*([\"']?)([A-Za-z_][A-Za-z0-9_]*)\1\s*\n.*?\n\s*\2(?:\s|$)",
    re.DOTALL,
)

TEST_SKIP_DIRS = {
    ".venv", "venv", "env", ".env", "node_modules", ".git", "__pycache__",
    ".tox", ".nox", "dist", "build", "site-packages", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".cache",
}


def turn_id(payload: dict | None) -> str:
    """Stable per-turn identifier. Falls back to 'current' when no scope id is
    present in stdin (single-session usage)."""
    if isinstance(payload, dict):
        for key in ("session_id", "sessionId", "turn_id", "conversation_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return re.sub(r"[^A-Za-z0-9._-]", "_", value)[:64]
    env_value = os.environ.get("CODEX_SESSION_ID")
    if env_value:
        return re.sub(r"[^A-Za-z0-9._-]", "_", env_value)[:64]
    return "current"


def session_events_path(tid: str) -> Path:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    return EVENTS_DIR / f"{tid}.jsonl"


def audit(record: dict) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record["hook_version"] = HOOK_VERSION
        with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass


def append_event(tid: str, event: dict) -> None:
    try:
        path = session_events_path(tid)
        event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except Exception:
        pass


def read_events(tid: str) -> list[dict]:
    path = session_events_path(tid)
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception:
        pass
    return out


def reset_events(tid: str) -> None:
    try:
        path = session_events_path(tid)
        if path.exists():
            path.unlink()
    except Exception:
        pass


def strip_heredocs(command: str) -> str:
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
    if not argv:
        return argv
    while argv and argv[0] == "env":
        argv = argv[1:]
        while argv and "=" in argv[0] and not argv[0].startswith("-"):
            argv = argv[1:]
    if not argv:
        return argv
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
    if not command:
        return []
    stripped = strip_heredocs(command)
    found: list[str] = []
    for rx in PY_MUTATE_RE_LIST:
        for m in rx.finditer(stripped):
            found.append(m.group(1))
    return found


def detect_apply_patch_py_edits(patch_body: str) -> list[str]:
    if not patch_body:
        return []
    return [m.group(1) for m in APPLY_PATCH_FILE_RE.finditer(patch_body)
            if m.group(1).endswith(".py")]


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
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return ""


def result_is_failure(tool_response) -> bool:
    """Detect failure from a PostToolUse tool_response. Accepts dict shapes
    seen across Codex and Claude bridge transports."""
    if tool_response is None:
        return False
    if isinstance(tool_response, dict):
        if tool_response.get("is_error") is True:
            return True
        exit_code = tool_response.get("exit_code")
        if isinstance(exit_code, int) and exit_code != 0:
            return True
        for key in ("output", "content", "stdout", "stderr", "text"):
            body = tool_response.get(key)
            if body and isinstance(body, (str, list)):
                txt = text_of(body)
                if re.match(r"\s*Exit code\s+\d+\b", txt or ""):
                    return True
    elif isinstance(tool_response, str):
        if re.match(r"\s*Exit code\s+\d+\b", tool_response):
            return True
    return False


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


def evaluate(
    events: list[dict], pytest_required: bool,
) -> tuple[list[str], list[str], list[str], int]:
    """Return (missing, edited_files, bash_edits, last_edit_idx)."""
    edits = [e for e in events if e.get("type") == "edit"]
    checks = [e for e in events if e.get("type") == "check"]
    edited_files = sorted({str(e.get("file_path") or "") for e in edits if e.get("file_path")})
    bash_edits = sorted({str(e.get("file_path") or "") for e in edits
                         if e.get("source") == "bash" and e.get("file_path")})
    if not edits:
        return [], edited_files, bash_edits, -1
    last_edit_idx = max(int(e.get("idx", 0)) for e in edits)
    has = {"ruff": False, "mypy": False, "pytest": False}
    for c in checks:
        name = c.get("name")
        idx = int(c.get("idx", 0))
        ok = bool(c.get("ok"))
        if name in has and ok and idx > last_edit_idx:
            has[name] = True
    missing: list[str] = []
    if not has["ruff"]:
        missing.append("ruff")
    if not has["mypy"]:
        missing.append("mypy")
    if pytest_required and not has["pytest"]:
        missing.append("pytest")
    return missing, edited_files, bash_edits, last_edit_idx
