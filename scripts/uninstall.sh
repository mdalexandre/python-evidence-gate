#!/usr/bin/env bash
# uninstall.sh — remove the python-evidence-gate registrations from
# ~/.claude/settings.json and ~/.codex/hooks.json. Hook scripts on disk are
# kept; the user can rm them manually if desired.

set -euo pipefail

remove_from_claude() {
  local f="${HOME}/.claude/settings.json"
  [ -f "$f" ] || return 0
  cp "$f" "${f}.bak-pre-uninstall-$(date +%Y%m%d%H%M%S)"
  python3 - "$f" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
s = json.loads(p.read_text())
stop = s.get("hooks", {}).get("Stop", [])
new_stop = []
removed = 0
for e in stop:
    hooks = [h for h in (e.get("hooks") or [])
             if "python_evidence_gate.py" not in (h.get("command") or "")]
    if hooks:
        e["hooks"] = hooks
        new_stop.append(e)
    else:
        removed += 1
if removed:
    s["hooks"]["Stop"] = new_stop
    p.write_text(json.dumps(s, indent=2) + "\n")
print(f"Claude: removed {removed} gate entry/entries")
PY
}

remove_from_codex() {
  local f="${HOME}/.codex/hooks.json"
  [ -f "$f" ] || return 0
  cp "$f" "${f}.bak-pre-uninstall-$(date +%Y%m%d%H%M%S)"
  python3 - "$f" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
s = json.loads(p.read_text())
removed = 0
for event_name in ("UserPromptSubmit", "PostToolUse", "Stop"):
    arr = s.get("hooks", {}).get(event_name, [])
    new_arr = []
    for e in arr:
        hooks = [h for h in (e.get("hooks") or [])
                 if "python_evidence_" not in (h.get("command") or "")]
        if hooks:
            e["hooks"] = hooks
            new_arr.append(e)
        else:
            removed += 1
    s["hooks"][event_name] = new_arr
if removed:
    p.write_text(json.dumps(s, indent=2) + "\n")
print(f"Codex: removed {removed} gate entry/entries")
PY
}

remove_from_claude
remove_from_codex
echo "Done. Hook scripts on disk are retained; rm them manually if desired."
