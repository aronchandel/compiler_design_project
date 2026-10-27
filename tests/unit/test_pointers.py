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

def test_pointer_declaration_and_deref():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 42;
        int *p = &x;
        cout << *p << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    assert "_Ptr" in py_code
    out = run_py(py_code).strip()
    assert out == "42"

def test_writing_through_pointer_mutates_original_variable():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 10;
        int *p = &x;
        *p = 99;
        cout << x << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "99"

def test_pointer_aliasing():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 100;
        int *p1 = &x;
        int *p2 = p1;
        *p2 = 250;
        cout << *p1 << " " << x << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "250 250"

def test_nullptr_declaration_and_equality():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int *p = nullptr;
        if (p == nullptr) {
            cout << "null" << endl;
        } else {
            cout << "not null" << endl;
        }
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "null"

def test_nullptr_dereference_raises_error():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int *p = nullptr;
        cout << *p << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_py(py_code)
    assert "Segmentation fault" in exc_info.value.stderr

def test_pointer_parameter_in_function():
    code = """
    #include <iostream>
    using namespace std;

    void add_ten(int *p) {
        *p += 10;
    }

    int main() {
        int val = 25;
        add_ten(&val);
        cout << val << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "35"

def test_pointer_to_array_and_pointer_arithmetic():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[4] = {10, 20, 30, 40};
        int *p = arr;
        p = p + 2;
        *p = 99;
        p++;
        cout << arr[2] << " " << *p << " " << *(p - 2) << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "99 40 20"

def test_pointer_difference():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int arr[5] = {10, 20, 30, 40, 50};
        int *p1 = &arr[1];
        int *p2 = &arr[4];
        cout << (p2 - p1) << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip()
    assert out == "3"

def test_pointer_input():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 0;
        int *p = &x;
        cin >> *p;
        cout << x << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code, input_str="777\n").strip()
    assert out == "777"

def test_unaddressed_scalars_remain_plain_without_boxing():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int a = 1;
        int b = 2;
        int c = a + b;
        cout << c << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    assert "_Ptr" not in py_code
    assert "[1]" not in py_code
    out = run_py(py_code).strip()
    assert out == "3"
