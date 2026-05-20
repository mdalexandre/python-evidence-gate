# Architecture

Distilled from SPR Chapter 4 for project `python-evidence-gate`.

## Directory layout

- `.`
- `.claude/hooks/`
- `.claude/hooks/tests/`
- `.codex/hooks/`
- `.codex/hooks/tests/`
- `scripts/`
- `docs/`
- `.github/workflows/`

## Architecture diagram (textual)

```
  +--------+    +-----------+    +------------+
  | input  |--->| processor |--->| output     |
  +--------+    +-----------+    +------------+
```

Refer to the SPR for the full design rationale and design patterns.
