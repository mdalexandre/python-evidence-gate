#!/usr/bin/env bash
# install.sh — one-line installer for python-evidence-gate.
# Idempotent: re-running is safe. Backs up every modified config.
# Supports: Linux, macOS. Windows users see docs/WINDOWS.md.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TS="$(date +%Y%m%d%H%M%S)"
CLAUDE_DIR="${HOME}/.claude"
CODEX_DIR="${HOME}/.codex"

log() { printf '[install] %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

ensure_uv() {
  if have uv; then return 0; fi
  log "uv not found; installing via Astral installer"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1091
  [ -f "${HOME}/.local/bin/env" ] && . "${HOME}/.local/bin/env" || true
}

ensure_tools() {
  ensure_uv
  for tool in ruff mypy; do
    if have "$tool"; then
      log "$tool already present"
    else
      log "uv tool install $tool"
      uv tool install "$tool"
    fi
  done
  if have pytest; then
    log "pytest already present"
  else
    log "uv tool install pytest"
    uv tool install pytest
  fi
}

backup() {
  local f="$1"
  [ -f "$f" ] || return 0
  cp "$f" "${f}.bak-pre-python-evidence-${TS}"
  log "backed up $f"
}

install_claude() {
  if [ ! -f "${CLAUDE_DIR}/settings.json" ]; then
    log "Claude Code not detected (no ${CLAUDE_DIR}/settings.json); skipping"
    return 0
  fi
  log "installing Claude Code hook"
  mkdir -p "${CLAUDE_DIR}/hooks/tests"
  cp "${REPO_ROOT}/.claude/hooks/python_evidence_gate.py" "${CLAUDE_DIR}/hooks/"
  cp "${REPO_ROOT}/.claude/hooks/tests/test_python_evidence_gate.py" "${CLAUDE_DIR}/hooks/tests/"
  chmod +x "${CLAUDE_DIR}/hooks/python_evidence_gate.py"

  backup "${CLAUDE_DIR}/settings.json"
  python3 - "${CLAUDE_DIR}/settings.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
s = json.loads(p.read_text())
stop = s.setdefault("hooks", {}).setdefault("Stop", [])
already = any(
    any("python_evidence_gate.py" in (h.get("command") or "") for h in (e.get("hooks") or []))
    for e in stop
)
if not already:
    stop.append({
        "hooks": [{
            "type": "command",
            "command": "python3 " + str(pathlib.Path.home() / ".claude/hooks/python_evidence_gate.py"),
            "statusMessage": "python-evidence: ruff/mypy/pytest required",
            "timeout": 5
        }]
    })
    p.write_text(json.dumps(s, indent=2) + "\n")
    print("REGISTERED")
else:
    print("ALREADY-REGISTERED")
PY

  install_doctrine "${CLAUDE_DIR}/CLAUDE.md" "Python Tooling Loop" claude
}

install_codex() {
  if [ ! -f "${CODEX_DIR}/hooks.json" ]; then
    log "Codex CLI not detected (no ${CODEX_DIR}/hooks.json); skipping"
    return 0
  fi
  log "installing Codex hook trio"
  mkdir -p "${CODEX_DIR}/hooks/tests"
  cp "${REPO_ROOT}/.codex/hooks/python_evidence_core.py"        "${CODEX_DIR}/hooks/"
  cp "${REPO_ROOT}/.codex/hooks/python_evidence_userprompt.py"  "${CODEX_DIR}/hooks/"
  cp "${REPO_ROOT}/.codex/hooks/python_evidence_postuse.py"     "${CODEX_DIR}/hooks/"
  cp "${REPO_ROOT}/.codex/hooks/python_evidence_stop.py"        "${CODEX_DIR}/hooks/"
  cp "${REPO_ROOT}/.codex/hooks/tests/test_python_evidence.py"  "${CODEX_DIR}/hooks/tests/"
  chmod +x "${CODEX_DIR}/hooks/python_evidence_userprompt.py" \
           "${CODEX_DIR}/hooks/python_evidence_postuse.py" \
           "${CODEX_DIR}/hooks/python_evidence_stop.py"

  backup "${CODEX_DIR}/hooks.json"
  python3 - "${CODEX_DIR}/hooks.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
s = json.loads(p.read_text())
hooks = s.setdefault("hooks", {})
home = pathlib.Path.home()
added = []

def append(event, matcher, script, status):
    arr = hooks.setdefault(event, [])
    if any(any(script in (h.get("command") or "") for h in (e.get("hooks") or [])) for e in arr):
        return False
    entry = {"hooks": [{
        "type": "command",
        "command": f"/usr/bin/python3 {home}/.codex/hooks/{script}",
        "timeout": 5,
        "statusMessage": status,
    }]}
    if matcher:
        entry["matcher"] = matcher
    arr.append(entry)
    return True

if append("UserPromptSubmit", None, "python_evidence_userprompt.py",
          "python-evidence: reset per-turn log"): added.append("UserPromptSubmit")
if append("PostToolUse",
          "exec_command|apply_patch|Bash|Write|Edit|MultiEdit|NotebookEdit",
          "python_evidence_postuse.py",
          "python-evidence: accumulate evidence"): added.append("PostToolUse")
if append("Stop", None, "python_evidence_stop.py",
          "python-evidence: ruff/mypy/pytest required"): added.append("Stop")

p.write_text(json.dumps(s, indent=2) + "\n")
print(f"REGISTERED: {added or 'nothing (already in place)'}")
PY

  install_doctrine "${CODEX_DIR}/AGENTS.md" "Python Tooling Loop" codex
}

install_doctrine() {
  local file="$1" header="$2" flavor="$3"
  [ -f "$file" ] || { log "$file not found; skipping doctrine append"; return 0; }
  if grep -q "## ${header}" "$file"; then
    log "doctrine section already present in $file; skipping"
    return 0
  fi
  backup "$file"
  cat "${REPO_ROOT}/docs/doctrine.${flavor}.md" >> "$file"
  log "appended doctrine to $file"
}

verify() {
  log "running test suites"
  if have ruff && have mypy && have pytest; then
    (cd "${REPO_ROOT}" \
      && ruff check .claude/hooks/python_evidence_gate.py \
                    .codex/hooks/python_evidence_core.py \
                    .codex/hooks/python_evidence_postuse.py \
                    .codex/hooks/python_evidence_stop.py \
                    .codex/hooks/python_evidence_userprompt.py \
      && mypy --ignore-missing-imports \
              .claude/hooks/python_evidence_gate.py \
              .codex/hooks/python_evidence_core.py \
              .codex/hooks/python_evidence_postuse.py \
              .codex/hooks/python_evidence_stop.py \
              .codex/hooks/python_evidence_userprompt.py \
      && pytest -q .claude/hooks/tests .codex/hooks/tests)
  else
    log "ruff/mypy/pytest not all present; skipping verification"
  fi
}

main() {
  ensure_tools
  install_claude
  install_codex
  verify
  log "done"
  log "audit logs:"
  log "  ${CLAUDE_DIR}/hooks/python_evidence_gate_audit.jsonl (if Claude installed)"
  log "  ${CODEX_DIR}/hooks/python_evidence_audit.jsonl       (if Codex installed)"
  log "override: export PYTHON_EVIDENCE_GATE=0"
}

main "$@"
