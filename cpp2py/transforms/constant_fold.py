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

    name: str = "constant_fold"

    def run(self, func: IRFunction, rw: IRRewriter, ctx: PassContext) -> None:
        target = ctx.config.target

        def get_dst_type(instr: Instruction) -> IRType:
            if instr.dst and hasattr(instr.dst, "type"):
                return instr.dst.type
            return IRType.I32

        def get_type_bounds(dst_type: IRType) -> tuple[int, int]:
            if dst_type == IRType.I64:
                return target.long_long_min, target.long_long_max
            return target.int_min, target.int_max

        const_temps: dict[str, tuple[Const, str]] = {}
        temp_defs: dict[str, Instruction] = {}

        for instr in func.body:
            if (
                instr.opcode == Opcode.ASSIGN
                and isinstance(instr.dst, TempRef)
                and len(instr.operands) == 1
                and isinstance(instr.operands[0], Const)
            ):
                const_temps[instr.dst.temp_id] = (instr.operands[0], instr.op_id)

        iteration = 0
        max_iterations = 10
        has_changed = True

        while has_changed and iteration < max_iterations:
            iteration += 1
            start_changed = rw.pass_changed
            iter_changed = False

            idx = 0
            while idx < len(func.body):
                instr = func.body[idx]

                if instr.opcode in (Opcode.LABEL, Opcode.BRANCH, Opcode.JUMP, Opcode.CALL):
                    temp_defs.clear()

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
                            iter_changed = True

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
                            res_type = get_dst_type(instr)
                            t_min, t_max = get_type_bounds(res_type)
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
                                iter_changed = True
                            else:
                                ctx.sink.warning(
                                    "W6004",
                                    f"constant folding skipped: {a} {op_sym} {b} overflows {instr.dst.type if instr.dst else 'i32'}",
                                    instr.span,
                                )

                elif instr.opcode == Opcode.NEG:
                    if len(instr.operands) == 1 and isinstance(instr.operands[0], Const):
                        a = instr.operands[0].value
                        res = -a
                        res_type = get_dst_type(instr)
                        t_min, t_max = get_type_bounds(res_type)
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
                            iter_changed = True
                        else:
                            ctx.sink.warning(
                                "W6004",
                                f"constant folding skipped: negation of {a} overflows",
                                instr.span,
                            )

                elif instr.opcode == Opcode.CAST:
                    if len(instr.operands) == 1 and isinstance(instr.operands[0], Const):
                        val = instr.operands[0].value
                        dst_type = get_dst_type(instr)
                        if dst_type == IRType.I64:
                            res = val
                            reason = f"cast widening is exact; {val} to i64"
                        else:
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
                        iter_changed = True

                # Commutative canonicalization: put constant as second operand for ADD / MUL
                if instr.opcode in (Opcode.ADD, Opcode.MUL) and len(instr.operands) == 2:
                    if isinstance(instr.operands[0], Const) and not isinstance(instr.operands[1], Const):
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=instr.opcode,
                            dst=instr.dst,
                            operands=(instr.operands[1], instr.operands[0]),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason="canonicalize commutative constant to right")
                        instr = new_instr
                        iter_changed = True

                # Algebraic identities
                if instr.opcode == Opcode.ADD and len(instr.operands) == 2:
                    if isinstance(instr.operands[1], Const) and instr.operands[1].value == 0:
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(instr.operands[0],),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason=f"algebraic identity: {instr.operands[0]} + 0")
                        instr = new_instr
                        iter_changed = True
                    elif isinstance(instr.operands[0], Const) and instr.operands[0].value == 0:
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(instr.operands[1],),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason=f"algebraic identity: 0 + {instr.operands[1]}")
                        instr = new_instr
                        iter_changed = True

                elif instr.opcode == Opcode.SUB and len(instr.operands) == 2:
                    if isinstance(instr.operands[1], Const) and instr.operands[1].value == 0:
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(instr.operands[0],),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason=f"algebraic identity: {instr.operands[0]} - 0")
                        instr = new_instr
                        iter_changed = True

                elif instr.opcode == Opcode.MUL and len(instr.operands) == 2:
                    if isinstance(instr.operands[1], Const) and instr.operands[1].value == 1:
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(instr.operands[0],),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason=f"algebraic identity: {instr.operands[0]} * 1")
                        instr = new_instr
                        iter_changed = True
                    elif isinstance(instr.operands[0], Const) and instr.operands[0].value == 1:
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(instr.operands[1],),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason=f"algebraic identity: 1 * {instr.operands[1]}")
                        instr = new_instr
                        iter_changed = True
                    elif (isinstance(instr.operands[1], Const) and instr.operands[1].value == 0) or (isinstance(instr.operands[0], Const) and instr.operands[0].value == 0):
                        res_type = get_dst_type(instr)
                        new_instr = Instruction(
                            op_id=instr.op_id,
                            opcode=Opcode.ASSIGN,
                            dst=instr.dst,
                            operands=(Const(0, res_type),),
                            span=instr.span,
                        )
                        rw.replace(func, instr, new_instr, reason="algebraic identity: multiply by 0")
                        instr = new_instr
                        iter_changed = True

                # Constant Reassociation
                if instr.opcode == Opcode.ADD and len(instr.operands) == 2:
                    op0 = instr.operands[0]
                    op1 = instr.operands[1]
                    if isinstance(op1, Const) and isinstance(op0, TempRef) and op0.temp_id in temp_defs:
                        c2 = op1.value
                        def_instr = temp_defs[op0.temp_id]
                        res_type = get_dst_type(instr)
                        t_min, t_max = get_type_bounds(res_type)

                        if def_instr.opcode == Opcode.ADD and len(def_instr.operands) == 2:
                            c1 = None
                            var = None
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]

                            if c1 is not None and var is not None:
                                c_combined = c1 + c2
                                if t_min <= c_combined <= t_max:
                                    new_instr = Instruction(
                                        op_id=instr.op_id,
                                        opcode=Opcode.ADD,
                                        dst=instr.dst,
                                        operands=(var, Const(c_combined, res_type)),
                                        span=instr.span,
                                    )
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate add: ({var} + {c1}) + {c2} = {var} + {c_combined}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True

                        elif def_instr.opcode == Opcode.SUB and len(def_instr.operands) == 2:
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                                diff = c2 - c1
                                if t_min <= diff <= t_max:
                                    if diff == 0:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.ASSIGN, dst=instr.dst, operands=(var,), span=instr.span)
                                    elif diff > 0:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.ADD, dst=instr.dst, operands=(var, Const(diff, res_type)), span=instr.span)
                                    else:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(var, Const(-diff, res_type)), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate add: ({var} - {c1}) + {c2}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]
                                sum_c = c1 + c2
                                if t_min <= sum_c <= t_max:
                                    new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(Const(sum_c, res_type), var), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate add: ({c1} - {var}) + {c2}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True

                elif instr.opcode == Opcode.SUB and len(instr.operands) == 2:
                    op0 = instr.operands[0]
                    op1 = instr.operands[1]
                    res_type = get_dst_type(instr)
                    t_min, t_max = get_type_bounds(res_type)

                    if isinstance(op1, Const) and isinstance(op0, TempRef) and op0.temp_id in temp_defs:
                        c2 = op1.value
                        def_instr = temp_defs[op0.temp_id]
                        if def_instr.opcode == Opcode.ADD and len(def_instr.operands) == 2:
                            c1 = None
                            var = None
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]
                            if c1 is not None and var is not None:
                                diff = c1 - c2
                                if t_min <= diff <= t_max:
                                    if diff == 0:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.ASSIGN, dst=instr.dst, operands=(var,), span=instr.span)
                                    elif diff > 0:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.ADD, dst=instr.dst, operands=(var, Const(diff, res_type)), span=instr.span)
                                    else:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(var, Const(-diff, res_type)), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate sub: ({var} + {c1}) - {c2}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True
                        elif def_instr.opcode == Opcode.SUB and len(def_instr.operands) == 2:
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                                sum_c = c1 + c2
                                if t_min <= sum_c <= t_max:
                                    new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(var, Const(sum_c, res_type)), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate sub: ({var} - {c1}) - {c2}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]
                                diff = c1 - c2
                                if t_min <= diff <= t_max:
                                    new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(Const(diff, res_type), var), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate sub: ({c1} - {var}) - {c2}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True

                    elif isinstance(op0, Const) and isinstance(op1, TempRef) and op1.temp_id in temp_defs:
                        c2 = op0.value
                        def_instr = temp_defs[op1.temp_id]
                        if def_instr.opcode == Opcode.ADD and len(def_instr.operands) == 2:
                            c1 = None
                            var = None
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]
                            if c1 is not None and var is not None:
                                diff = c2 - c1
                                if t_min <= diff <= t_max:
                                    new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(Const(diff, res_type), var), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate sub: {c2} - ({var} + {c1})",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True
                        elif def_instr.opcode == Opcode.SUB and len(def_instr.operands) == 2:
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                                sum_c = c2 + c1
                                if t_min <= sum_c <= t_max:
                                    new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(Const(sum_c, res_type), var), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate sub: {c2} - ({var} - {c1})",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]
                                diff = c2 - c1
                                if t_min <= diff <= t_max:
                                    if diff == 0:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.ASSIGN, dst=instr.dst, operands=(var,), span=instr.span)
                                    elif diff > 0:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.ADD, dst=instr.dst, operands=(var, Const(diff, res_type)), span=instr.span)
                                    else:
                                        new_instr = Instruction(op_id=instr.op_id, opcode=Opcode.SUB, dst=instr.dst, operands=(var, Const(-diff, res_type)), span=instr.span)
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate sub: {c2} - ({c1} - {var})",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True

                elif instr.opcode == Opcode.MUL and len(instr.operands) == 2:
                    op0 = instr.operands[0]
                    op1 = instr.operands[1]
                    if isinstance(op1, Const) and isinstance(op0, TempRef) and op0.temp_id in temp_defs:
                        c2 = op1.value
                        def_instr = temp_defs[op0.temp_id]
                        if def_instr.opcode == Opcode.MUL and len(def_instr.operands) == 2:
                            c1 = None
                            var = None
                            if isinstance(def_instr.operands[1], Const):
                                c1 = def_instr.operands[1].value
                                var = def_instr.operands[0]
                            elif isinstance(def_instr.operands[0], Const):
                                c1 = def_instr.operands[0].value
                                var = def_instr.operands[1]
                            if c1 is not None and var is not None:
                                c_combined = c1 * c2
                                res_type = get_dst_type(instr)
                                t_min, t_max = get_type_bounds(res_type)
                                if t_min <= c_combined <= t_max:
                                    new_instr = Instruction(
                                        op_id=instr.op_id,
                                        opcode=Opcode.MUL,
                                        dst=instr.dst,
                                        operands=(var, Const(c_combined, res_type)),
                                        span=instr.span,
                                    )
                                    rw.replace(
                                        func,
                                        instr,
                                        new_instr,
                                        reason=f"reassociate mul: ({var} * {c1}) * {c2} = {var} * {c_combined}",
                                        derived_from=[def_instr.op_id, instr.op_id],
                                    )
                                    instr = new_instr
                                    iter_changed = True

                if (
                    instr.opcode == Opcode.ASSIGN
                    and isinstance(instr.dst, TempRef)
                    and len(instr.operands) == 1
                    and isinstance(instr.operands[0], Const)
                ):
                    const_temps[instr.dst.temp_id] = (instr.operands[0], instr.op_id)

                if instr.dst is not None and isinstance(instr.dst, TempRef):
                    temp_defs[instr.dst.temp_id] = instr

                if instr.dst is not None and isinstance(instr.dst, VarRef):
                    v_sym = instr.dst.symbol_id
                    temp_defs = {
                        tid: t_ins for tid, t_ins in temp_defs.items()
                        if not any(isinstance(o, VarRef) and o.symbol_id == v_sym for o in t_ins.operands)
                    }

                idx += 1

            has_changed = iter_changed or (rw.pass_changed != start_changed)
