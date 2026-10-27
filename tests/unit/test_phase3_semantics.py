import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze

def analyze_src(code: str):
    source = SourceFile("test.cpp", code)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    config = CompilerConfig()
    info = analyze(ast, config, sink)
    return info, sink

def test_shadowing_in_nested_block():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 10;
        {
            int x = 20;
            cout << x << endl;
        }
        cout << x << endl;
        return 0;
    }
    """
    info, sink = analyze_src(code)
    assert not sink.has_errors()
    assert info is not None

def test_definite_assignment_both_branches_assigned():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        int cond = 1;
        if (cond > 0) {
            x = 42;
        } else {
            x = 24;
        }
        cout << x << endl;
        return 0;
    }
    """
    info, sink = analyze_src(code)
    assert not sink.has_errors()

def test_definite_assignment_one_branch_only_fails():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        int cond = 1;
        if (cond > 0) {
            x = 42;
        } else {
            // not assigned
        }
        cout << x << endl;
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3003" for d in sink.diagnostics)

def test_definite_assignment_no_else_fails():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        int cond = 1;
        if (cond > 0) {
            x = 42;
        }
        cout << x << endl;
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3003" for d in sink.diagnostics)

def test_definite_assignment_loop_body_not_counted_after_loop():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        int i = 0;
        while (i < 5) {
            x = 10;
            i += 1;
        }
        cout << x << endl;
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3003" for d in sink.diagnostics)

def test_for_init_counts_as_assigned():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        for (int i = 0; i < 5; i++) {
            cout << i << endl;
        }
        return 0;
    }
    """
    info, sink = analyze_src(code)
    assert not sink.has_errors()

def test_missing_return_non_void_function():
    code = """
    int foo(int a) {
        if (a > 0) {
            return a;
        }
        // missing return when a <= 0
    }
    int main() {
        return foo(1);
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3007" for d in sink.diagnostics)

def test_main_exempt_from_missing_return():
    code = """
    int main() {
        int x = 1;
    }
    """
    info, sink = analyze_src(code)
    assert not sink.has_errors()

def test_void_function_with_return_value_fails():
    code = """
    void foo() {
        return 42;
    }
    int main() {
        foo();
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3004" for d in sink.diagnostics)

def test_void_function_value_used_fails():
    code = """
    void foo() {}
    int main() {
        int x = foo();
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3004" for d in sink.diagnostics)

def test_call_before_define_fails():
    code = """
    int main() {
        return bar();
    }
    int bar() {
        return 1;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3001" for d in sink.diagnostics)

def test_recursion_allowed():
    code = """
    int fact(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * fact(n - 1);
    }
    int main() {
        return fact(5);
    }
    """
    info, sink = analyze_src(code)
    assert not sink.has_errors()

def test_argument_count_mismatch():
    code = """
    int add(int a, int b) {
        return a + b;
    }
    int main() {
        return add(1);
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3006" for d in sink.diagnostics)

def test_relational_operator_as_value_fails():
    code = """
    int main() {
        int x = 5 < 10;
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3008" for d in sink.diagnostics)

def test_duplicate_function_names_fail():
    code = """
    int foo() { return 1; }
    int foo() { return 2; }
    int main() { return 0; }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E3002" for d in sink.diagnostics)

def test_main_with_parameters_rejected():
    code = """
    int main(int argc) {
        return 0;
    }
    """
    _, sink = analyze_src(code)
    assert sink.has_errors()
    assert any(d.code == "E4001" for d in sink.diagnostics)
