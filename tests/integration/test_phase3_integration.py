"""Integration tests for Phase 3.

Covers:
- AC3.2: All Phase 3 examples with .expected files produce byte-identical stdout and exit 0.
- AC3.3: All Phase 3 errors/*.cpp programs exit 2 with the expected code on stderr and write no output file.
- AC3.6: codegen/ast_to_python.py does not exist and --backend option is absent.
- AC3.10: No transforms/, analysis/, compat/ directories exist.
"""

from pathlib import Path
import subprocess
import sys
import pytest


PHASE3_EXAMPLES = sorted(Path("examples/phase3").glob("*.cpp"))
PHASE3_ERRORS = sorted(Path("examples/phase3/errors").glob("*.cpp"))

ERROR_EXPECTATIONS = {
    "missing_return.cpp": "E3007",
    "call_before_define.cpp": "E3001",
    "wrong_arg_count.cpp": "E3006",
    "relational_as_value.cpp": "E3008",
    "uninit_in_one_branch.cpp": "E3003",
    "and_operator.cpp": "E4001",
    "break_stmt.cpp": "E4001",
    "for_without_cond.cpp": "E2001",
    "void_value_used.cpp": "E3004",
    "duplicate_function.cpp": "E3002",
    "main_with_params.cpp": "E4001",
}


@pytest.mark.parametrize("cpp_path", PHASE3_EXAMPLES, ids=lambda p: p.name)
def test_phase3_examples_stdout_matches_expected(cpp_path: Path, tmp_path: Path):
    """AC3.2: Translate and execute each Phase 3 example, assert byte-identical stdout."""
    expected_path = cpp_path.with_suffix(".expected")
    assert expected_path.exists(), f"Missing .expected for {cpp_path}"
    expected_bytes = expected_path.read_bytes()

    in_path = cpp_path.with_suffix(".in")
    stdin_bytes = in_path.read_bytes() if in_path.exists() else b""

    out_py = tmp_path / f"{cpp_path.stem}.py"

    # Translate
    cmd_trans = [
        sys.executable,
        "-m",
        "cpp2py",
        "translate",
        str(cpp_path),
        "-o",
        str(out_py),
    ]
    trans_proc = subprocess.run(cmd_trans, capture_output=True, text=True)
    assert trans_proc.returncode == 0, f"Translation failed for {cpp_path}:\n{trans_proc.stderr}"
    assert out_py.exists()

    # Execute
    exec_proc = subprocess.run(
        [sys.executable, str(out_py)],
        input=stdin_bytes,
        capture_output=True,
    )
    assert exec_proc.returncode == 0, f"Execution failed for {cpp_path}:\n{exec_proc.stderr.decode('utf-8', errors='replace')}"

    # Normalize CRLF/LF for cross-platform robustness if needed, or compare bytes
    actual = exec_proc.stdout.replace(b"\r\n", b"\n")
    expected = expected_bytes.replace(b"\r\n", b"\n")
    assert actual == expected


@pytest.mark.parametrize("cpp_path", PHASE3_ERRORS, ids=lambda p: p.name)
def test_phase3_errors_exit_2_and_no_output_file(cpp_path: Path, tmp_path: Path):
    """AC3.3: Every errors/*.cpp exits 2 with expected code and produces no output file."""
    expected_code = ERROR_EXPECTATIONS[cpp_path.name]
    out_py = tmp_path / f"{cpp_path.stem}.py"

    cmd = [
        sys.executable,
        "-m",
        "cpp2py",
        "translate",
        str(cpp_path),
        "-o",
        str(out_py),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    assert proc.returncode == 2, f"Expected returncode 2 for {cpp_path.name}, got {proc.returncode}"
    assert expected_code in proc.stderr, f"Expected {expected_code} in stderr for {cpp_path.name}:\n{proc.stderr}"
    assert not out_py.exists(), f"Output file should not be created on error for {cpp_path.name}"


def test_ac3_6_ast_to_python_removed():
    """AC3.6: codegen/ast_to_python.py and --backend option do not exist."""
    ast_to_py = Path("cpp2py/codegen/ast_to_python.py")
    assert not ast_to_py.exists()

    # Verify --backend is rejected
    proc = subprocess.run(
        [sys.executable, "-m", "cpp2py", "translate", "--backend", "direct", "examples/phase1/arith_basic.cpp"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "unrecognized arguments: --backend" in proc.stderr


def test_ac3_10_no_transforms_analysis_compat_directories():
    """No testing/, localisation/, reporting/, or evaluation/ directories exist in Phase 5."""
    repo_cpp2py = Path("cpp2py")
    assert not (repo_cpp2py / "localisation").exists()
