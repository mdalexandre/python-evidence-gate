# Risk Register

Derived from `risks`.

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | Vendor schema change: new edit tool not in EDIT_TOOLS | 4 | 4 | CI smoke against latest CLIs; Bash mutation fallback; issue template captures tool name |
| R-2 | Vendor schema change: tool_response loses is_error | 3 | 4 | result_is_failure defensively checks is_error, exit_code, content prefix |
| R-3 | Regex false-positive on filenames in prose | 2 | 2 | argv[0] head-position check; tests cover echo/heredoc cases |
| R-4 | Regex false-negative on exotic .py mutation paths | 3 | 3 | Documented v3 work; pytest runtime path satisfies gate |
| R-5 | Concurrency: parallel Codex sessions share `current` log | 2 | 3 | CODEX_SESSION_ID per shell; v2 PPID-based scoping |
| R-6 | Hook timeout on pathological transcripts | 1 | 3 | os.walk depth 4 + 5000 file cutoff |
| R-7 | Permission error writing /tmp/codex-python-evidence/ | 1 | 3 | mkdir parents=True, exist_ok=True; OSError fall-through fail-open |
| R-8 | Audit log unbounded growth | 2 | 2 | Documented manual rotation; v2 built-in rotation |
| R-9 | Supply chain: malicious typosquatted ruff/mypy/pytest wheel | 1 | 5 | Install via official uv tool install; README recommends version pin |
| R-10 | License contamination from contributors | 2 | 4 | DCO required; CI rejects unsigned PRs |
| R-11 | Vendor deprecates hooks subsystem | 1 | 5 | No announced deprecation; portable design; ~1 day re-port |
| R-12 | Documentation drift between SPR and code | 3 | 2 | SPR is authoritative; PRs touching code require SPR update at review |
