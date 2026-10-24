"""Constant folding pass for cpp2py IR.

Conforms to ARCH §D.4, §E.2, and §F.4.
- Folds binop/unop on constants using TargetModel integer semantics.
- Division truncates towards zero; remainder has sign of dividend.
- Never folds division or remainder by zero (emits W6004).
- Never folds if result exceeds TargetModel range (emits W6004).
- Substitutes constant temps into users (single-assignment temps only).
- Never touches cmp, branch, or control flow.
- No variable constant propagation, no algebraic simplification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cpp2py.ir.model import (
    IRFunction,
    Instruction,
    Opcode,
    Const,
    TempRef,
    VarRef,
    IRType,
)

if TYPE_CHECKING:
    from cpp2py.transforms.manager import IRRewriter, PassContext


class ConstantFoldPass:
    """Pass that folds constant arithmetic expressions and propagates constant temps."""

    name: str = "constant_fold"

    def run(self, func: IRFunction, rw: IRRewriter, ctx: PassContext) -> None:
        target = ctx.config.target
        int_min = target.int_min
        int_max = target.int_max

        # Map temp_id -> (Const, defining_op_id)
        const_temps: dict[str, tuple[Const, str]] = {}

        # Pre-seed with existing constant assignments to temps if any
        for instr in func.body:
            if (
                instr.opcode == Opcode.ASSIGN
                and isinstance(instr.dst, TempRef)
                and len(instr.operands) == 1
                and isinstance(instr.operands[0], Const)
            ):
                const_temps[instr.dst.temp_id] = (instr.operands[0], instr.op_id)

        # Traverse instructions
        # Note: func.body may be modified via rw, so iterate over a snapshot of indices or while loop
        idx = 0
        while idx < len(func.body):
            instr = func.body[idx]

            # 1. Substitute constant temps into users
            # Strictly NEVER touch cmp, branch, label, or jump
            if instr.opcode not in (Opcode.CMP, Opcode.BRANCH, Opcode.LABEL, Opcode.JUMP):
                for op in list(instr.operands):
                    if isinstance(op, TempRef) and op.temp_id in const_temps:
                        c_val, def_op_id = const_temps[op.temp_id]
                        rw.substitute_operand(
                            func,
                            instr,
                            old_op=op,
                            new_op=c_val,
                            reason=f"substitute constant temp {op.temp_id}",
                            derived_from=[def_op_id],
                        )

            # 2. Check for constant folding on binops
            if instr.opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD):
                if (
                    len(instr.operands) == 2
                    and isinstance(instr.operands[0], Const)
                    and isinstance(instr.operands[1], Const)
                ):
                    a = instr.operands[0].value
                    b = instr.operands[1].value
                    res: int | None = None
                    op_sym = ""

                    if instr.opcode == Opcode.DIV:
                        op_sym = "/"
                        if b == 0:
                            ctx.sink.warning("W6004", "constant folding skipped: division by zero", instr.span)
                        else:
                            res = -(abs(a) // abs(b)) if (a < 0) ^ (b < 0) else (abs(a) // abs(b))
                    elif instr.opcode == Opcode.MOD:
                        op_sym = "%"
                        if b == 0:
                            ctx.sink.warning("W6004", "constant folding skipped: remainder by zero", instr.span)
                        else:
                            rem = abs(a) % abs(b)
                            res = -rem if a < 0 else rem
                    elif instr.opcode == Opcode.ADD:
                        op_sym = "+"
                        res = a + b
                    elif instr.opcode == Opcode.SUB:
                        op_sym = "-"
                        res = a - b
                    elif instr.opcode == Opcode.MUL:
                        op_sym = "*"
                        res = a * b

                    if res is not None:
                        # Check TargetModel type range
                        res_type = instr.dst.type if (instr.dst and hasattr(instr.dst, "type")) else IRType.I32
                        t_min = target.long_long_min if res_type == IRType.I64 else target.int_min
                        t_max = target.long_long_max if res_type == IRType.I64 else target.int_max
                        if t_min <= res <= t_max:
                            type_name = str(res_type)
                            reason = f"both operands constant; {a}{op_sym}{b}={res} within {type_name}"
                            new_instr = Instruction(
                                op_id=instr.op_id,
                                opcode=Opcode.ASSIGN,
                                dst=instr.dst,
                                operands=(Const(res, res_type),),
                                span=instr.span,
                            )
                            rw.replace(func, instr, new_instr, reason=reason)
                            instr = new_instr
                        else:
                            ctx.sink.warning(
                                "W6004",
                                f"constant folding skipped: {a} {op_sym} {b} overflows {instr.dst.type if instr.dst else 'i32'}",
                                instr.span,
                            )

            # 3. Check for constant folding on unops (NEG)
            elif instr.opcode == Opcode.NEG:
                if len(instr.operands) == 1 and isinstance(instr.operands[0], Const):
                    a = instr.operands[0].value
                    res = -a
                    res_type = instr.dst.type if (instr.dst and hasattr(instr.dst, "type")) else IRType.I32
                    t_min = target.long_long_min if res_type == IRType.I64 else target.int_min
                    t_max = target.long_long_max if res_type == IRType.I64 else target.int_max
                    if t_min <= res <= t_max:
                        type_name = str(res_type)
                        reason = f"operand constant; -({a})={res} within {type_name}"
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(Const(res, res_type),),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason=reason)
                        instr = new_instr
                    else:
                        ctx.sink.warning(
                            "W6004",
                            f"constant folding skipped: negation of {a} overflows",
                            instr.span,
                        )

            # 3b. Check for constant folding on casts
            elif instr.opcode == Opcode.CAST:
                if len(instr.operands) == 1 and isinstance(instr.operands[0], Const):
                    val = instr.operands[0].value
                    dst_type = instr.dst.type if (instr.dst and hasattr(instr.dst, "type")) else IRType.I32
                    if dst_type == IRType.I64:
                        res = val
                        reason = f"cast widening is exact; {val} to i64"
                    else:
                        # Modular narrowing per TargetModel
                        int_bits = target.int_bits
                        res = ((val + (1 << (int_bits - 1))) % (1 << int_bits)) - (1 << (int_bits - 1))
                        reason = f"cast narrowing modular; {val} to i32 = {res}"
                    new_instr = Instruction(
                        op_id=instr.op_id,
                        opcode=Opcode.ASSIGN,
                        dst=instr.dst,
                        operands=(Const(res, dst_type),),
                        span=instr.span,
                    )
                    rw.replace(func, instr, new_instr, reason=reason)
                    instr = new_instr

            # 4. Record new constant temp assignment
            if (
                instr.opcode == Opcode.ASSIGN
                and isinstance(instr.dst, TempRef)
                and len(instr.operands) == 1
                and isinstance(instr.operands[0], Const)
            ):
                const_temps[instr.dst.temp_id] = (instr.operands[0], instr.op_id)

            idx += 1
