import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.codegen.pyexpr import render_expr
from cpp2py.codegen.names import NameMangler


def parse_expression(expr_str: str):
    source = SourceFile("test.cpp", f"int main() {{ int x = {expr_str}; }}")
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    assert not sink.has_errors()
    decl = ast.main.body.statements[0]
    return decl.declarators[0].init


def render(expr_str: str) -> str:
    expr = parse_expression(expr_str)
    mangler = NameMangler()
    return render_expr(expr, mangler.mangle)


def test_pyexpr_right_assoc_parens():
    # a - (b - c)
    assert render("a - (b - c)") == "a - (b - c)"


def test_pyexpr_left_assoc_no_parens():
    # a - b - c
    assert render("a - b - c") == "a - b - c"


def test_pyexpr_unary_minus_over_binary():
    # -(a + b)
    assert render("-(a + b)") == "-(a + b)"


def test_pyexpr_unary_minus_double():
    # -(-x)
    assert render("-(-x)") == "-(-x)"


def test_pyexpr_mixed_precedence_and_mod():
    # a * (b + c) % d
    assert render("a * (b + c) % d") == "a * (b + c) % d"


def test_pyexpr_division_assoc():
    # a / (b / c)
    assert render("a / (b / c)") == "a // (b // c)"


def test_pyexpr_unary_plus():
    # +x emits x
    assert render("+x") == "x"


def test_pyexpr_nested_complex():
    # (a + b) * (c - d) / (e % f)
    res = render("(a + b) * (c - d) / (e % f)")
    assert res == "(a + b) * (c - d) // (e % f)"


def test_pyexpr_left_division():
    # a / b / c
    assert render("a / b / c") == "a // b // c"
