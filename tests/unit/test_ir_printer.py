"""Unit tests for cpp2py/ir/printer.py."""

from pathlib import Path
import pytest
from cpp2py.source import SourceFile, SourceSpan, Pos
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.ir.printer import format_module, format_instruction
from cpp2py.ir.model import (
    Instruction,
    Opcode,
    VarRef,
    TempRef,
    Const,
    StrConst,
    LabelRef,
    IRType,
    IRFunction,
    IRModule,
)


def test_printer_fold_demo_golden_character_for_character():
    fold_cpp = Path("examples/worked/fold_demo.cpp").read_text(encoding="utf-8")
    source = SourceFile("examples/worked/fold_demo.cpp", fold_cpp)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    info = analyze(ast, CompilerConfig(), sink)
    module = build_ir(ast, info, CompilerConfig())
    formatted = format_module(module)

    golden = Path("examples/worked/fold_demo.ir.golden").read_text(encoding="utf-8")
    assert formatted == golden


def test_printer_print_instruction_endl_variations():
    # With endl
    p1 = Instruction("op_0", Opcode.PRINT, operands=(VarRef(1, "x"),), newline=True)
    assert "print x, endl" in format_instruction(p1)

    # Without endl
    p2 = Instruction("op_1", Opcode.PRINT, operands=(VarRef(1, "x"),), newline=False)
    assert "print x" in format_instruction(p2)
    assert "endl" not in format_instruction(p2)

    # Alone endl
    p3 = Instruction("op_2", Opcode.PRINT, operands=(), newline=True)
    assert "print endl" in format_instruction(p3)


def test_printer_read_instruction():
    r = Instruction("op_3", Opcode.READ, dst=VarRef(1, "val"), operands=(VarRef(1, "val"),))
    assert "read val" in format_instruction(r)


def test_printer_control_flow_instructions():
    lbl = Instruction("op_4", Opcode.LABEL, label_name="loop_head_r0")
    assert "loop_head_r0:" in format_instruction(lbl)

    jmp = Instruction("op_5", Opcode.JUMP, label_name="loop_head_r0")
    assert "jump loop_head_r0" in format_instruction(jmp)

    br = Instruction("op_6", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("loop_body_r0"), LabelRef("loop_end_r0")))
    assert "branch t0, loop_body_r0, loop_end_r0" in format_instruction(br)


def test_printer_cmp_and_call_instructions():
    cmp_i = Instruction("op_7", Opcode.CMP, dst=TempRef("t1", IRType.BOOL), operands=(VarRef(1, "i"), Const(3)), cmp_op="lt")
    assert "t1 = cmp lt i, 3" in format_instruction(cmp_i)

    call_i = Instruction("op_8", Opcode.CALL, dst=TempRef("t2"), operands=(Const(5),), func_name="foo")
    assert "t2 = call foo(5)" in format_instruction(call_i)


def test_printer_instruction_with_origin():
    span = SourceSpan("test.cpp", Pos(5, 5, 0), Pos(5, 10, 5))
    instr = Instruction("op_2", Opcode.ASSIGN, dst=VarRef(1, "a"), operands=(Const(42),), span=span, origin=("op_1",))
    text = format_instruction(instr)
    assert "; L5:5     [derived from op_1]" in text
