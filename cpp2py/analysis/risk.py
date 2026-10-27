from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from cpp2py.analysis.intervals import Interval
from cpp2py.ir.model import Opcode, IRType, Instruction

if TYPE_CHECKING:
    from cpp2py.config import TargetModel

class Risk(Enum):
    DIV_TRUNC_DIFFERS = "DIV_TRUNC_DIFFERS"
    MOD_SIGN_DIFFERS = "MOD_SIGN_DIFFERS"
    DIV_BY_ZERO_POSSIBLE = "DIV_BY_ZERO_POSSIBLE"
    DIV_BY_ZERO_CERTAIN = "DIV_BY_ZERO_CERTAIN"
    INT_MIN_DIV_MINUS_ONE = "INT_MIN_DIV_MINUS_ONE"
    SIGNED_OVERFLOW_POSSIBLE = "SIGNED_OVERFLOW_POSSIBLE"
    NARROWING_LOSSY = "NARROWING_LOSSY"

    def __str__(self) -> str:
        return self.value

def classify_risks(
    instr: Instruction,
    operand_ranges: tuple[Interval, ...],
    exact_result_range: Interval,
    target: TargetModel,
) -> set[Risk]:
    risks: set[Risk] = set()
    opcode = instr.opcode

    if opcode in (Opcode.DIV, Opcode.MOD):
        if len(operand_ranges) >= 2:
            a, b = operand_ranges[0], operand_ranges[1]

            if b.contains(0):
                if b.lo == 0 and b.hi == 0:
                    risks.add(Risk.DIV_BY_ZERO_CERTAIN)
                else:
                    risks.add(Risk.DIV_BY_ZERO_POSSIBLE)

            is_native_safe = (a.lo is not None and a.lo >= 0 and b.lo is not None and b.lo >= 1)
            if not is_native_safe:

                if not (b.lo == 0 and b.hi == 0):
                    if opcode == Opcode.DIV:
                        risks.add(Risk.DIV_TRUNC_DIFFERS)
                    else:
                        risks.add(Risk.MOD_SIGN_DIFFERS)

            bits = target.long_long_bits if (instr.dst and instr.dst.type == IRType.I64) else target.int_bits
            t_min = -(1 << (bits - 1))
            if a.lo is not None and a.lo <= t_min and b.contains(-1):
                risks.add(Risk.INT_MIN_DIV_MINUS_ONE)

    elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.NEG):
        bits = target.long_long_bits if (instr.dst and instr.dst.type == IRType.I64) else target.int_bits
        t_min = -(1 << (bits - 1))
        t_max = (1 << (bits - 1)) - 1
        t_range = Interval(t_min, t_max)
        if not t_range.contains_interval(exact_result_range):
            risks.add(Risk.SIGNED_OVERFLOW_POSSIBLE)

    elif opcode == Opcode.CAST:
        if len(operand_ranges) >= 1:
            src_range = operand_ranges[0]
            dst_type = instr.dst.type if instr.dst else IRType.I32

            if dst_type == IRType.I32:
                int_range = Interval(target.int_min, target.int_max)
                if not int_range.contains_interval(src_range):
                    risks.add(Risk.NARROWING_LOSSY)

    return risks

classify = classify_risks
