import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.ir.model import Opcode, IRType, Const, VarRef, TempRef, StrConst

def compile_to_ir(text: str):
    source = SourceFile("test.cpp", text)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    assert not sink.has_errors()
    info = analyze(ast, CompilerConfig(), sink)
    assert not sink.has_errors()
    module = build_ir(ast, info, CompilerConfig())
    return module, module.functions[0]

def test_builder_decl_without_init():
    _, func = compile_to_ir("int main() { int x; }")

    assert len(func.body) == 2
    assert func.body[0].opcode == Opcode.DECLARE
    assert func.body[0].dst.ir_name == "x"
    assert func.body[1].opcode == Opcode.RETURN

def test_builder_decl_with_init():
    _, func = compile_to_ir("int main() { int x = 10; }")
    assert len(func.body) == 3
    assert func.body[0].opcode == Opcode.DECLARE
    assert func.body[1].opcode == Opcode.ASSIGN
    assert func.body[1].operands[0] == Const(10, IRType.I32)

def test_builder_multi_decl():
    _, func = compile_to_ir("int main() { int a = 1, b = 2; }")
    assert func.body[0].opcode == Opcode.DECLARE
    assert func.body[1].opcode == Opcode.ASSIGN
    assert func.body[2].opcode == Opcode.DECLARE
    assert func.body[3].opcode == Opcode.ASSIGN

def test_builder_assign_stmt():
    _, func = compile_to_ir("int main() { int x; x = 42; }")
    assign_instr = func.body[1]
    assert assign_instr.opcode == Opcode.ASSIGN
    assert assign_instr.dst.ir_name == "x"
    assert assign_instr.operands[0] == Const(42, IRType.I32)

def test_builder_input_stmt_multiple():
    _, func = compile_to_ir("using namespace std; int main() { int a, b; cin >> a >> b; }")

    reads = [i for i in func.body if i.opcode == Opcode.READ]
    assert len(reads) == 2
    assert reads[0].dst.ir_name == "a"
    assert reads[1].dst.ir_name == "b"

def test_builder_output_no_endl():
    _, func = compile_to_ir("using namespace std; int main() { int x = 5; cout << x; }")
    prints = [i for i in func.body if i.opcode == Opcode.PRINT]
    assert len(prints) == 1
    assert prints[0].newline is False
    assert len(prints[0].operands) == 1

def test_builder_output_with_trailing_endl():
    _, func = compile_to_ir("using namespace std; int main() { int x = 5; cout << x << endl; }")
    prints = [i for i in func.body if i.opcode == Opcode.PRINT]
    assert len(prints) == 1
    assert prints[0].newline is True
    assert len(prints[0].operands) == 1

def test_builder_output_non_final_endl():
    _, func = compile_to_ir('using namespace std; int main() { cout << 1 << endl << 2; }')
    prints = [i for i in func.body if i.opcode == Opcode.PRINT]
    assert len(prints) == 1
    assert prints[0].newline is False

    assert prints[0].operands[1] == StrConst("\n")

def test_builder_output_endl_alone():
    _, func = compile_to_ir("using namespace std; int main() { cout << endl; }")
    prints = [i for i in func.body if i.opcode == Opcode.PRINT]
    assert len(prints) == 1
    assert prints[0].newline is True
    assert len(prints[0].operands) == 0

def test_builder_explicit_return():
    _, func = compile_to_ir("int main() { return 0; }")
    assert len(func.body) == 1
    assert func.body[0].opcode == Opcode.RETURN
    assert func.body[0].operands[0] == Const(0, IRType.I32)

def test_builder_implicit_return_closing_brace_span():
    _, func = compile_to_ir("int main() { int x = 1; }")
    last_instr = func.body[-1]
    assert last_instr.opcode == Opcode.RETURN
    assert last_instr.operands[0] == Const(0, IRType.I32)
    assert last_instr.span is not None

def test_builder_evaluation_order_left_before_right():

    _, func = compile_to_ir("int main() { int a = 1, b = 2, c = 3, d = 4; int x = (a - b) - (c - d); }")
    subs = [i for i in func.body if i.opcode == Opcode.SUB]
    assert len(subs) == 3

    assert subs[0].dst.temp_id == "t0"
    assert subs[0].operands[0].ir_name == "a"
    assert subs[0].operands[1].ir_name == "b"

    assert subs[1].dst.temp_id == "t1"
    assert subs[1].operands[0].ir_name == "c"
    assert subs[1].operands[1].ir_name == "d"

    assert subs[2].dst.temp_id == "t2"
    assert subs[2].operands[0].temp_id == "t0"
    assert subs[2].operands[1].temp_id == "t1"

def test_builder_unary_minus_and_plus():
    _, func = compile_to_ir("int main() { int a = 1; int b = -a; int c = +a; }")
    negs = [i for i in func.body if i.opcode == Opcode.NEG]
    assert len(negs) == 1
    assert negs[0].operands[0].ir_name == "a"

    assigns = [i for i in func.body if i.opcode == Opcode.ASSIGN and i.dst.ir_name == "c"]
    assert len(assigns) == 1
    assert assigns[0].operands[0].ir_name == "a"

def test_builder_cpp_div_mod_opcodes():
    _, func = compile_to_ir("int main() { int x = 10 / 2; int y = 10 % 3; }")
    divs = [i for i in func.body if i.opcode == Opcode.DIV]
    mods = [i for i in func.body if i.opcode == Opcode.MOD]
    assert len(divs) == 1
    assert len(mods) == 1
