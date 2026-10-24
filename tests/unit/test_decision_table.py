"""Exhaustive tests for ARCH §E.5 decision table rows."""

import pytest
from cpp2py.analysis.intervals import Interval
from cpp2py.analysis.risk import Risk
from cpp2py.compat.policy import decide_compat, build_plan
from cpp2py.compat.plan import CompatAction
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.ir.model import Instruction, Opcode, VarRef, TempRef, IRType


def make_instr(op_id: str, opcode: Opcode, dst_type: IRType = IRType.I32) -> Instruction:
    dst = TempRef("t0", dst_type)
    return Instruction(
        op_id=op_id,
        opcode=opcode,
        dst=dst,
        operands=[VarRef("a", dst_type), VarRef("b", dst_type)],
    )


# --- Addition under all 3 policies ---
def test_add_i32_no_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.ADD)
    dec = decide_compat(ins, Interval(0, 100), Interval(0, 100), cfg)
    assert dec.action == CompatAction.NATIVE
    assert Risk.SIGNED_OVERFLOW_POSSIBLE not in dec.risks


def test_add_i32_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.ADD)
    dec = decide_compat(ins, Interval(2000000000, 2000000000), Interval(2000000000, 2000000000), cfg)
    assert dec.action == CompatAction.NATIVE
    assert Risk.SIGNED_OVERFLOW_POSSIBLE in dec.risks
    assert dec.warning == "W6002"


