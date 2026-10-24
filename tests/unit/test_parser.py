import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.frontend.ast_nodes import (
    Program, FunctionDef, DeclStmt, AssignStmt, InputStmt, OutputStmt,
    ReturnStmt, BinaryExpr, UnaryExpr, IntLiteral, NameExpr
)


def parse_text(text: str):
    source = SourceFile("test.cpp", text)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    return ast, sink


def test_parse_empty_main():
    ast, sink = parse_text("int main() {}")
    assert not sink.has_errors()
    assert ast is not None
    assert ast.main.name == "main"
    assert len(ast.main.body.statements) == 0


def test_parse_declarations():
    text = "int main() { int a; int b = 10; int x, y = 20, z; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmts = ast.main.body.statements
    assert len(stmts) == 3
    assert isinstance(stmts[0], DeclStmt)
    assert len(stmts[0].declarators) == 1
    assert stmts[0].declarators[0].name == "a"
    assert stmts[0].declarators[0].init is None

    assert isinstance(stmts[1], DeclStmt)
    assert stmts[1].declarators[0].init is not None

    assert isinstance(stmts[2], DeclStmt)
    assert len(stmts[2].declarators) == 3


def test_parse_assignment():
    text = "int main() { int x; x = 42 + 1; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmts = ast.main.body.statements
    assert isinstance(stmts[1], AssignStmt)
    assert stmts[1].target.name == "x"
    assert isinstance(stmts[1].value, BinaryExpr)


def test_parse_cin():
    text = "int main() { int a, b; cin >> a >> b; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmt = ast.main.body.statements[1]
    assert isinstance(stmt, InputStmt)
    assert [t.name for t in stmt.targets] == ["a", "b"]


def test_parse_std_cin():
    text = "int main() { int a; std::cin >> a; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmt = ast.main.body.statements[1]
    assert isinstance(stmt, InputStmt)
    assert [t.name for t in stmt.targets] == ["a"]


def test_parse_cout_chain():
    text = 'int main() { cout << "val: " << 42 << endl; }'
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmt = ast.main.body.statements[0]
    assert isinstance(stmt, OutputStmt)
    assert len(stmt.items) == 3


def test_parse_return_0():
    text = "int main() { return 0; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmt = ast.main.body.statements[0]
    assert isinstance(stmt, ReturnStmt)
    assert isinstance(stmt.value, IntLiteral)
    assert stmt.value.value == 0


def test_parse_precedence_and_associativity():
    text = "int main() { int x = 2 + 3 * 4; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    init_expr = ast.main.body.statements[0].declarators[0].init
    assert isinstance(init_expr, BinaryExpr)
    assert init_expr.op == "+"
    assert isinstance(init_expr.right, BinaryExpr)
    assert init_expr.right.op == "*"


def test_parse_parentheses():
    text = "int main() { int x = (2 + 3) * 4; }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    init_expr = ast.main.body.statements[0].declarators[0].init
    assert isinstance(init_expr, BinaryExpr)
    assert init_expr.op == "*"
    assert isinstance(init_expr.left, BinaryExpr)
    assert init_expr.left.op == "+"


def test_parse_unary_minus_and_plus():
    text = "int main() { int x = -a; int y = +b; int z = -(-a); }"
    ast, sink = parse_text(text)
    assert not sink.has_errors()
    stmts = ast.main.body.statements
    assert isinstance(stmts[0].declarators[0].init, UnaryExpr)
    assert stmts[0].declarators[0].init.op == "-"
    assert isinstance(stmts[1].declarators[0].init, UnaryExpr)
    assert stmts[1].declarators[0].init.op == "+"
    assert isinstance(stmts[2].declarators[0].init, UnaryExpr)


def test_parse_unsupported_type():
    text = "int main() { float x; }"
    _, sink = parse_text(text)
    assert sink.has_errors()
    assert any(e.code == "E4002" for e in sink.errors)


def test_parse_unsupported_break():
    text = "int main() { break; return 0; }"
    _, sink = parse_text(text)
    assert sink.has_errors()
    assert any(e.code == "E4001" for e in sink.errors)


def test_parse_unsupported_switch():
    text = "int main() { switch (1) {} return 0; }"
    _, sink = parse_text(text)
    assert sink.has_errors()
    assert any(e.code == "E4001" for e in sink.errors)


def test_parse_missing_semicolon():
    text = "int main() { int x = 1 return 0; }"
    _, sink = parse_text(text)
    assert sink.has_errors()
    assert any(e.code == "E2002" for e in sink.errors)


def test_parse_no_main():
    text = "int foo() { return 0; }"
    _, sink = parse_text(text)
    assert sink.has_errors()
    # Either E4001 (other function) or E2001
    assert any(e.code in ("E2001", "E4001") for e in sink.errors)


def test_parse_error_recovery_multiple_errors():
    # Two independent missing semicolons
    text = "int main() { int a = 1 \n int b = 2 \n return 0; }"
    _, sink = parse_text(text)
    assert sink.has_errors()
    errors = [e for e in sink.errors if e.code == "E2002"]
    assert len(errors) >= 2
