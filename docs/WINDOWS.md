# Windows install

Two paths. WSL2 is recommended; native PowerShell is best-effort.

## Path A: WSL2 (recommended)

1. Install WSL2 with Ubuntu 22.04 or later. Microsoft docs at `https://learn.microsoft.com/windows/wsl/install`.
2. Inside the WSL2 shell, the Linux install path applies unchanged:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/mdalexandre/python-evidence-gate/main/install.sh | bash
   ```
3. Install Claude Code and Codex CLI inside the WSL2 environment, not on Windows.

## Path B: Native PowerShell (best-effort)

The hook code itself is cross-platform Python and will run on Windows; the bash installer will not. Manual install:

1. Install `uv`:
   ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```
2. Install ruff and mypy:
   ```powershell
   uv tool install ruff
   uv tool install mypy
   uv tool install pytest
   ```
3. Copy the hook scripts manually:
   ```powershell
   New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\hooks\tests"
   New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\hooks\tests"
   Copy-Item ".claude\hooks\python_evidence_gate.py" "$env:USERPROFILE\.claude\hooks\"
   Copy-Item ".claude\hooks\tests\test_python_evidence_gate.py" "$env:USERPROFILE\.claude\hooks\tests\"
   Copy-Item ".codex\hooks\python_evidence_*.py" "$env:USERPROFILE\.codex\hooks\"
   Copy-Item ".codex\hooks\tests\test_python_evidence.py" "$env:USERPROFILE\.codex\hooks\tests\"
   ```
4. Edit `~/.claude/settings.json` and `~/.codex/hooks.json` manually to register the hooks. See the `install.sh` python heredoc for the exact JSON structure to insert.

## Known Windows caveats

- The Codex hook registration uses an absolute Python path on Linux (`/usr/bin/python3`). On Windows you would need to substitute the path to your Python installation (likely `C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe`).
- The Bash-side `.py` mutation detection regex still works on Windows for tool calls invoked via WSL2 or via a Bash-compatible shell. PowerShell-side mutations (`Set-Content`, `Out-File`) are not detected by the regex; this is a known gap.
- `chmod +x` is a no-op on Windows; the hook scripts are invoked via Python interpreter, not directly.
- Audit log path on Windows: `%USERPROFILE%\.claude\hooks\python_evidence_gate_audit.jsonl` etc.

## CI status

GitHub Actions CI for `windows-latest` is deferred to v1.1. Until then, Windows support is community-tested. Reports of breakage are welcome via GitHub issues.
