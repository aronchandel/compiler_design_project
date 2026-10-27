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

    assert render("a - (b - c)") == "a - (b - c)"

def test_pyexpr_left_assoc_no_parens():

    assert render("a - b - c") == "a - b - c"

def test_pyexpr_unary_minus_over_binary():

    assert render("-(a + b)") == "-(a + b)"

def test_pyexpr_unary_minus_double():

    assert render("-(-x)") == "-(-x)"

def test_pyexpr_mixed_precedence_and_mod():

    assert render("a * (b + c) % d") == "a * (b + c) % d"

def test_pyexpr_division_assoc():

    assert render("a / (b / c)") == "a // (b // c)"

def test_pyexpr_unary_plus():

    assert render("+x") == "x"

def test_pyexpr_nested_complex():

    res = render("(a + b) * (c - d) / (e % f)")
    assert res == "(a + b) * (c - d) // (e % f)"

def test_pyexpr_left_division():

    assert render("a / b / c") == "a // b // c"
