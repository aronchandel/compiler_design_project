"""Differential testing of arrays, pointers, and <climits> against the host C++ compiler."""

import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from cpp2py.config import CompilerConfig
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.codegen.python_gen import generate
from cpp2py.testing.cxx_runner import probe_cxx_capabilities

capabilities = probe_cxx_capabilities()
cxx_skip = pytest.mark.skipif(
    not capabilities.available,
    reason=f"g++ compiler not available/functional: {capabilities.reason}",
)


def run_diff_test(cxx_code: str, input_data: str = "") -> None:
    """Compile with g++, compile with cpp2py, run both and assert exact stdout match."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cxx_file = tmp_path / "main.cpp"
        exe_file = tmp_path / ("main.exe" if sys.platform == "win32" else "main")

        cxx_file.write_text(cxx_code, encoding="utf-8")

        # 1. Compile C++ with g++
        compile_cmd = ["g++", "-O2", "-std=c++17", str(cxx_file), "-o", str(exe_file)]
        subprocess.run(compile_cmd, check=True, capture_output=True)

        # Run C++ binary
        cxx_run = subprocess.run(
            [str(exe_file)],
            input=input_data,
            capture_output=True,
            text=True,
            check=True,
        )
        expected_stdout = cxx_run.stdout

        # 2. Translate with cpp2py
        src = SourceFile(str(cxx_file), cxx_code)
        sink = DiagnosticSink()
        tokens = tokenize(src, sink)
        ast_tree = parse(tokens, sink)
        assert not sink.has_errors(), f"Parse errors: {[d.message for d in sink.diagnostics]}"

        config = CompilerConfig()
        info = analyze(ast_tree, config, sink)
        assert not sink.has_errors(), f"Semantic errors: {[d.message for d in sink.diagnostics]}"

        mod = build_ir(ast_tree, info, config)
        gen_sink = DiagnosticSink()
        py_code = generate(mod, gen_sink, config)

        # Run generated Python
        py_run = subprocess.run(
            [sys.executable, "-c", py_code],
            input=input_data,
            capture_output=True,
            text=True,
            check=True,
        )
        actual_stdout = py_run.stdout

        # 3. Assert exact match
        assert actual_stdout == expected_stdout


@pytest.mark.requires_cxx
@cxx_skip
def test_difftest_climits():
    code = """
    #include <iostream>
    #include <climits>
    using namespace std;
    int main() {
        cout << CHAR_BIT << endl;
        cout << INT_MIN << " " << INT_MAX << endl;
        cout << LONG_MIN << " " << LONG_MAX << endl;
        cout << LLONG_MIN << " " << LLONG_MAX << endl;
        return 0;
    }
    """
    run_diff_test(code)


@pytest.mark.requires_cxx
@cxx_skip
def test_difftest_array_algorithms():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[6] = {5, 2, 8, 1, 9, 3};
        // Bubble sort
        for (int i = 0; i < 6; ++i) {
            for (int j = 0; j < 5; ++j) {
                if (arr[j] > arr[j + 1]) {
                    int tmp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = tmp;
                }
            }
        }
        for (int i = 0; i < 6; ++i) {
            cout << arr[i] << " ";
        }
        cout << endl;
        return 0;
    }
    """
    run_diff_test(code)


@pytest.mark.requires_cxx
@cxx_skip
def test_difftest_pointer_aliasing_and_mutation():
    code = """
    #include <iostream>
    using namespace std;

    void update(int *p1, int *p2) {
        *p1 += 15;
        *p2 *= 2;
    }

    int main() {
        int a = 10;
        int b = 20;
        update(&a, &b);
        cout << a << " " << b << endl;

        // Pointer aliasing
        int *p = &a;
        int *q = p;
        *q = 999;
        cout << *p << " " << a << endl;
        return 0;
    }
    """
    run_diff_test(code)


@pytest.mark.requires_cxx
@cxx_skip
def test_difftest_array_pointer_decay_and_arithmetic():
    code = """
    #include <iostream>
    using namespace std;

    int sum_slice(int *p, int count) {
        int total = 0;
        for (int i = 0; i < count; ++i) {
            total += *(p + i);
        }
        return total;
    }

    int main() {
        int numbers[5] = {10, 20, 30, 40, 50};
        cout << sum_slice(numbers, 5) << endl;
        cout << sum_slice(&numbers[2], 3) << endl;
        return 0;
    }
    """
    run_diff_test(code)
