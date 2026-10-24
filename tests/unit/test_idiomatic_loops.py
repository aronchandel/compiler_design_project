"""Unit tests for optional idiomatic loops (--idiomatic-loops).

Conforms to ARCH §D.3.4 and IMPLEMENTATION_PLAN §P4.
"""

import subprocess
import sys
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig


def run_py_snippet(py_code: str, stdin: str = "") -> str:
    """Helper to execute generated Python snippet and return normalized stdout."""
    proc = subprocess.run(
        [sys.executable, "-c", py_code],
        input=stdin,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, f"Python execution failed: {proc.stderr}\nCode:\n{py_code}"
    return proc.stdout.replace("\r\n", "\n")


QUALIFYING_CASES = [
    (
        "int main() { for (int i = 0; i < 5; ++i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(0, 5):",
    ),
    (
        "int main() { for (int i = 0; i <= 5; ++i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(0, 6):",
    ),
    (
        "int main() { int n = 4; for (int i = 0; i < n; ++i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(0, n):",
    ),
    (
        "int main() { int n = 4; for (int i = 0; i <= n; ++i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(0, n + 1):",
    ),
    (
        "int main() { for (int i = 0; i < 10; i += 2) { cout << i << endl; } return 0; }",
        "",
        "for i in range(0, 10, 2):",
    ),
    (
        "int main() { for (int i = 1; i <= 9; i += 2) { cout << i << endl; } return 0; }",
        "",
        "for i in range(1, 10, 2):",
    ),
    (
        "int main() { for (int i = 5; i > 0; --i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(5, 0, -1):",
    ),
    (
        "int main() { for (int i = 5; i >= 0; --i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(5, -1, -1):",
    ),
    (
        "int main() { for (int i = 10; i > 0; i -= 3) { cout << i << endl; } return 0; }",
        "",
        "for i in range(10, 0, -3):",
    ),
    (
        "int main() { int n = 2; for (int i = 5; i >= n; --i) { cout << i << endl; } return 0; }",
        "",
        "for i in range(5, n - 1, -1):",
    ),
]


@pytest.mark.parametrize("cpp_code, stdin, expected_for_line", QUALIFYING_CASES)
def test_qualifying_loops_emit_for_range_and_produce_identical_output(cpp_code, stdin, expected_for_line):
    prefix = "using namespace std;\n"
    full_code = prefix + cpp_code

    # 1. Compile with idiomatic loops ON
    cfg_on = CompilerConfig(idiomatic_loops=True)
    res_on = compile_source(full_code, "test.cpp", cfg_on)
    assert res_on.success, [d.message for d in res_on.diagnostics]
    assert expected_for_line in res_on.python_source

    # 2. Compile with idiomatic loops OFF (default)
    cfg_off = CompilerConfig(idiomatic_loops=False)
    res_off = compile_source(full_code, "test.cpp", cfg_off)
    assert res_off.success
    assert "while " in res_off.python_source
    assert "for i in range" not in res_off.python_source

    # 3. Execution outputs must be identical
    out_on = run_py_snippet(res_on.python_source, stdin)
    out_off = run_py_snippet(res_off.python_source, stdin)
    assert out_on == out_off


DISQUALIFIED_CASES = [
    # 1. loop var written in body
    "int main() { for (int i = 0; i < 5; ++i) { i += 1; cout << i << endl; } return 0; }",
    # 2. bound var written in body
    "int main() { int n = 5; for (int i = 0; i < n; ++i) { n -= 1; cout << i << endl; } return 0; }",
    # 3. non-constant step
    "int main() { int s = 2; for (int i = 0; i < 10; i += s) { cout << i << endl; } return 0; }",
    # 4. != condition
    "int main() { for (int i = 0; i != 5; ++i) { cout << i << endl; } return 0; }",
    # 5. variable declared outside the loop
    "int main() { int i; for (i = 0; i < 5; ++i) { cout << i << endl; } return 0; }",
    # 6. decreasing step with <
    "int main() { for (int i = 5; i < 0; --i) { cout << i << endl; } return 0; }",
    # 7. increasing step with >
    "int main() { for (int i = 0; i > 5; ++i) { cout << i << endl; } return 0; }",
    # 8. update is not add/sub (e.g. *= 2)
    "int main() { for (int i = 1; i < 10; i *= 2) { cout << i << endl; } return 0; }",
    # 9. while loop (not a for loop)
    "int main() { int i = 0; while (i < 5) { cout << i << endl; ++i; } return 0; }",
    # 10. loop var read via cin inside body
    "int main() { for (int i = 0; i < 5; ++i) { cin >> i; cout << i << endl; } return 0; }",
]


@pytest.mark.parametrize("cpp_code", DISQUALIFIED_CASES)
def test_disqualified_loops_emit_while_and_preserve_output(cpp_code):
    prefix = "using namespace std;\n"
    full_code = prefix + cpp_code

    # Even with idiomatic_loops=True, disqualified loops MUST emit while
    cfg = CompilerConfig(idiomatic_loops=True)
    res = compile_source(full_code, "test.cpp", cfg)
    assert res.success, [d.message for d in res.diagnostics]
    assert "for i in range" not in res.python_source
    assert "while " in res.python_source
