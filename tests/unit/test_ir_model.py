"""Unit tests for cpp2py/ir/model.py."""

import pytest
from cpp2py.source import SourceSpan, Pos
from cpp2py.ir.model import (
    IdAllocator,
    IRType,
    Const,
    VarRef,
    TempRef,
    StrConst,
    LabelRef,
    Opcode,
    Instruction,
    IRFunction,
    IRModule,
    RegionInfo,
)


def test_id_allocator_monotonic_and_unique_ops():
    alloc = IdAllocator()
    ids = [alloc.next_op_id() for _ in range(5)]
    assert ids == ["op_0", "op_1", "op_2", "op_3", "op_4"]
    assert len(set(ids)) == 5


def test_id_allocator_monotonic_and_unique_temps():
    alloc = IdAllocator()
    ids = [alloc.next_temp_id() for _ in range(5)]
    assert ids == ["t0", "t1", "t2", "t3", "t4"]
    assert len(set(ids)) == 5


def test_id_allocator_monotonic_and_unique_regions():
    alloc = IdAllocator()
    ids = [alloc.next_region_id() for _ in range(3)]
    assert ids == ["r0", "r1", "r2"]
    assert len(set(ids)) == 3


def test_const_operand():
    c1 = Const(42, IRType.I32)
    c2 = Const(42, IRType.I32)
    c3 = Const(42, IRType.I64)
    assert c1 == c2
    assert c1 != c3
    assert str(c1) == "42"


def test_var_ref_operand():
    v1 = VarRef(1, "x", IRType.I32)
    v2 = VarRef(1, "x", IRType.I32)
    v3 = VarRef(2, "x", IRType.I32)
    assert v1 == v2
    assert v1 != v3
    assert str(v1) == "x"


def test_temp_ref_operand():
    t1 = TempRef("t0", IRType.I32)
    t2 = TempRef("t0", IRType.I32)
    assert t1 == t2
    assert str(t1) == "t0"


def test_str_const_and_label_ref():
    s = StrConst("hello\nworld")
    assert str(s) == r'"hello\nworld"'
    lbl = LabelRef("loop_head_r0")
    assert str(lbl) == "loop_head_r0"


def test_all_arch_opcodes_present():
    expected_opcodes = {
        "declare", "assign", "add", "sub", "mul", "div", "mod", "neg",
        "read", "print", "label", "jump", "branch", "cmp", "call", "return", "cast"
    }
    actual = {op.value for op in Opcode}
    assert actual == expected_opcodes


def test_instruction_creation_and_defaults():
    span = SourceSpan(file="test.cpp", start=Pos(1, 1, 0), end=Pos(1, 5, 4))
    instr = Instruction(
        op_id="op_0",
        opcode=Opcode.DECLARE,
        dst=VarRef(1, "a", IRType.I32),
        operands=(VarRef(1, "a", IRType.I32),),
        span=span,
    )
    assert instr.op_id == "op_0"
    assert instr.opcode == Opcode.DECLARE
    assert instr.origin == ()
    assert instr.newline is False
