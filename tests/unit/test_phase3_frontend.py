import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.frontend.ast_nodes import (
    IfStmt,
    WhileStmt,
    ForStmt,
    IncDecStmt,
    AssignStmt,
    CallExpr,
    CallStmt,
    ReturnStmt,
    Block,
    FunctionDef,
    Condition,
    BinaryExpr,
    UnaryExpr,
)

def parse_src(src_code: str):
    source = SourceFile("test.cpp", src_code)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    return ast, sink

def test_parse_if_without_else():
    code = "int main() { if (x < 10) { x += 1; } return 0; }"
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    body = ast.functions[0].body.statements
    if_stmt = body[0]
    assert isinstance(if_stmt, IfStmt)
    assert isinstance(if_stmt.cond, Condition)
    assert if_stmt.cond.op == "<"
    assert if_stmt.else_body is None

def test_parse_if_with_else():
    code = "int main() { if (x == 0) { y = 1; } else { y = 2; } return 0; }"
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    if_stmt = ast.functions[0].body.statements[0]
    assert isinstance(if_stmt, IfStmt)
    assert isinstance(if_stmt.else_body, Block)

def test_parse_dangling_else_binds_to_innermost_if():
    code = """
    int main() {
        if (a > 0)
            if (b > 0)
                x = 1;
            else
                x = 2;
        return 0;
    }
    """
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    outer_if = ast.functions[0].body.statements[0]
    assert isinstance(outer_if, IfStmt)
    assert outer_if.else_body is None
    inner_if = outer_if.then_body
    if isinstance(inner_if, Block):
        inner_if = inner_if.statements[0]
    assert isinstance(inner_if, IfStmt)
    assert inner_if.else_body is not None

def test_parse_while_loop():
    code = "int main() { while (n != 0) { n -= 1; } return 0; }"
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    while_stmt = ast.functions[0].body.statements[0]
    assert isinstance(while_stmt, WhileStmt)
    assert while_stmt.cond.op == "!="

def test_parse_for_loop():
    code = "int main() { for (int i = 0; i < 10; ++i) { sum += i; } return 0; }"
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    for_stmt = ast.functions[0].body.statements[0]
    assert isinstance(for_stmt, ForStmt)
    assert for_stmt.init is not None
    assert for_stmt.cond is not None
    assert for_stmt.cond.op == "<"
    assert isinstance(for_stmt.update, IncDecStmt)
    assert for_stmt.update.is_prefix is True

def test_parse_for_without_condition_fails():
    code = "int main() { for (int i = 0; ; i++) { } return 0; }"
    ast, sink = parse_src(code)
    assert sink.has_errors()
    assert any(d.code == "E2001" for d in sink.diagnostics)

def test_parse_compound_assignments():
    ops = ["+=", "-=", "*=", "/=", "%="]
    for op in ops:
        code = f"int main() {{ x {op} 5; return 0; }}"
        ast, sink = parse_src(code)
        assert not sink.has_errors(), f"Failed on {op}"
        stmt = ast.functions[0].body.statements[0]
        assert isinstance(stmt, AssignStmt)
        assert stmt.op == op

def test_parse_prefix_and_postfix_inc_dec():
    code = """
    int main() {
        ++x;
        x++;
        --y;
        y--;
        return 0;
    }
    """
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    stmts = ast.functions[0].body.statements
    assert isinstance(stmts[0], IncDecStmt) and stmts[0].op == "++" and stmts[0].is_prefix
    assert isinstance(stmts[1], IncDecStmt) and stmts[1].op == "++" and not stmts[1].is_prefix
    assert isinstance(stmts[2], IncDecStmt) and stmts[2].op == "--" and stmts[2].is_prefix
    assert isinstance(stmts[3], IncDecStmt) and stmts[3].op == "--" and not stmts[3].is_prefix

def test_parse_multiple_functions_with_params():
    code = """
    int add(int a, int b) {
        return a + b;
    }
    void greet(int x) {
        cout << x << endl;
    }
    int main() {
        int r = add(2, 3);
        greet(r);
        return 0;
    }
    """
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    assert len(ast.functions) == 3
    fn_add = ast.functions[0]
    assert fn_add.name == "add"
    assert len(fn_add.params) == 2
    assert fn_add.params[0].name == "a"
    assert fn_add.params[1].name == "b"

    fn_greet = ast.functions[1]
    assert fn_greet.name == "greet"
    assert fn_greet.return_type.name == "void"
    assert len(fn_greet.params) == 1

    fn_main = ast.functions[2]
    assert isinstance(fn_main.body.statements[0].declarators[0].init, CallExpr)
    assert isinstance(fn_main.body.statements[1], CallStmt)

def test_parse_nested_blocks():
    code = """
    int main() {
        int x = 1;
        {
            int x = 2;
            {
                int y = x;
            }
        }
        return 0;
    }
    """
    ast, sink = parse_src(code)
    assert not sink.has_errors()
    stmts = ast.functions[0].body.statements
    assert isinstance(stmts[1], Block)
    inner_block = stmts[1].statements[1]
    assert isinstance(inner_block, Block)

@pytest.mark.parametrize(
    "token, code_snip",
    [
        ("&&", "int main() { if (a && b) {} return 0; }"),
        ("||", "int main() { if (a || b) {} return 0; }"),
        ("!", "int main() { if (!a) {} return 0; }"),
        ("break", "int main() { while (1) { break; } return 0; }"),
        ("continue", "int main() { while (1) { continue; } return 0; }"),
        ("switch", "int main() { switch(x) {} return 0; }"),
        ("goto", "int main() { goto end; end: return 0; }"),
        ("float", "float foo() { return 0.0; } int main() { return 0; }"),
    ],
)
def test_unsupported_tokens_rejected(token, code_snip):
    _, sink = parse_src(code_snip)
    assert sink.has_errors()
    assert any(d.code in ("E4001", "E4002", "E2001") for d in sink.diagnostics)

def test_expression_position_inc_dec_rejected():
    code = "int main() { int y = ++x; return 0; }"
    _, sink = parse_src(code)
    assert sink.has_errors()
    assert any(d.code == "E4001" for d in sink.diagnostics)

def test_unsupported_ternary_rejected():
    code = "int main() { int y = a ? b : c; return 0; }"
    _, sink = parse_src(code)
    assert sink.has_errors()
    assert any(d.code in ("E4001", "E2001") for d in sink.diagnostics)
