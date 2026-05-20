#!/usr/bin/env python3
"""UserPromptSubmit hook: reset the per-turn Python evidence log so each
fresh user prompt starts the gate from a clean slate."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from python_evidence_core import audit, reset_events, turn_id  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    if not isinstance(payload, dict):
        payload = {}
    if os.environ.get("PYTHON_EVIDENCE_GATE") == "0":
        return 0
    tid = turn_id(payload)
    reset_events(tid)
    audit({"event": "turn_reset", "turn_id": tid})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
