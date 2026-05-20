.PHONY: install verify test lint type uninstall release help

help:
	@echo "Targets:"
	@echo "  install    Install hooks into ~/.claude and/or ~/.codex (whichever are present)."
	@echo "  verify     Run ruff + mypy + pytest against the hook code."
	@echo "  test       Run pytest only."
	@echo "  lint       Run ruff only."
	@echo "  type       Run mypy only."
	@echo "  uninstall  Remove the gate from ~/.claude/settings.json and ~/.codex/hooks.json."
	@echo "  release    Tag a release (requires VERSION=x.y.z)."

install:
	bash ./install.sh

verify: lint type test

lint:
	ruff check .claude/hooks/python_evidence_gate.py \
	           .codex/hooks/python_evidence_core.py \
	           .codex/hooks/python_evidence_postuse.py \
	           .codex/hooks/python_evidence_stop.py \
	           .codex/hooks/python_evidence_userprompt.py \
	           .claude/hooks/tests/test_python_evidence_gate.py \
	           .codex/hooks/tests/test_python_evidence.py

type:
	mypy --ignore-missing-imports \
	     .claude/hooks/python_evidence_gate.py \
	     .codex/hooks/python_evidence_core.py \
	     .codex/hooks/python_evidence_postuse.py \
	     .codex/hooks/python_evidence_stop.py \
	     .codex/hooks/python_evidence_userprompt.py

test:
	pytest -q .claude/hooks/tests .codex/hooks/tests

uninstall:
	@bash ./scripts/uninstall.sh

release:
	@[ -n "$(VERSION)" ] || (echo "Set VERSION=x.y.z" && exit 1)
	git tag -a v$(VERSION) -m "Release v$(VERSION)"
	@echo "Now: git push origin v$(VERSION)"
