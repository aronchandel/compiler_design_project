from __future__ import annotations

from typing import TYPE_CHECKING

from cpp2py.ir.model import (
    IRFunction,
    Opcode,
    TempRef,
)

if TYPE_CHECKING:
    from cpp2py.transforms.manager import IRRewriter, PassContext

class DeadTempsPass:

    name: str = "dead_temps"

    def run(self, func: IRFunction, rw: IRRewriter, ctx: PassContext) -> None:

        use_counts: dict[str, int] = {}
        for instr in func.body:
            for op in instr.operands:
                if isinstance(op, TempRef):
                    use_counts[op.temp_id] = use_counts.get(op.temp_id, 0) + 1

        allowed_opcodes = {
            Opcode.ASSIGN,
            Opcode.ADD,
            Opcode.SUB,
            Opcode.MUL,
            Opcode.NEG,
            Opcode.CMP,
        }

        for instr in list(func.body):

            if instr.dst is not None and isinstance(instr.dst, TempRef):
                t_id = instr.dst.temp_id

                if use_counts.get(t_id, 0) == 0 and instr.opcode in allowed_opcodes:
                    rw.delete(func, instr, reason=f"{t_id} has no remaining uses")
