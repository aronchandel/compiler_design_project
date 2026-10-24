"""Unit tests for Phase 3 verifier checks.

Verifies:
- AC3.5: Builder output for all Phase 1 and Phase 3 examples is accepted.
- AC3.5: Rejection of >= 6 hand-built canonical shape violations with E5001.
"""

from pathlib import Path
import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.ir.verifier import verify_module
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    VarRef,
    TempRef,
    LabelRef,
    IRType,
)


def make_module(body: list[Instruction]) -> tuple[IRModule, DiagnosticSink]:
    func = IRFunction(name="main", params=(), return_type=IRType.I32, body=body)
    mod = IRModule(functions=[func], source_name="test.cpp")
    sink = DiagnosticSink()
    return mod, sink


def test_ac3_5_verifier_accepts_all_phase3_examples():
    """Verifier accepts builder output for every Phase 3 example program."""
    examples_dir = Path("examples/phase3")
    cpp_files = sorted(examples_dir.glob("*.cpp"))
    assert len(cpp_files) >= 14, f"Found {len(cpp_files)} files in examples/phase3"

    for cpp_file in cpp_files:
        code = cpp_file.read_text(encoding="utf-8")
        src = SourceFile(str(cpp_file), code)
        sink = DiagnosticSink()
        tokens = tokenize(src, sink)
        ast = parse(tokens, sink)
        assert not sink.has_errors(), f"Parse failed on {cpp_file.name}: {sink.diagnostics}"
        config = CompilerConfig()
        info = analyze(ast, config, sink)
        assert not sink.has_errors(), f"Semantics failed on {cpp_file.name}: {sink.diagnostics}"
        module = build_ir(ast, info, config)

        v_sink = DiagnosticSink()
        assert verify_module(module, v_sink), f"Verifier failed on {cpp_file.name}: {v_sink.diagnostics}"
        assert not v_sink.has_errors()


def test_shape_violation_1_mismatched_region_in_branch():
    # Targets valid roles but from different regions (r0 vs r1)
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="if_then_r0", operands=(LabelRef("if_then_r0"),)),
        Instruction("op_1", Opcode.LABEL, label_name="if_else_r1", operands=(LabelRef("if_else_r1"),)),
        Instruction("op_2", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_3", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("if_then_r0"), LabelRef("if_else_r1"))),
        Instruction("op_4", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)


def test_shape_violation_2_missing_jump_to_if_end():
    # If-shape missing jump if_end_r0 after then-body
    body = [
        Instruction("op_0", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_1", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("if_then_r0"), LabelRef("if_else_r0"))),
        Instruction("op_2", Opcode.LABEL, label_name="if_then_r0", operands=(LabelRef("if_then_r0"),)),
        # Missing jump if_end_r0 here
        Instruction("op_3", Opcode.LABEL, label_name="if_else_r0", operands=(LabelRef("if_else_r0"),)),
        Instruction("op_4", Opcode.LABEL, label_name="if_end_r0", operands=(LabelRef("if_end_r0"),)),
        Instruction("op_5", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)


def test_shape_violation_3_non_canonical_ordering_in_if():
    # else before then
    body = [
        Instruction("op_0", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_1", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("if_then_r0"), LabelRef("if_else_r0"))),
        Instruction("op_2", Opcode.LABEL, label_name="if_else_r0", operands=(LabelRef("if_else_r0"),)),
        Instruction("op_3", Opcode.LABEL, label_name="if_then_r0", operands=(LabelRef("if_then_r0"),)),
        Instruction("op_4", Opcode.JUMP, label_name="if_end_r0", operands=(LabelRef("if_end_r0"),)),
        Instruction("op_5", Opcode.LABEL, label_name="if_end_r0", operands=(LabelRef("if_end_r0"),)),
        Instruction("op_6", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)


def test_shape_violation_4_loop_missing_head():
    # Loop branch without preceding loop_head label
    body = [
        Instruction("op_0", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_1", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("loop_body_r0"), LabelRef("loop_end_r0"))),
        Instruction("op_2", Opcode.LABEL, label_name="loop_body_r0", operands=(LabelRef("loop_body_r0"),)),
        Instruction("op_3", Opcode.JUMP, label_name="loop_head_r0", operands=(LabelRef("loop_head_r0"),)),
        Instruction("op_4", Opcode.LABEL, label_name="loop_end_r0", operands=(LabelRef("loop_end_r0"),)),
        Instruction("op_5", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)


def test_shape_violation_5_loop_missing_back_jump():
    # Loop body without jump to loop_head
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="loop_head_r0", operands=(LabelRef("loop_head_r0"),)),
        Instruction("op_1", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_2", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("loop_body_r0"), LabelRef("loop_end_r0"))),
        Instruction("op_3", Opcode.LABEL, label_name="loop_body_r0", operands=(LabelRef("loop_body_r0"),)),
        # Missing jump loop_head_r0
        Instruction("op_4", Opcode.LABEL, label_name="loop_end_r0", operands=(LabelRef("loop_end_r0"),)),
        Instruction("op_5", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)


def test_shape_violation_6_mixed_role_targets():
    # Mixing if_then and loop_end in one branch
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="if_then_r0", operands=(LabelRef("if_then_r0"),)),
        Instruction("op_1", Opcode.LABEL, label_name="loop_end_r0", operands=(LabelRef("loop_end_r0"),)),
        Instruction("op_2", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_3", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("if_then_r0"), LabelRef("loop_end_r0"))),
        Instruction("op_4", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)


def test_shape_violation_7_invalid_label_naming():
    # Branch target label doesn't match canonical role naming
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="my_custom_target", operands=(LabelRef("my_custom_target"),)),
        Instruction("op_1", Opcode.LABEL, label_name="other_target", operands=(LabelRef("other_target"),)),
        Instruction("op_2", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_3", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("my_custom_target"), LabelRef("other_target"))),
        Instruction("op_4", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(d.code == "E5001" for d in sink.diagnostics)
