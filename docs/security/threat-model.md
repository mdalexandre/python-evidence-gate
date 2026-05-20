# Threat Model (STRIDE)

Authority: Shostack, *Threat Modeling: Designing for Security* (Wiley, 2014).

This document is the STRIDE analysis for the python-evidence-gate. The corresponding chapter in the SPR is §4.8.

## Trust boundary

The gate trusts the agent's hook stdin payload (`tool_name`, `tool_input`, `tool_response`) as faithful. If the agent is compromised — for example, an attacker controls the model and can fabricate `is_error: false` on a failed pytest — the gate cannot detect that and will not defend against it. The gate is a **guardrail on the agent's output discipline**, not a security control against an adversarial agent.

The gate does **not** trust:

- Text inside `tool_input.command` strings (passed to `shlex.split` only, never to a shell).
- Text inside the assistant's `last_assistant_message` (Codex Stop event; used only by the existing `asymmetric_stop_return_gate.py`, not by this gate).
- Contents of files the agent edits.
- Arbitrary env vars except `PYTHON_EVIDENCE_GATE`.

## Components

| ID | Component | Trust zone |
|---|---|---|
| C1 | `python_evidence_gate.py` (Claude Stop hook) | Agent process |
| C2 | `python_evidence_core.py` + the three Codex hook wrappers | Agent process |
| C3 | Per-turn events log at `/tmp/codex-python-evidence/<sid>.jsonl` | Same UID as user |
| C4 | Audit log at `~/.claude/hooks/python_evidence_gate_audit.jsonl` and `~/.codex/hooks/python_evidence_audit.jsonl` | Same UID as user |
| C5 | `install.sh` (one-time installer) | User shell, may invoke `sudo` only for `uv` install (Astral installer's choice) |
| C6 | `~/.claude/settings.json` and `~/.codex/hooks.json` (modified by C5) | Same UID as user |
| C7 | Backup files (`*.bak-pre-python-evidence-<ts>`) | Same UID as user |

## STRIDE per element

### C1: Claude Stop hook

| Threat | Risk | Mitigation |
|---|---|---|
| **S**poofing | An attacker convinces the gate that `ruff` ran when it did not, by injecting fake transcript entries. | Within trust boundary: tokenizer rejects literal strings inside heredoc bodies and echoed labels (`echo "=== ruff check ==="` does not count). Outside trust boundary: a compromised agent can forge transcript events; this is acknowledged as out of scope. |
| **T**ampering | An attacker modifies the transcript JSONL between the agent writing it and the hook reading it. | The transcript file is in the agent's own data directory (`~/.claude/projects/...`). An attacker with that level of access already exceeds the gate's threat scope. |
| **R**epudiation | Owner claims the gate blocked a turn it did not block, or vice versa. | Every gate decision (pass, block, override_env) plus per-PostToolUse `post_tool` and per-UserPromptSubmit `turn_reset` events is written to the audit log with ISO-8601 UTC timestamp and hook version. The log is append-only by file mode but NOT cryptographically chained or signed; tamper detection beyond filesystem ACLs is out of scope. |
| **I**nformation disclosure | The gate echoes file content, env values, or command output in the block reason or audit log. | Block reason contains only: count of edited files, up to 4 file path samples, missing check names, override instructions. Audit log records the same plus session id. No content, no env. |
| **D**enial of service | A pathological transcript (e.g., 1 GB JSONL) hangs the hook. | Settings.json declares `timeout: 5` seconds. `os.walk` is bounded to depth 4 and 5000 files scanned. Observed max latency: ~80 ms on 514 KB transcript. |
| **E**levation of privilege | The hook acquires capability beyond the user. | Runs as the user, same UID as the agent. No `setuid`, no `sudo`, no capability acquisition. |

### C2: Codex hook trio

Same STRIDE analysis as C1 with two additional considerations:

- **Tampering of the per-turn events log (C3)** by another process running as the same user. Mitigation: documented as in-scope of the user's local trust boundary. The events log lives under `/tmp/codex-python-evidence-<euid>/` (v1.1: UID-scoped to avoid cross-user collision). The hook creates the directory with mode 0700, checks owner via `lstat`, refuses to use it if it is a symlink, and opens log files with `O_NOFOLLOW` to defeat symlink/precreation attacks on `/tmp`. The log is short-lived (truncated each `UserPromptSubmit`).
- **Spoofing via session id collision**: when `session_id` is absent from stdin and two parallel Codex sessions both fall back to `"current"`, they share an events log. Mitigation: documented in SPR §8.2; recommended workaround is `export CODEX_SESSION_ID=...` per shell.

### C3: Per-turn events log

| Threat | Risk | Mitigation |
|---|---|---|
| **T**ampering | Another user-owned process appends fake `check` events. | Out of scope: an attacker with shell access to this user account already exceeds the gate. |
| **I**nformation disclosure | Events log leaks intent. | The log contains only file paths (`.py` only), tool names (`Edit`/`Bash`/etc.), and check names. No content. |
| **D**enial of service | Disk fills up with `/tmp/codex-python-evidence/*.jsonl`. | One file per turn; truncated at `UserPromptSubmit`. Bounded by user's turn count. |

### C4: Audit logs

Append-only by design. No rotation in v1; documented as v2 candidate. Manual rotation via `logrotate` is the recommended workaround.

### C5: `install.sh`

| Threat | Risk | Mitigation |
|---|---|---|
| **T**ampering | A man-in-the-middle modifies `install.sh` before the user pipes it to bash. | The `curl \| bash` pattern is documented and carries known supply-chain risk. The installer's preamble explicitly recommends an audit-first variant (`curl ... -o /tmp/peg.sh && less /tmp/peg.sh && bash /tmp/peg.sh`) as the safe default. Release signing has NOT been set up for v1.0/v1.1 and does not protect the raw-`main` `curl \| bash` path. v1.2 candidate: signed release tarballs + GPG-verified install script. |
| **E**levation of privilege | `install.sh` invokes `sudo`. | It does not. The only sudo-capable substep is the Astral uv installer, which the user runs only if `uv` is absent. We document this explicitly. |

### C6: Modifications to `settings.json` / `hooks.json`

| Threat | Risk | Mitigation |
|---|---|---|
| **T**ampering | Install script corrupts the config and the agent can no longer launch. | Every modification is preceded by a timestamped backup (FR-NFR-R-3). v1.1: the installer runs `python3 -m json.tool` against each modified config (`~/.claude/settings.json`, `~/.codex/hooks.json`) and aborts with a `restore-from-backup` instruction if the post-write file is not valid JSON. |
| **R**epudiation | Owner cannot tell whether the gate was registered by this tool or another. | Hook entries carry a distinct `statusMessage` ("python-evidence: …") and `command` path. The backup filename includes the install timestamp. |

## Supply chain (Shostack §159 "Mitigate Supply Chain Attack Risks")

The gate depends on:

- Python stdlib (trust by user choice of interpreter).
- `uv`, `ruff`, `mypy`, `pytest` — installer pins specific versions (v1.1): `ruff@0.15.13`, `mypy@2.1.0`, `pytest@9.0.3`. Pins are overridable via `RUFF_PIN` / `MYPY_PIN` / `PYTEST_PIN` env vars at install time. Bump after reviewing upstream changelogs.
- The user's agent CLI (Claude Code or Codex) — out of scope.

No transitive Python dependencies; the gate uses no third-party packages.

## Out-of-scope

- Adversarial AI agents.
- Attackers with shell access to the user account.
- Modifications to the agent CLI binaries themselves.
- Privileged-process exploits in the user's OS.

## Reference

For the full project context, see [SPR-python-evidence-gate.md](../../SPR-python-evidence-gate.md) §4.8 "Threat model (STRIDE)".
