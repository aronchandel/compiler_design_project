"""Unit tests for long long support (Phase 5)."""

import pytest

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.semantics.types import IntType
from cpp2py.config import CompilerConfig, TargetModel
from cpp2py.ir.builder import build_ir
from cpp2py.ir.verifier import verify_module
from cpp2py.ir.model import Opcode, IRType


def test_parse_long_long_variable():
    src = SourceFile("test.cpp", "int main() { long long x = 123; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    assert not sink.has_errors()
    prog = parse(tokens, sink)
    assert not sink.has_errors()
    assert prog is not None
    decl = prog.functions[0].body.statements[0]
    assert decl.type_spec.name == "long long"


def test_parse_standalone_long_rejected():
    src = SourceFile("test.cpp", "int main() { long x = 123; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    assert not sink.has_errors()
    prog = parse(tokens, sink)
    assert sink.has_errors()
    assert any(e.code == "E4002" for e in sink.errors)


def test_semantics_long_long_type():
    src = SourceFile("test.cpp", "int main() { long long x = 10; int y = 20; return 0; }")
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    assert info is not None
    decl_x = prog.functions[0].body.statements[0].declarators[0]
    decl_y = prog.functions[0].body.statements[1].declarators[0]
    sym_x = info.symbols_by_node[decl_x.node_id]
    sym_y = info.symbols_by_node[decl_y.node_id]
    assert isinstance(sym_x.type, IntType) and sym_x.type.bits == 64
    assert isinstance(sym_y.type, IntType) and sym_y.type.bits == 32


def test_semantics_usual_arithmetic_promotions():
    src = SourceFile("test.cpp", """
    int main() {
        int a = 5;
        long long b = 10;
        long long c = a + b;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    decl_c = prog.functions[0].body.statements[2].declarators[0]
    plus_expr = decl_c.init
    expr_type = info.type_by_node[plus_expr.node_id]
    assert isinstance(expr_type, IntType) and expr_type.bits == 64


def test_long_long_literal_threshold():
    # 2^31 - 1 is i32, 2^31 is i64
    src = SourceFile("test.cpp", """
    int main() {
        long long x = 2147483648;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    init_expr = prog.functions[0].body.statements[0].declarators[0].init
    expr_type = info.type_by_node[init_expr.node_id]
    assert isinstance(expr_type, IntType) and expr_type.bits == 64


def test_long_long_function_params_and_return():
    src = SourceFile("test.cpp", """
    long long add_ll(long long a, int b) {
        return a + b;
    }
    int main() {
        long long r = add_ll(100, 50);
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, cfg)
    assert verify_module(mod, sink)
    fn = mod.functions[0]
    assert fn.return_type == IRType.I64
    assert fn.params[0].type == IRType.I64
    assert fn.params[1].type == IRType.I32


def test_long_long_subtraction_promotion():
    src = SourceFile("test.cpp", "int main() { long long a = 10; int b = 3; long long c = a - b; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_multiplication_promotion():
    src = SourceFile("test.cpp", "int main() { int a = 100000; long long b = 200000; long long c = a * b; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_division_promotion():
    src = SourceFile("test.cpp", "int main() { long long a = 100; int b = 5; long long c = a / b; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_modulo_promotion():
    src = SourceFile("test.cpp", "int main() { long long a = 100; int b = 7; long long c = a % b; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_comparison_promotion():
    src = SourceFile("test.cpp", "int main() { int a = 5; long long b = 10; if (a < b) { return 1; } return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_for_loop_decl():
    src = SourceFile("test.cpp", "int main() { for (long long i = 0; i < 10; ++i) {} return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_while_loop_cond():
    src = SourceFile("test.cpp", "int main() { long long i = 10; while (i > 0) { --i; } return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_max_literal():
    # 9223372036854775807 is LLONG_MAX
    src = SourceFile("test.cpp", "int main() { long long x = 9223372036854775807; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    assert not sink.has_errors()
    prog = parse(tokens, sink)
    assert not sink.has_errors()


def test_long_long_too_large_literal_e1004():
    # 9223372036854775808 exceeds LLONG_MAX
    src = SourceFile("test.cpp", "int main() { long long x = 9223372036854775808; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    assert sink.has_errors()
    assert any(e.code == "E1004" for e in sink.errors)


def test_long_long_unary_negation():
    src = SourceFile("test.cpp", "int main() { long long a = 42; long long b = -a; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_cin_cout():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        long long x;
        cin >> x;
        cout << x << endl;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)


def test_long_long_assign_narrowing_cast():
    src = SourceFile("test.cpp", "int main() { long long a = 100; int b = a; return 0; }")
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, CompilerConfig(), sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, CompilerConfig())
    assert verify_module(mod, sink)
    # Check that cast opcode was emitted for narrowing conversion
    cast_instrs = [ins for ins in mod.functions[0].body if ins.opcode == Opcode.CAST]
    assert len(cast_instrs) >= 1
