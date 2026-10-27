import subprocess
import sys
from pathlib import Path
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode

def test_phase1_examples(tmp_path, repo_root):
    examples_dir = repo_root / "examples" / "phase1"
    expected_files = list(examples_dir.glob("*.expected"))
    assert len(expected_files) > 0

    for exp_file in expected_files:
        stem = exp_file.stem
        cpp_file = examples_dir / f"{stem}.cpp"
        assert cpp_file.exists(), f"Missing {cpp_file}"

        cpp_content = cpp_file.read_text(encoding="utf-8")
        res = compile_source(cpp_content, str(cpp_file), CompilerConfig())
        assert res.success, f"Compilation failed for {cpp_file}: {[d.message for d in res.diagnostics.errors]}"

        py_file = tmp_path / f"{stem}.py"
        py_file.write_text(res.python_source, encoding="utf-8")

        in_file = examples_dir / f"{stem}.in"
        stdin_data = in_file.read_bytes() if in_file.exists() else b""

        proc = subprocess.run(
            [sys.executable, str(py_file)],
            input=stdin_data,
            capture_output=True,
        )
        assert proc.returncode == 0, f"Running {py_file} failed with code {proc.returncode}: {proc.stderr.decode()}"

        expected_bytes = exp_file.read_bytes()
        actual_normalized = proc.stdout.replace(b'\r\n', b'\n')
        expected_normalized = expected_bytes.replace(b'\r\n', b'\n')
        assert actual_normalized == expected_normalized, (
            f"Output mismatch for {stem}:\n"
            f"Expected: {expected_normalized!r}\n"
            f"Got:      {actual_normalized!r}"
        )

def test_neg_division_warning_example(tmp_path, repo_root):
    cpp_file = repo_root / "examples" / "phase1" / "neg_division_warning.cpp"
    assert cpp_file.exists()

    cpp_content = cpp_file.read_text(encoding="utf-8")

    res_naive = compile_source(cpp_content, str(cpp_file), CompilerConfig(compat_mode=CompatMode.NAIVE))
    assert res_naive.success
    assert any(w.code == "W6001" for w in res_naive.diagnostics)
    assert "# WARNING W6001" in res_naive.python_source

    res_rg = compile_source(cpp_content, str(cpp_file), CompilerConfig())
    assert res_rg.success
    assert "_cpp_div" in res_rg.python_source

def test_ac1_10_precedence_execution(tmp_path):

    cxx_code = """#include <iostream>
using namespace std;
int main() {
    cout << 20 - 5 - 3 << endl;
    cout << 20 - (5 - 3) << endl;
    cout << -(17 + 3) << endl;
    cout << 100 / (5 / 2) << endl;
    return 0;
}
"""
    res = compile_source(cxx_code, "test.cpp", CompilerConfig())
    assert res.success

    py_file = tmp_path / "prec.py"
    py_file.write_text(res.python_source, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(py_file)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    lines = proc.stdout.strip().splitlines()
    assert lines == ["12", "18", "-20", "50"]
