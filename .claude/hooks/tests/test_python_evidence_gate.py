"""Tests for python_evidence_gate.py Stop hook (v2).

Each test builds a synthetic transcript JSONL and a synthetic Stop payload,
runs the hook via subprocess, and asserts on the block-or-pass behavior.

v2 transcripts must include tool_result blocks with matching tool_use_ids so
the hook's exit-code awareness can evaluate success.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "python_evidence_gate.py"

_id_counter = itertools.count(1)


def _next_id() -> str:
    return f"toolu_test_{next(_id_counter):04d}"


def _run(transcript_path: Path, cwd: Path, env_extra: dict | None = None,
         stop_hook_active: bool = False) -> tuple[int, str]:
    payload = {
        "session_id": "pytest",
        "transcript_path": str(transcript_path),
        "cwd": str(cwd),
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
    }
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    return proc.returncode, proc.stdout


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _edit(file_path: str, tool_use_id: str | None = None) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": tool_use_id or _next_id(),
                "name": "Edit",
                "input": {"file_path": file_path,
                          "old_string": "a", "new_string": "b"},
            }],
        },
    }


def _bash(cmd: str, tool_use_id: str | None = None) -> tuple[dict, str]:
    tid = tool_use_id or _next_id()
    rec = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": tid,
                "name": "Bash",
                "input": {"command": cmd},
            }],
        },
    }
    return rec, tid


def _result(tool_use_id: str, is_error: bool = False, content: str = "") -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "is_error": is_error,
                "content": content,
            }],
        },
    }


def _bash_ok(cmd: str) -> list[dict]:
    rec, tid = _bash(cmd)
    return [rec, _result(tid, is_error=False, content="")]


def _bash_fail(cmd: str) -> list[dict]:
    rec, tid = _bash(cmd)
    return [rec, _result(tid, is_error=True, content="Exit code 1\nfailure\n")]


def _no_tests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "no_tests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _with_tests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "with_tests"
    (d / "tests").mkdir(parents=True, exist_ok=True)
    (d / "tests" / "test_sample.py").write_text("def test_x(): pass\n")
    return d


def _expect_block(stdout: str) -> dict:
    assert stdout.strip(), "expected block payload, got empty stdout"
    parsed = json.loads(stdout)
    assert parsed.get("decision") == "block", parsed
    return parsed


def test_python_edit_without_checks_blocks(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_user("edit foo.py"), _edit("/tmp/foo.py")])
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" in payload["reason"]


def test_ruff_and_mypy_run_no_tests_passes(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("uv run ruff check --fix /tmp/foo.py")
    records += _bash_ok("uv run mypy /tmp/foo.py")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    assert out.strip() == ""


def test_pytest_required_when_tests_exist(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("uv run ruff check --fix /tmp/foo.py")
    records += _bash_ok("uv run mypy /tmp/foo.py")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _with_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "pytest" in payload["reason"]


def test_all_three_with_tests_passes(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("ruff check .")
    records += _bash_ok("mypy .")
    records += _bash_ok("pytest -q")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _with_tests_dir(tmp_path))
    assert rc == 0
    assert out.strip() == ""


def test_non_python_edit_passes(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_user("edit md"), _edit("/tmp/foo.md")])
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    assert out.strip() == ""


def test_install_and_version_do_not_count(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("uv tool install ruff mypy pytest")
    records += _bash_ok("command -v ruff")
    records += _bash_ok("ruff --version")
    records += _bash_ok("mypy --version")
    records += _bash_ok("pytest --version")
    records += _bash_ok("uv run ruff --version")  # v2: wrapped version excluded
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" in payload["reason"]


def test_override_env_disables(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_user("edit foo.py"), _edit("/tmp/foo.py")])
    rc, out = _run(transcript, _no_tests_dir(tmp_path),
                   env_extra={"PYTHON_EVIDENCE_GATE": "0"})
    assert rc == 0
    assert out.strip() == ""


def test_stop_hook_active_is_loop_safe(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_user("edit foo.py"), _edit("/tmp/foo.py")])
    rc, out = _run(transcript, _no_tests_dir(tmp_path), stop_hook_active=True)
    assert rc == 0
    assert out.strip() == ""


def test_python_m_module_form_counts(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("python3 -m ruff check .")
    records += _bash_ok("python -m mypy .")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    assert out.strip() == ""


# --- v2 new tests --------------------------------------------------------


def test_check_before_edit_does_not_count(tmp_path: Path) -> None:
    """A successful ruff/mypy that ran BEFORE the edit must not count."""
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py")]
    records += _bash_ok("ruff check .")
    records += _bash_ok("mypy .")
    records.append(_edit("/tmp/foo.py"))
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" in payload["reason"]


def test_failed_check_does_not_count(tmp_path: Path) -> None:
    """is_error=True or 'Exit code N' on the tool_result -> check rejected."""
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_fail("ruff check .")
    records += _bash_fail("mypy .")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" in payload["reason"]


def test_bash_redirect_creates_py_edit(tmp_path: Path) -> None:
    """`echo x > foo.py` counts as a .py edit even without an Edit tool call."""
    transcript = tmp_path / "t.jsonl"
    records = [_user("create via shell")]
    records += _bash_ok("echo 'def f(): pass' > /tmp/created.py")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "created.py" in payload["reason"]


def test_bash_tee_creates_py_edit(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("tee a file")]
    records += _bash_ok("echo 'x' | tee /tmp/teed.py")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "teed.py" in payload["reason"]


def test_bash_sed_inplace_counts_as_edit(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    records = [_user("sed inplace")]
    records += _bash_ok("sed -i 's/a/b/' /tmp/foo.py")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "foo.py" in payload["reason"]


def test_echo_label_does_not_count_as_invocation(tmp_path: Path) -> None:
    """`echo '=== ruff check ==='` must not satisfy the ruff requirement."""
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok('echo "=== ruff check ==="')
    records += _bash_ok('echo "running mypy now"')
    records += _bash_ok('echo "pytest passed"')
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" in payload["reason"]


def test_heredoc_body_does_not_count(tmp_path: Path) -> None:
    """Tokens inside heredoc bodies must not satisfy the gate."""
    transcript = tmp_path / "t.jsonl"
    heredoc_cmd = "cat > /tmp/note.txt << 'EOF'\nuv run ruff check .\nuv run mypy .\nEOF"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok(heredoc_cmd)
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" in payload["reason"]


def test_ruff_format_alone_does_not_count(tmp_path: Path) -> None:
    """Doctrine requires `ruff check`; bare `ruff format` is not enough."""
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("ruff format .")
    records += _bash_ok("mypy .")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    payload = _expect_block(out)
    assert "ruff" in payload["reason"]
    assert "mypy" not in payload["reason"]


def test_chained_check_in_one_segment_counts(tmp_path: Path) -> None:
    """`ruff check . && mypy .` succeeding should satisfy both."""
    transcript = tmp_path / "t.jsonl"
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok("ruff check . && mypy .")
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    assert out.strip() == ""


def test_newline_separated_commands_count(tmp_path: Path) -> None:
    """Multi-line bash scripts (newlines, not `&&`) should be segmented."""
    transcript = tmp_path / "t.jsonl"
    cmd = (
        "cd /home/x\n"
        'echo "=== ruff ==="\n'
        "ruff check .\n"
        'echo "=== mypy ==="\n'
        "mypy ."
    )
    records = [_user("edit foo.py"), _edit("/tmp/foo.py")]
    records += _bash_ok(cmd)
    _write_transcript(transcript, records)
    rc, out = _run(transcript, _no_tests_dir(tmp_path))
    assert rc == 0
    assert out.strip() == ""
