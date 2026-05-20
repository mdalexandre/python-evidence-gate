# Contributing

Thank you for considering a contribution. This project values:

- A complete, working hook on every release. No half-built features.
- Tests for every new requirement or bug fix.
- Documentation kept in sync with code. The SPR is the spec.

## Before you start

1. Read [`SPR-python-evidence-gate.md`](../SPR-python-evidence-gate.md). It is the authoritative design document.
2. Read [`docs/security/threat-model.md`](security/threat-model.md). Security-relevant changes require a threat-model update.
3. Open an issue describing the problem you intend to solve, before writing code.

## Development workflow

```bash
git clone https://github.com/mdalexandre/python-evidence-gate
cd python-evidence-gate

# Install dev tools
uv tool install ruff
uv tool install mypy
uv tool install pytest

# Run the full verification locally
make verify

# Run just the tests
make test
```

## Pull request checklist

- [ ] All tests pass (`make verify` is clean).
- [ ] If a new functional requirement was added, the SPR §3.1 and §6.2 traceability matrix are updated.
- [ ] If a hook payload or response schema changed, `docs/SCHEMAS.md` is updated.
- [ ] If a security-relevant assumption changed, `docs/security/threat-model.md` is updated.
- [ ] If a new external command is invoked or a new env var is read, it is documented.
- [ ] The commit message includes a `Signed-off-by:` line (DCO).
- [ ] No secrets, real session ids, or real audit-log entries are included in the diff.

## DCO sign-off

By signing off on your commits you certify the [Developer Certificate of Origin v1.1](https://developercertificate.org/). Use:

```bash
git commit -s -m "feat: ..."
```

CI rejects PRs without sign-off.

## Releases

Maintainer-only. To cut a release:

```bash
make release VERSION=x.y.z
git push origin vx.y.z
```

GitHub Releases publishes a signed tarball.

## Code style

- PEP 8 enforced by ruff with `select = ["E", "F", "I"]`.
- Type hints required on public functions. mypy must be clean with `--ignore-missing-imports`.
- No third-party Python dependencies. The gate uses stdlib only.
- Shell scripts pass `shellcheck` with default config.
- No comments restating obvious code; comments reserved for non-obvious why.

## Reporting security issues

Do not file public issues for security vulnerabilities. See `SECURITY.md` for the disclosure channel.
