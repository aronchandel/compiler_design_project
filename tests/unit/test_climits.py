import sys
import subprocess
import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig, TargetModel
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.codegen.python_gen import generate

def compile_cpp(code: str, config: CompilerConfig | None = None) -> tuple[str, DiagnosticSink]:
    src = SourceFile("test.cpp", code)
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    ast_tree = parse(tokens, sink)
    if sink.has_errors():
        return "", sink
    if config is None:
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

def test_climits_header_recognition():
    code = """
    #include <climits>
    #include <iostream>
    using namespace std;
    int main() {
        cout << INT_MAX << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    assert "INT_MAX" not in py_code
    out = run_py(py_code)
    assert str(TargetModel().int_max) in out

def test_climits_missing_macro_diagnostic():

    code = """
    #include <iostream>
    using namespace std;
    int main() {
        cout << INT_MAX << endl;
        return 0;
    }
    """
    _, sink = compile_cpp(code)
    assert sink.has_errors()
    assert any(d.code == "E3001" for d in sink.diagnostics)

def test_all_climits_macros():
    code = """
    #include <iostream>
    #include <climits>
    using namespace std;
    int main() {
        cout << CHAR_BIT << endl;
        cout << SCHAR_MIN << endl;
        cout << SCHAR_MAX << endl;
        cout << UCHAR_MAX << endl;
        cout << SHRT_MIN << endl;
        cout << SHRT_MAX << endl;
        cout << USHRT_MAX << endl;
        cout << INT_MIN << endl;
        cout << INT_MAX << endl;
        cout << UINT_MAX << endl;
        cout << LONG_MIN << endl;
        cout << LONG_MAX << endl;
        cout << ULONG_MAX << endl;
        cout << LLONG_MIN << endl;
        cout << LLONG_MAX << endl;
        cout << ULLONG_MAX << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    out = run_py(py_code).strip().splitlines()
    target = TargetModel()
    expected = [
        str(target.char_bit),
        str(target.schar_min),
        str(target.schar_max),
        str(target.uchar_max),
        str(target.shrt_min),
        str(target.shrt_max),
        str(target.ushrt_max),
        str(target.int_min),
        str(target.int_max),
        str(target.uint_max),
        str(target.long_min),
        str(target.long_max),
        str(target.ulong_max),
        str(target.llong_min),
        str(target.llong_max),
        str(target.ullong_max),
    ]
    assert out == expected

def test_climits_macro_in_expressions():
    code = """
    #include <climits>
    #include <iostream>
    using namespace std;
    int main() {
        int a = INT_MAX - 100;
        int b = INT_MIN + 50;
        cout << a << " " << b << endl;
        return 0;
    }
    """
    py_code, sink = compile_cpp(code)
    assert not sink.has_errors()
    target = TargetModel()
    out = run_py(py_code).strip()
    assert out == f"{target.int_max - 100} {target.int_min + 50}"

def test_target_model_non_hardcoded_limits():

    t32 = TargetModel(long_bits=32)
    assert t32.long_max == 2147483647
    assert t32.long_min == -2147483648
    assert t32.ulong_max == 4294967295

    t64 = TargetModel(long_bits=64)
    assert t64.long_max == 9223372036854775807
    assert t64.long_min == -9223372036854775808
    assert t64.ulong_max == 18446744073709551615
