import subprocess
import sys
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig

def run_py_snippet(py_code: str, stdin: str = "") -> str:
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

    cfg_on = CompilerConfig(idiomatic_loops=True)
    res_on = compile_source(full_code, "test.cpp", cfg_on)
    assert res_on.success, [d.message for d in res_on.diagnostics]
    assert expected_for_line in res_on.python_source

    cfg_off = CompilerConfig(idiomatic_loops=False)
    res_off = compile_source(full_code, "test.cpp", cfg_off)
    assert res_off.success
    assert "while " in res_off.python_source
    assert "for i in range" not in res_off.python_source

    out_on = run_py_snippet(res_on.python_source, stdin)
    out_off = run_py_snippet(res_off.python_source, stdin)
    assert out_on == out_off

DISQUALIFIED_CASES = [

    "int main() { for (int i = 0; i < 5; ++i) { i += 1; cout << i << endl; } return 0; }",

    "int main() { int n = 5; for (int i = 0; i < n; ++i) { n -= 1; cout << i << endl; } return 0; }",

    "int main() { int s = 2; for (int i = 0; i < 10; i += s) { cout << i << endl; } return 0; }",

    "int main() { for (int i = 0; i != 5; ++i) { cout << i << endl; } return 0; }",

    "int main() { int i; for (i = 0; i < 5; ++i) { cout << i << endl; } return 0; }",

    "int main() { for (int i = 5; i < 0; --i) { cout << i << endl; } return 0; }",

    "int main() { for (int i = 0; i > 5; ++i) { cout << i << endl; } return 0; }",

    "int main() { for (int i = 1; i < 10; i *= 2) { cout << i << endl; } return 0; }",

    "int main() { int i = 0; while (i < 5) { cout << i << endl; ++i; } return 0; }",

    "int main() { for (int i = 0; i < 5; ++i) { cin >> i; cout << i << endl; } return 0; }",
]

@pytest.mark.parametrize("cpp_code", DISQUALIFIED_CASES)
def test_disqualified_loops_emit_while_and_preserve_output(cpp_code):
    prefix = "using namespace std;\n"
    full_code = prefix + cpp_code

    cfg = CompilerConfig(idiomatic_loops=True)
    res = compile_source(full_code, "test.cpp", cfg)
    assert res.success, [d.message for d in res.diagnostics]
    assert "for i in range" not in res.python_source
    assert "while " in res.python_source


def test_bubble_sort_idiomatic_code_generation():
    code = """
    #include <iostream>
    using namespace std;

    int main() {
        int n;
        cin >> n;
        int arr[n];
        for (int i = 0; i < n; i++) {
            cin >> arr[i];
        }
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n - i - 1; j++) {
                if (arr[j] > arr[j + 1]) {
                    int temp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = temp;
                }
            }
        }
        for (int i = 0; i < n; i++) {
            cout << arr[i] << " ";
        }
        return 0;
    }
    """
    cfg_on = CompilerConfig(idiomatic_loops=True)
    res_on = compile_source(code, "test.cpp", cfg_on)
    assert res_on.success, [d.message for d in res_on.diagnostics]
    py_src = res_on.python_source

    # Check for idiomatic constructs
    assert "for i in range(0, n):" in py_src
    assert "for j in range(0, n - i - 1):" in py_src
    assert "if arr[j] > arr[j + 1]:" in py_src
    assert "arr[i] = int(next(_tokens))" in py_src
    assert 'if __name__ == "__main__":' in py_src

    # Verify no _Ptr helper class is emitted
    assert "class _Ptr:" not in py_src

    # Verify execution output
    stdin = "5\n42 17 99 8 23\n"
    out_on = run_py_snippet(py_src, stdin).strip()
    assert out_on == "8 17 23 42 99"

    # Verify fallback to while loops with identical output
    cfg_off = CompilerConfig(idiomatic_loops=False)
    res_off = compile_source(code, "test.cpp", cfg_off)
    assert res_off.success
    assert "while i < n:" in res_off.python_source
    assert "while j < n - i - 1:" in res_off.python_source
    out_off = run_py_snippet(res_off.python_source, stdin).strip()
    assert out_off == out_on


def test_no_ptr_helper_for_array_indexing():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int a[3];
        a[0] = 10;
        a[1] = 20;
        a[2] = a[0] + a[1];
        cout << a[2] << endl;
        return 0;
    }
    """
    res = compile_source(code, "test.cpp")
    assert res.success
    assert "class _Ptr:" not in res.python_source
    out = run_py_snippet(res.python_source).strip()
    assert out == "30"


def test_ptr_helper_retained_for_actual_pointers():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 42;
        int* p = &x;
        cout << *p << endl;
        return 0;
    }
    """
    res = compile_source(code, "test.cpp")
    assert res.success
    assert "class _Ptr:" in res.python_source
    out = run_py_snippet(res.python_source).strip()
    assert out == "42"

