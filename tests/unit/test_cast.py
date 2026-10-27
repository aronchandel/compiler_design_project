import pytest

from cpp2py.source import SourceFile, SourceSpan, Pos
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.config import CompilerConfig, TargetModel
from cpp2py.ir.builder import build_ir
from cpp2py.ir.verifier import verify_module
from cpp2py.ir.model import Opcode, IRType, Instruction, Const, TempRef, VarRef, IRFunction, IRModule, IdAllocator
from cpp2py.transforms.constant_fold import ConstantFoldPass
from cpp2py.transforms.manager import IRRewriter, PassContext
from cpp2py.transforms.log import TransformLog

def test_builder_emits_cast_on_mixed_types():
    src = SourceFile("test.cpp", """
    int main() {
        int a = 10;
        long long b = 20;
        long long c = a + b;
        int d = b;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    assert verify_module(mod, sink)
    cast_instrs = [instr for instr in mod.functions[0].body if instr.opcode == Opcode.CAST]
    assert len(cast_instrs) >= 2

def test_verifier_accepts_valid_cast():
    sink = DiagnosticSink()
    func = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction("op_0", Opcode.DECLARE, dst=VarRef(1, "x", IRType.I32), operands=(VarRef(1, "x", IRType.I32),)),
            Instruction("op_1", Opcode.CAST, dst=TempRef("t0", IRType.I64), operands=(VarRef(1, "x", IRType.I32),)),
            Instruction("op_2", Opcode.RETURN, operands=(Const(0, IRType.I32),)),
        ]
    )
    mod = IRModule([func])
    assert verify_module(mod, sink)

def test_verifier_rejects_bool_cast():
    sink = DiagnosticSink()
    func = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction("op_0", Opcode.DECLARE, dst=VarRef(1, "x", IRType.I32), operands=(VarRef(1, "x", IRType.I32),)),
            Instruction("op_1", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(VarRef(1, "x", IRType.I32), Const(0, IRType.I32)), cmp_op="eq"),
            Instruction("op_2", Opcode.CAST, dst=TempRef("t1", IRType.I32), operands=(TempRef("t0", IRType.BOOL),)),
            Instruction("op_3", Opcode.RETURN, operands=(Const(0, IRType.I32),)),
        ]
    )
    mod = IRModule([func])
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_constant_fold_cast_widening():
    target = TargetModel()
    cfg = CompilerConfig(target=target)
    sink = DiagnosticSink()
    ctx = PassContext(cfg, sink)
    log = TransformLog()
    allocator = IdAllocator()
    rw = IRRewriter(log=log, allocator=allocator)
    func = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction("op_0", Opcode.CAST, dst=TempRef("t0", IRType.I64), operands=(Const(42, IRType.I32),)),
            Instruction("op_1", Opcode.RETURN, operands=(Const(0, IRType.I32),)),
        ]
    )
    ConstantFoldPass().run(func, rw, ctx)
    assert func.body[0].opcode == Opcode.ASSIGN
    assert isinstance(func.body[0].operands[0], Const)
    assert func.body[0].operands[0].value == 42
    assert func.body[0].operands[0].type == IRType.I64

def test_constant_fold_cast_narrowing_modular():
    target = TargetModel()
    cfg = CompilerConfig(target=target)
    sink = DiagnosticSink()
    ctx = PassContext(cfg, sink)
    log = TransformLog()
    allocator = IdAllocator()
    rw = IRRewriter(log=log, allocator=allocator)

    func = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction("op_0", Opcode.CAST, dst=TempRef("t0", IRType.I32), operands=(Const(2147483648, IRType.I64),)),
            Instruction("op_1", Opcode.RETURN, operands=(Const(0, IRType.I32),)),
        ]
    )
    ConstantFoldPass().run(func, rw, ctx)
    assert func.body[0].opcode == Opcode.ASSIGN
    assert isinstance(func.body[0].operands[0], Const)
    assert func.body[0].operands[0].value == -2147483648
    assert func.body[0].operands[0].type == IRType.I32
