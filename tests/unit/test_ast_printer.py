import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.frontend.ast_printer import dump


def test_ast_printer_empty_main():
    source = SourceFile("test.cpp", "int main() {}")
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    out = dump(ast)
    assert "Program uses_std=False" in out
    assert "FunctionDef main -> int" in out


def test_ast_printer_golden():
    source = SourceFile("test.cpp", "int main() { int x = 42; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    out = dump(ast)
    expected = "\n".join([
        "Program uses_std=False",
        "└─ FunctionDef main -> int",
        "   └─ Block",
        "      ├─ DeclStmt int",
        "      │  └─ Declarator x",
        "      │     └─ IntLiteral 42",
        "      └─ ReturnStmt",
        "         └─ IntLiteral 0",
    ])
    assert out.strip() == expected.strip()
