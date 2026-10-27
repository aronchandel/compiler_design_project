"""Unit tests for C++ 1D array support in cpp2py."""

import sys
import subprocess
import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.codegen.python_gen import generate


def compile_cpp(code: str) -> tuple[str, DiagnosticSink]:
    src = SourceFile("test.cpp", code)
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    ast_tree = parse(tokens, sink)
    if sink.has_errors():
        return "", sink
    config = CompilerConfig()
    info = analyze(ast_tree, config, sink)
    if sink.has_errors():
        return "", sink
    mod = build_ir(ast_tree, info, config)
    gen_sink = DiagnosticSink()
    py_code = generate(mod, gen_sink, config)
    return py_code, sink


def run_py(py_code: str, input_str: str = "") -> str:
    res = subprocess.run(
        [sys.executable, "-c", py_code],
        input=input_str,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


def test_array_declaration_and_init():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[3] = {10, 20, 30};
        cout << arr[0] << " " << arr[1] << " " << arr[2] << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "10 20 30"


def test_array_partial_init():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[4] = {5, 6};
        cout << arr[0] << " " << arr[1] << " " << arr[2] << " " << arr[3] << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "5 6 0 0"


def test_array_read_and_modify():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[3];
        arr[0] = 7;
        arr[1] = arr[0] + 3;
        arr[2] = arr[1] * 2;
        arr[0] += 1;
        arr[1]++;
        cout << arr[0] << " " << arr[1] << " " << arr[2] << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "8 11 20"


def test_array_loop_traversal():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[5] = {1, 2, 3, 4, 5};
        int sum = 0;
        for (int i = 0; i < 5; ++i) {
            sum += arr[i];
        }
        cout << sum << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "15"


def test_array_passed_to_function():
    code = """
    #include <iostream>
    using namespace std;

    void double_elements(int a[], int n) {
        for (int i = 0; i < n; ++i) {
            a[i] = a[i] * 2;
        }
    }

    int main() {
        int arr[3] = {10, 20, 30};
        double_elements(arr, 3);
        cout << arr[0] << " " << arr[1] << " " << arr[2] << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "20 40 60"


def test_array_input():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[3];
        for (int i = 0; i < 3; ++i) {
            cin >> arr[i];
        }
        cout << arr[0] << " " << arr[1] << " " << arr[2] << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code, input_str="100 200 300\n").strip()
    assert out == "100 200 300"


def test_multidimensional_array_rejected():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int matrix[3][3];
        return 0;
    }
    """
    _, sink = compile_cpp(code)
    assert sink.has_errors()
    assert any(d.code == "E4001" for d in sink.diagnostics)


def test_excess_initializers_rejected():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[2] = {1, 2, 3};
        return 0;
    }
    """
    _, sink = compile_cpp(code)
    assert sink.has_errors()
    assert any(d.code == "E3003" for d in sink.diagnostics)
