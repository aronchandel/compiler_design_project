import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze


def check_semantics(text: str):
    source = SourceFile("test.cpp", text)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    if sink.has_errors():
        return None, sink
    sem = analyze(ast, CompilerConfig(), sink)
    return sem, sink


def test_semantics_valid_program():
    text = "int main() { int a = 1; int b = a + 2; return 0; }"
    sem, sink = check_semantics(text)
    assert not sink.has_errors()
    assert sem is not None


def test_semantics_undeclared_variable():
    text = "int main() { x = 1; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E3001" for e in sink.errors)


def test_semantics_unqualified_iostream_without_using():
    text = "int main() { cout << 1; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E3001" for e in sink.errors)


def test_semantics_qualified_iostream_valid():
    text = "int main() { std::cout << 1; }"
    _, sink = check_semantics(text)
    assert not sink.has_errors()


def test_semantics_using_namespace_std():
    text = "using namespace std; int main() { cout << 1 << endl; }"
    _, sink = check_semantics(text)
    assert not sink.has_errors()


def test_semantics_redeclaration():
    text = "int main() { int x = 1; int x = 2; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E3002" for e in sink.errors)


def test_semantics_reserved_identifier_declaration():
    text = "int main() { int cout = 1; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E3002" for e in sink.errors)


def test_semantics_use_before_init():
    text = "int main() { int x; int y = x + 1; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E3003" for e in sink.errors)


def test_semantics_cin_initializes_var():
    text = "using namespace std; int main() { int x; cin >> x; int y = x + 1; }"
    _, sink = check_semantics(text)
    assert not sink.has_errors()


def test_semantics_assignment_initializes_var():
    text = "int main() { int x; x = 5; int y = x + 1; }"
    _, sink = check_semantics(text)
    assert not sink.has_errors()


def test_semantics_cin_undeclared_target():
    text = "using namespace std; int main() { cin >> x; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code in ("E3001", "E3005") for e in sink.errors)


def test_semantics_invalid_return_value():
    text = "int main() { return 1; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E4001" for e in sink.errors)


def test_semantics_return_not_last():
    text = "int main() { return 0; int x = 1; }"
    _, sink = check_semantics(text)
    assert sink.has_errors()
    assert any(e.code == "E4001" for e in sink.errors)