def test_add_i32_overflow_wrap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.ADD)
    dec = decide_compat(ins, Interval(2000000000, 2000000000), Interval(2000000000, 2000000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_wrap_i32"


def test_add_i32_overflow_trap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.ADD)
    dec = decide_compat(ins, Interval(2000000000, 2000000000), Interval(2000000000, 2000000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_check_i32"


# --- Subtraction under all 3 policies ---
def test_sub_i32_no_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.SUB)
    dec = decide_compat(ins, Interval(10, 20), Interval(1, 5), cfg)
    assert dec.action == CompatAction.NATIVE
    assert Risk.SIGNED_OVERFLOW_POSSIBLE not in dec.risks


def test_sub_i32_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.SUB)
    dec = decide_compat(ins, Interval(-2000000000, -2000000000), Interval(2000000000, 2000000000), cfg)
    assert dec.action == CompatAction.NATIVE
    assert Risk.SIGNED_OVERFLOW_POSSIBLE in dec.risks
    assert dec.warning == "W6002"


def test_sub_i32_overflow_wrap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.SUB)
    dec = decide_compat(ins, Interval(-2000000000, -2000000000), Interval(2000000000, 2000000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_wrap_i32"


def test_sub_i32_overflow_trap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.SUB)
    dec = decide_compat(ins, Interval(-2000000000, -2000000000), Interval(2000000000, 2000000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_check_i32"


# --- Multiplication under all 3 policies ---
def test_mul_i32_no_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.MUL)
    dec = decide_compat(ins, Interval(2, 5), Interval(3, 4), cfg)
    assert dec.action == CompatAction.NATIVE


def test_mul_i32_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.MUL)
    dec = decide_compat(ins, Interval(1000000, 1000000), Interval(1000000, 1000000), cfg)
    assert dec.action == CompatAction.NATIVE
    assert Risk.SIGNED_OVERFLOW_POSSIBLE in dec.risks
    assert dec.warning == "W6002"


def test_mul_i32_overflow_wrap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.MUL)
    dec = decide_compat(ins, Interval(1000000, 1000000), Interval(1000000, 1000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_wrap_i32"


def test_mul_i32_overflow_trap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.MUL)
    dec = decide_compat(ins, Interval(1000000, 1000000), Interval(1000000, 1000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_check_i32"


# --- Negation under all 3 policies ---
def test_neg_i32_no_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = Instruction("op_1", Opcode.NEG, TempRef("t0", IRType.I32), [VarRef("a", IRType.I32)])
    dec = decide_compat(ins, Interval(-10, 10), None, cfg)
    assert dec.action == CompatAction.NATIVE


def test_neg_i32_overflow_assume():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = Instruction("op_1", Opcode.NEG, TempRef("t0", IRType.I32), [VarRef("a", IRType.I32)])
    dec = decide_compat(ins, Interval(-2147483648, -2147483648), None, cfg)
    assert dec.action == CompatAction.NATIVE
    assert Risk.SIGNED_OVERFLOW_POSSIBLE in dec.risks
    assert dec.warning == "W6002"


def test_neg_i32_overflow_wrap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = Instruction("op_1", Opcode.NEG, TempRef("t0", IRType.I32), [VarRef("a", IRType.I32)])
    dec = decide_compat(ins, Interval(-2147483648, -2147483648), None, cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_wrap_i32"


def test_neg_i32_overflow_trap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = Instruction("op_1", Opcode.NEG, TempRef("t0", IRType.I32), [VarRef("a", IRType.I32)])
    dec = decide_compat(ins, Interval(-2147483648, -2147483648), None, cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_check_i32"


# --- 64-bit (long long) overflow operations ---
def test_add_i64_overflow_wrap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.ADD, IRType.I64)
    dec = decide_compat(ins, Interval(5000000000000000000, 5000000000000000000), Interval(5000000000000000000, 5000000000000000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_wrap_i64"


def test_add_i64_overflow_trap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.ADD, IRType.I64)
    dec = decide_compat(ins, Interval(5000000000000000000, 5000000000000000000), Interval(5000000000000000000, 5000000000000000000), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_check_i64"


# --- Division and Modulo cases ---
def test_div_positive_operands():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(0, 100), Interval(1, 10), cfg)
    assert dec.action == CompatAction.NATIVE
    assert not dec.risks


def test_div_negative_dividend():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(-10, 10), Interval(1, 10), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_cpp_div"
    assert Risk.DIV_TRUNC_DIFFERS in dec.risks


def test_div_negative_divisor():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(0, 10), Interval(-5, -1), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_cpp_div"
    assert Risk.DIV_TRUNC_DIFFERS in dec.risks


def test_mod_positive_operands():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.MOD)
    dec = decide_compat(ins, Interval(0, 100), Interval(1, 10), cfg)
    assert dec.action == CompatAction.NATIVE
    assert not dec.risks


def test_mod_negative_dividend():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.MOD)
    dec = decide_compat(ins, Interval(-10, 10), Interval(1, 10), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_cpp_mod"
    assert Risk.MOD_SIGN_DIFFERS in dec.risks


def test_mod_negative_divisor():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.MOD)
    dec = decide_compat(ins, Interval(0, 10), Interval(-5, -1), cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_cpp_mod"
    assert Risk.MOD_SIGN_DIFFERS in dec.risks


def test_div_definite_zero():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(10, 20), Interval(0, 0), cfg)
    assert Risk.DIV_BY_ZERO_CERTAIN in dec.risks
    assert dec.action == CompatAction.HELPER


def test_div_possible_zero():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(10, 20), Interval(-2, 2), cfg)
    assert Risk.DIV_BY_ZERO_POSSIBLE in dec.risks
    assert dec.warning == "W6003"
    assert dec.action == CompatAction.HELPER


def test_int_min_div_minus_one_wrap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(-2147483648, -2147483648), Interval(-1, -1), cfg)
    assert Risk.INT_MIN_DIV_MINUS_ONE in dec.risks
    assert dec.action == CompatAction.HELPER
    assert dec.wrap_int_min_div is True


def test_int_min_div_minus_one_trap():
    cfg = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        compat_mode=CompatMode.RANGE_GUIDED,
    )
    ins = make_instr("op_1", Opcode.DIV)
    dec = decide_compat(ins, Interval(-2147483648, -2147483648), Interval(-1, -1), cfg)
    assert Risk.INT_MIN_DIV_MINUS_ONE in dec.risks
    assert dec.action == CompatAction.HELPER


def test_cast_exact_fits():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = Instruction("op_1", Opcode.CAST, TempRef("t0", IRType.I32), [VarRef("a", IRType.I64)])
    dec = decide_compat(ins, Interval(0, 1000), None, cfg)
    assert dec.action == CompatAction.NATIVE
    assert not dec.risks


def test_cast_lossy_narrowing():
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    ins = Instruction("op_1", Opcode.CAST, TempRef("t0", IRType.I32), [VarRef("a", IRType.I64)])
    dec = decide_compat(ins, Interval(0, 10000000000), None, cfg)
    assert dec.action == CompatAction.HELPER
    assert dec.helper == "_wrap_i32"
    assert Risk.NARROWING_LOSSY in dec.risks
    assert dec.warning == "W6006"
