import pytest

from cpp2py.config import TargetModel
from cpp2py.ir.model import Opcode, IRType, Instruction, TempRef
from cpp2py.analysis.intervals import Interval
from cpp2py.analysis.risk import Risk, classify_risks

def test_div_native_safe_no_risks():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.DIV, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(0, 100), Interval(1, 10)), Interval(0, 100), target)
    assert len(risks) == 0

def test_div_negative_dividend_risk():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.DIV, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(-10, 100), Interval(1, 10)), Interval(-10, 100), target)
    assert Risk.DIV_TRUNC_DIFFERS in risks
    assert Risk.DIV_BY_ZERO_POSSIBLE not in risks

def test_div_negative_divisor_risk():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.DIV, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(10, 100), Interval(-5, -1)), Interval(-100, -2), target)
    assert Risk.DIV_TRUNC_DIFFERS in risks

def test_mod_sign_differs_risk():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.MOD, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(-10, 10), Interval(1, 10)), Interval(-9, 9), target)
    assert Risk.MOD_SIGN_DIFFERS in risks

def test_div_by_zero_possible():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.DIV, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(1, 10), Interval(-2, 2)), Interval(-10, 10), target)
    assert Risk.DIV_BY_ZERO_POSSIBLE in risks
    assert Risk.DIV_BY_ZERO_CERTAIN not in risks

def test_div_by_zero_certain():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.DIV, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(1, 10), Interval(0, 0)), Interval(None, None), target)
    assert Risk.DIV_BY_ZERO_CERTAIN in risks

def test_int_min_div_minus_one_risk():
    target = TargetModel()
    int_min = target.int_min
    instr = Instruction("op_0", Opcode.DIV, dst=TempRef("t0", IRType.I32))
    risks = classify_risks(instr, (Interval(int_min, 0), Interval(-1, 10)), Interval(0, -int_min), target)
    assert Risk.INT_MIN_DIV_MINUS_ONE in risks

def test_signed_overflow_possible_add():
    target = TargetModel()
    int_max = target.int_max
    instr = Instruction("op_0", Opcode.ADD, dst=TempRef("t0", IRType.I32))

    risks = classify_risks(instr, (Interval(int_max, int_max), Interval(1, 1)), Interval(int_max + 1, int_max + 1), target)
    assert Risk.SIGNED_OVERFLOW_POSSIBLE in risks

def test_narrowing_lossy_risk():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.CAST, dst=TempRef("t0", IRType.I32))

    risks = classify_risks(instr, (Interval(0, 1 << 32),), Interval(target.int_min, target.int_max), target)
    assert Risk.NARROWING_LOSSY in risks

def test_narrowing_safe_no_risk():
    target = TargetModel()
    instr = Instruction("op_0", Opcode.CAST, dst=TempRef("t0", IRType.I32))

    risks = classify_risks(instr, (Interval(42, 42),), Interval(42, 42), target)
    assert Risk.NARROWING_LOSSY not in risks
