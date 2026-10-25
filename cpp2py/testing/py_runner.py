"""Python execution runner for differential testing."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cpp2py.testing.cxx_runner import ExecutionResult, _get_minimal_env


def run_python(
    source_or_file: str | Path,
    stdin_text: str = "",
    timeout: float = 5.0,
    output_cap: int = 1048576,
    is_file: bool = False,
    cwd: str | Path | None = None,
) -> ExecutionResult:
    """Run a Python script under isolated conditions via sys.executable -X utf8."""
    temp_dir_obj: tempfile.TemporaryDirectory | None = None
    if cwd is None:
        temp_dir_obj = tempfile.TemporaryDirectory()
        run_cwd = Path(temp_dir_obj.name)
    else:
        run_cwd = Path(cwd)

    if is_file:
        script_path = str(Path(source_or_file).resolve())
    else:
        temp_script = run_cwd / "program.py"
        temp_script.write_text(str(source_or_file), encoding="utf-8")
        script_path = str(temp_script)

    cmd = [sys.executable, "-X", "utf8", script_path]
    stdin_bytes = stdin_text.encode("utf-8")

    env = _get_minimal_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(run_cwd),
            env=env,
        )
        try:
            raw_stdout, raw_stderr = proc.communicate(input=stdin_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return ExecutionResult(
                stdout="",
                stderr="Execution timed out",
                exit_code=-1,
                timed_out=True,
                output_capped=False,
            )

        capped = False
        if len(raw_stdout) > output_cap:
            raw_stdout = raw_stdout[:output_cap]
            capped = True

        stdout_str = raw_stdout.decode("utf-8", errors="replace")
        stderr_str = raw_stderr.decode("utf-8", errors="replace")

        return ExecutionResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=proc.returncode,
            timed_out=False,
            output_capped=capped,
        )

    except Exception as e:
        return ExecutionResult(
            stdout="",
            stderr=str(e),
            exit_code=-1,
            timed_out=False,
            output_capped=False,
        )
    finally:
        if temp_dir_obj is not None:
            try:
                temp_dir_obj.cleanup()
            except Exception:
                pass
