# Requirements

Distilled from SPR Chapter 3.

## Functional requirements

| ID | Summary | Acceptance |
|---|---|---|
| FR-1 | Detect .py edits via Edit/Write/MultiEdit/NotebookEdit | Audit log contains edit event with file_path, tool, source=tool |
| FR-2 | Detect .py mutation via shell redirects, tee, sed -i | Audit log contains edit event with source=bash for known mutation patterns |
| FR-3 | Parse apply_patch payloads for *.py file paths (Codex) | apply_patch with `*** Update File: path.py` emits an edit event |
| FR-4 | Recognize ruff check, reject ruff format and bare ruff | ruff format does not satisfy gate; ruff check does |
| FR-5 | Recognize mypy and dmypy | Either invocation satisfies the mypy slot |
| FR-6 | Recognize pytest (incl. python -m pytest) | Both forms satisfy the pytest slot |
| FR-7 | Normalize env, uv run [flags], python -m wrappers | Wrapped invocations match; wrapped --version excluded |
| FR-8 | Reject checks that ran before the last .py edit | Pre-edit ruff/mypy/pytest do not count |
| FR-9 | Reject failed-pipeline checks (whole pipeline rule) | is_error=true or Exit code N prefix voids the segment |
| FR-10 | Pytest required only when repo has tests | tests/ or test/ dir, or [tool.pytest...] in pyproject.toml, or test_*.py / *_test.py |
| FR-11 | Block Stop with structured reason | stdout JSON: decision=block, reason names missing checks, suggests command, lists override |
| FR-12 | PYTHON_EVIDENCE_GATE=0 env override | Override exits clean and audit-logs override_env |
| FR-13 | stop_hook_active loop-safe | Hook exits clean inside continuation |
| FR-14 | UserPromptSubmit resets per-turn log (Codex) | Fresh prompt starts with empty events log |
