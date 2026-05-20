"""Tests for the Codex Python evidence gate (core + postuse + stop)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOKS_DIR))

from python_evidence_core import (  # noqa: E402
    detect_apply_patch_py_edits,
    detect_bash_py_edits,
    evaluate,
    matches_check,
    normalize_argv,
    result_is_failure,
    session_events_path,
    split_segments,
)

POSTUSE = HOOKS_DIR / "python_evidence_postuse.py"
STOP = HOOKS_DIR / "python_evidence_stop.py"
USERPROMPT = HOOKS_DIR / "python_evidence_userprompt.py"


# --- core unit tests -----------------------------------------------------


def test_split_segments_basic() -> None:
    assert split_segments("ruff check .") == [["ruff", "check", "."]]


def test_split_segments_semicolons_and_amp() -> None:
    segs = split_segments("ruff check . && mypy . ; pytest -q")
    assert segs == [["ruff", "check", "."], ["mypy", "."], ["pytest", "-q"]]


def test_split_segments_multiline() -> None:
    cmd = "echo hi\nruff check .\nmypy ."
    segs = split_segments(cmd)
    assert ["ruff", "check", "."] in segs
    assert ["mypy", "."] in segs


def test_split_segments_heredoc_body_dropped() -> None:
    cmd = "cat > /tmp/x << 'EOF'\nruff check .\nmypy .\nEOF"
    segs = split_segments(cmd)
    flat = [tok for seg in segs for tok in seg]
    assert "ruff" not in flat
    assert "mypy" not in flat


def test_split_segments_echo_does_not_leak() -> None:
    segs = split_segments('echo "=== ruff check ==="')
    assert segs == [["echo", "=== ruff check ==="]]


def test_matches_check_ruff_requires_check_subcommand() -> None:
    assert matches_check(["ruff", "check", "."], "ruff") is True
    assert matches_check(["ruff", "format", "."], "ruff") is False
    assert matches_check(["ruff"], "ruff") is False


def test_matches_check_excludes_versions_and_installs() -> None:
    assert matches_check(["ruff", "--version"], "ruff") is False
    assert matches_check(["uv", "tool", "install", "ruff"], "ruff") is False
    assert matches_check(["pip", "install", "ruff"], "ruff") is False
    assert matches_check(["command", "-v", "ruff"], "ruff") is False


def test_matches_check_normalizes_uv_run_and_python_m() -> None:
    assert matches_check(["uv", "run", "ruff", "check", "."], "ruff") is True
    assert matches_check(["uv", "run", "--python", "3.12", "ruff", "check"], "ruff") is True
    assert matches_check(["python3", "-m", "pytest"], "pytest") is True
    assert matches_check(["uv", "run", "ruff", "--version"], "ruff") is False


def test_matches_check_mypy_accepts_dmypy() -> None:
    assert matches_check(["dmypy", "run", "--", "."], "mypy") is True


def test_detect_bash_py_edits_redirects_and_tee_and_sed() -> None:
    assert detect_bash_py_edits("echo x > /tmp/a.py") == ["/tmp/a.py"]
    assert detect_bash_py_edits("echo x | tee /tmp/b.py") == ["/tmp/b.py"]
    assert detect_bash_py_edits("sed -i 's/a/b/' /tmp/c.py") == ["/tmp/c.py"]
    assert detect_bash_py_edits("cat foo") == []


def test_detect_apply_patch_py_edits() -> None:
    patch = (
        "*** Begin Patch\n"
        "*** Update File: /tmp/x.py\n"
        "@@ ...\n"
        "*** Add File: /tmp/y.py\n"
        "*** Update File: /tmp/z.md\n"
        "*** End Patch\n"
    )
    edits = detect_apply_patch_py_edits(patch)
    assert "/tmp/x.py" in edits
    assert "/tmp/y.py" in edits
    assert "/tmp/z.md" not in edits


def test_result_is_failure_signals() -> None:
    assert result_is_failure({"is_error": True}) is True
    assert result_is_failure({"exit_code": 2}) is True
    assert result_is_failure({"is_error": False, "output": "Exit code 1\nboom"}) is True
    assert result_is_failure({"is_error": False, "output": "ok"}) is False
    assert result_is_failure(None) is False
    assert result_is_failure("Exit code 7\nfail") is True


def test_normalize_argv_strips_env_prefix() -> None:
    assert normalize_argv(["env", "VAR=val", "ruff", "check", "."]) == ["ruff", "check", "."]


def test_evaluate_gates_correctly() -> None:
    events = [
        {"type": "edit", "idx": 0, "file_path": "/tmp/a.py", "source": "tool"},
        {"type": "check", "idx": 1, "name": "ruff", "ok": True},
        # mypy missing
    ]
    missing, files, bash_edits, last = evaluate(events, pytest_required=False)
    assert "mypy" in missing
    assert "ruff" not in missing
    assert "/tmp/a.py" in files
    assert last == 0


def test_evaluate_order_check_before_edit_does_not_count() -> None:
    events = [
        {"type": "check", "idx": 0, "name": "ruff", "ok": True},
        {"type": "check", "idx": 1, "name": "mypy", "ok": True},
        {"type": "edit", "idx": 2, "file_path": "/tmp/a.py", "source": "tool"},
    ]
    missing, _, _, _ = evaluate(events, pytest_required=False)
    assert sorted(missing) == ["mypy", "ruff"]


def test_evaluate_failed_check_does_not_count() -> None:
    events = [
        {"type": "edit", "idx": 0, "file_path": "/tmp/a.py", "source": "tool"},
        {"type": "check", "idx": 1, "name": "ruff", "ok": False},
        {"type": "check", "idx": 2, "name": "mypy", "ok": False},
    ]
    missing, _, _, _ = evaluate(events, pytest_required=False)
    assert sorted(missing) == ["mypy", "ruff"]


# --- subprocess-driven hook tests ----------------------------------------


def _fresh_tid() -> str:
    return f"pytest_{uuid.uuid4().hex[:12]}"


def _run_hook(script: Path, payload: dict, env_extra: dict | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        text=True, capture_output=True, env=env, timeout=10,
    )
    return proc.returncode, proc.stdout


def _no_tests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "no_tests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _with_tests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "with_tests"
    (d / "tests").mkdir(parents=True, exist_ok=True)
    (d / "tests" / "test_sample.py").write_text("def test_x(): pass\n")
    return d


def test_postuse_edit_then_check_flow(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    edit_payload = {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py",
                       "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False, "output": ""},
    }
    rc, _ = _run_hook(POSTUSE, edit_payload)
    assert rc == 0
    bash_payload = {
        "session_id": tid,
        "tool_name": "Bash",
        "tool_input": {"command": "ruff check . && mypy ."},
        "tool_response": {"is_error": False, "output": ""},
    }
    rc, _ = _run_hook(POSTUSE, bash_payload)
    assert rc == 0
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    types = [(e.get("type"), e.get("name") or e.get("file_path")) for e in events]
    assert ("edit", "/tmp/foo.py") in types
    assert ("check", "ruff") in types
    assert ("check", "mypy") in types


def test_stop_blocks_when_evidence_missing(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False},
    })
    rc, out = _run_hook(STOP, {
        "session_id": tid,
        "cwd": str(_no_tests_dir(tmp_path)),
        "stop_hook_active": False,
        "last_assistant_message": "done",
    })
    assert rc == 0
    parsed = json.loads(out)
    assert parsed.get("decision") == "block"
    assert "ruff" in parsed["reason"]
    assert "mypy" in parsed["reason"]


def test_stop_passes_when_checks_after_edit(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False},
    })
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Bash",
        "tool_input": {"command": "ruff check . && mypy ."},
        "tool_response": {"is_error": False},
    })
    rc, out = _run_hook(STOP, {
        "session_id": tid,
        "cwd": str(_no_tests_dir(tmp_path)),
        "stop_hook_active": False,
    })
    assert rc == 0
    assert out.strip() == "" or json.loads(out).get("continue") is True


def test_stop_blocks_on_pytest_when_tests_exist(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False},
    })
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Bash",
        "tool_input": {"command": "ruff check . && mypy ."},
        "tool_response": {"is_error": False},
    })
    rc, out = _run_hook(STOP, {
        "session_id": tid,
        "cwd": str(_with_tests_dir(tmp_path)),
        "stop_hook_active": False,
    })
    assert rc == 0
    parsed = json.loads(out)
    assert parsed.get("decision") == "block"
    assert "pytest" in parsed["reason"]


def test_postuse_apply_patch_detects_py_files(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    patch_body = (
        "*** Begin Patch\n"
        "*** Update File: /tmp/patched.py\n"
        "@@ ...\n"
        "*** End Patch\n"
    )
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "apply_patch",
        "tool_input": {"input": patch_body},
        "tool_response": {"is_error": False},
    })
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert any(e.get("type") == "edit" and e.get("file_path") == "/tmp/patched.py"
               for e in events)


def test_postuse_bash_redirect_records_edit(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Bash",
        "tool_input": {"command": "echo 'x' > /tmp/redirected.py"},
        "tool_response": {"is_error": False},
    })
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert any(e.get("type") == "edit" and e.get("file_path") == "/tmp/redirected.py"
               for e in events)


def test_postuse_failed_command_does_not_record_check(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    if log.exists():
        log.unlink()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False},
    })
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Bash",
        "tool_input": {"command": "ruff check . && mypy ."},
        "tool_response": {"is_error": True, "output": "Exit code 1\nfailed"},
    })
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert not any(e.get("type") == "check" for e in events)


def test_userprompt_resets_log(tmp_path: Path) -> None:
    tid = _fresh_tid()
    log = session_events_path(tid)
    log.write_text(json.dumps({"type": "edit", "idx": 0, "file_path": "/tmp/x.py"}) + "\n")
    assert log.exists()
    rc, _ = _run_hook(USERPROMPT, {"session_id": tid})
    assert rc == 0
    assert not log.exists()


def test_stop_loop_safe_when_continuation(tmp_path: Path) -> None:
    tid = _fresh_tid()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False},
    })
    rc, out = _run_hook(STOP, {
        "session_id": tid,
        "cwd": str(_no_tests_dir(tmp_path)),
        "stop_hook_active": True,
    })
    assert rc == 0
    assert json.loads(out).get("continue") is True


def test_stop_override_env_disables(tmp_path: Path) -> None:
    tid = _fresh_tid()
    _run_hook(POSTUSE, {
        "session_id": tid,
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/foo.py", "old_string": "a", "new_string": "b"},
        "tool_response": {"is_error": False},
    })
    rc, out = _run_hook(STOP, {
        "session_id": tid,
        "cwd": str(_no_tests_dir(tmp_path)),
        "stop_hook_active": False,
    }, env_extra={"PYTHON_EVIDENCE_GATE": "0"})
    assert rc == 0
    assert json.loads(out).get("continue") is True
