import pytest
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    VarRef,
    TempRef,
    Const,
    LabelRef,
    IRType,
)
from cpp2py.ir.verifier import verify_module

def make_module(body: list[Instruction], return_type: IRType = IRType.I32, params: tuple = ()) -> tuple[IRModule, DiagnosticSink]:
    func = IRFunction(name="main", params=params, return_type=return_type, body=body)
    mod = IRModule(functions=[func], source_name="test.cpp")
    sink = DiagnosticSink()
    return mod, sink

def test_verifier_accepts_valid_ir():
    body = [
        Instruction("op_0", Opcode.DECLARE, dst=VarRef(1, "x")),
        Instruction("op_1", Opcode.ASSIGN, dst=VarRef(1, "x"), operands=(Const(42),)),
        Instruction("op_2", Opcode.RETURN, operands=(VarRef(1, "x"),)),
    ]
    mod, sink = make_module(body)
    assert verify_module(mod, sink)
    assert not sink.has_errors()

def test_verifier_rejects_duplicate_op_id():
    body = [
        Instruction("op_0", Opcode.DECLARE, dst=VarRef(1, "x")),
        Instruction("op_0", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_temp_used_before_definition():
    body = [
        Instruction("op_0", Opcode.DECLARE, dst=VarRef(1, "x")),
        Instruction("op_1", Opcode.ASSIGN, dst=VarRef(1, "x"), operands=(TempRef("t0"),)),
        Instruction("op_2", Opcode.ADD, dst=TempRef("t0"), operands=(Const(1), Const(2))),
        Instruction("op_3", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_temp_defined_twice():
    body = [
        Instruction("op_0", Opcode.ADD, dst=TempRef("t0"), operands=(Const(1), Const(2))),
        Instruction("op_1", Opcode.MUL, dst=TempRef("t0"), operands=(Const(3), Const(4))),
        Instruction("op_2", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_undeclared_variable():
    body = [
        Instruction("op_0", Opcode.ASSIGN, dst=VarRef(1, "y"), operands=(Const(10),)),
        Instruction("op_1", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_operand_type_mismatch():
    body = [
        Instruction("op_0", Opcode.ADD, dst=TempRef("t0", IRType.I32), operands=(Const(1, IRType.I32), Const(2, IRType.I64))),
        Instruction("op_1", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_bool_outside_branch():
    body = [
        Instruction("op_0", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_1", Opcode.ADD, dst=TempRef("t1", IRType.I32), operands=(TempRef("t0", IRType.BOOL), Const(1))),
        Instruction("op_2", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_jump_to_missing_label():
    body = [
        Instruction("op_0", Opcode.JUMP, label_name="missing_label_r0"),
        Instruction("op_1", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_duplicate_label():
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="loop_head_r0"),
        Instruction("op_1", Opcode.LABEL, label_name="loop_head_r0"),
        Instruction("op_2", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_return_type_mismatch():
    body = [
        Instruction("op_0", Opcode.RETURN, operands=(Const(0, IRType.I64),)),
    ]
    mod, sink = make_module(body, return_type=IRType.I32)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_branch_on_non_bool():
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="if_then_r0"),
        Instruction("op_1", Opcode.LABEL, label_name="if_else_r0"),
        Instruction("op_2", Opcode.LABEL, label_name="if_end_r0"),
        Instruction("op_3", Opcode.BRANCH, operands=(Const(1, IRType.I32), LabelRef("if_then_r0"), LabelRef("if_else_r0"))),
        Instruction("op_4", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_label_region_mismatch():
    body = [
        Instruction("op_0", Opcode.LABEL, label_name="if_then_r0"),
        Instruction("op_1", Opcode.LABEL, label_name="if_else_r1"),
        Instruction("op_2", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_3", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("if_then_r0"), LabelRef("if_else_r1"))),
        Instruction("op_4", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)

def test_verifier_rejects_non_canonical_control_flow_shape():

    body = [
        Instruction("op_0", Opcode.LABEL, label_name="if_then_r0"),
        Instruction("op_1", Opcode.LABEL, label_name="loop_body_r0"),
        Instruction("op_2", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(Const(1), Const(2)), cmp_op="lt"),
        Instruction("op_3", Opcode.BRANCH, operands=(TempRef("t0", IRType.BOOL), LabelRef("if_then_r0"), LabelRef("loop_body_r0"))),
        Instruction("op_4", Opcode.RETURN, operands=(Const(0),)),
    ]
    mod, sink = make_module(body)
    assert not verify_module(mod, sink)
    assert any(e.code == "E5001" for e in sink.errors)
