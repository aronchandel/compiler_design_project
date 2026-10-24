"""Integration tests verifying the Phase 2 IR pipeline against the direct backend and .expected files."""

import subprocess
import sys
from pathlib import Path
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig


def test_ir_pipeline_all_phase1_examples(tmp_path, repo_root):
    examples_dir = repo_root / "examples" / "phase1"
    expected_files = list(examples_dir.glob("*.expected"))
    assert len(expected_files) > 0

    for exp_file in expected_files:
        stem = exp_file.stem
        cpp_file = examples_dir / f"{stem}.cpp"
        assert cpp_file.exists(), f"Missing {cpp_file}"

        cpp_content = cpp_file.read_text(encoding="utf-8")

        # 1. Compile through default IR pipeline
        res_ir = compile_source(cpp_content, str(cpp_file), CompilerConfig(backend="ir"))
        assert res_ir.success, f"IR pipeline compilation failed for {stem}: {[d.message for d in res_ir.diagnostics]}"

        # 2. Compile through direct backend (Phase 1 bootstrap path)
        res_direct = compile_source(cpp_content, str(cpp_file), CompilerConfig(backend="direct"))
        assert res_direct.success, f"Direct backend compilation failed for {stem}"

        # Write generated scripts
        py_ir_file = tmp_path / f"{stem}_ir.py"
        py_ir_file.write_text(res_ir.python_source, encoding="utf-8")

        py_direct_file = tmp_path / f"{stem}_direct.py"
        py_direct_file.write_text(res_direct.python_source, encoding="utf-8")

        # Stdin
        in_file = examples_dir / f"{stem}.in"
        stdin_data = in_file.read_bytes() if in_file.exists() else b""

        # Execute IR path
        proc_ir = subprocess.run(
            [sys.executable, str(py_ir_file)],
            input=stdin_data,
            capture_output=True,
        )
        assert proc_ir.returncode == 0, f"Running {py_ir_file} failed with code {proc_ir.returncode}: {proc_ir.stderr.decode()}"

        # Execute direct path
        proc_direct = subprocess.run(
            [sys.executable, str(py_direct_file)],
            input=stdin_data,
            capture_output=True,
        )
        assert proc_direct.returncode == 0

        # Normalise newlines
        actual_ir = proc_ir.stdout.replace(b"\r\n", b"\n")
        actual_direct = proc_direct.stdout.replace(b"\r\n", b"\n")
        expected = exp_file.read_bytes().replace(b"\r\n", b"\n")

        # AC2.4: IR path and direct backend produce identical stdout equal to .expected
        assert actual_ir == expected, f"Mismatch with expected in {stem}:\nExpected: {expected!r}\nGot: {actual_ir!r}"
        assert actual_ir == actual_direct, f"Mismatch between IR path and direct backend in {stem}"


def test_fold_demo_execution(tmp_path, repo_root):
    cpp_file = repo_root / "examples" / "worked" / "fold_demo.cpp"
    assert cpp_file.exists()

    cpp_content = cpp_file.read_text(encoding="utf-8")
    res = compile_source(cpp_content, str(cpp_file), CompilerConfig(backend="ir"))
    assert res.success

    py_file = tmp_path / "fold_demo.py"
    py_file.write_text(res.python_source, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(py_file)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "48"
