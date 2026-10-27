from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import cpp2py.codegen.python_gen as pygen_mod
import cpp2py.compat.policy as policy_mod
import cpp2py.ir.builder as builder_mod
import cpp2py.transforms.constant_fold as fold_mod
from cpp2py.analysis.intervals import Interval
from cpp2py.analysis.risk import Risk
from cpp2py.compat.plan import CompatAction, CompatDecision
from cpp2py.frontend import ast_nodes as ast
from cpp2py.ir.model import Const, Instruction, IRType, Opcode, TempRef

@contextmanager
def patch_fault_f1_floor_div() -> Iterator[None]:
    orig_run = fold_mod.ConstantFoldPass.run

    def patched_run(self: Any, func: Any, rw: Any, ctx: Any) -> None:
        orig_replace = rw.replace

        def faulty_replace(f: Any, old: Any, new: Any, reason: str = "", derived_from: Any = ()) -> None:
            if derived_from is None:
                derived_from = ()
            if old.opcode == Opcode.DIV and len(old.operands) == 2:
                if isinstance(old.operands[0], Const) and isinstance(old.operands[1], Const):
                    a_val = old.operands[0].value
                    b_val = old.operands[1].value
                    if b_val != 0:
                        faulty_res = a_val // b_val
                        res_type = new.operands[0].type if new.operands else IRType.I32
                        new.operands = (Const(faulty_res, res_type),)
                        reason = f"fault F1: {a_val}//{b_val}={faulty_res}"
            orig_replace(f, old, new, reason, derived_from)

        rw.replace = faulty_replace
        orig_run(self, func, rw, ctx)

    fold_mod.ConstantFoldPass.run = patched_run
    try:
        yield
    finally:
        fold_mod.ConstantFoldPass.run = orig_run

@contextmanager
def patch_fault_f2_mod_plan_native() -> Iterator[None]:
    orig_decide = policy_mod.decide

    def faulty_decide(
        instr: Any,
        risks: Any,
        config: Any,
        operand_ranges: Any = (),
        result_range: Any = None,
        sink: Any = None,
    ) -> CompatDecision:
        dec = orig_decide(instr, risks, config, operand_ranges, result_range, sink)
        if instr.opcode == Opcode.MOD:

            risks_set = set(dec.risks)
            risks_set.add(Risk.MOD_SIGN_DIFFERS)
            return CompatDecision(
                op_id=dec.op_id,
                risks=risks_set,
                action=CompatAction.NATIVE,
                helper=None,
                reason="fault F2: mod range transfer ignored dividend sign, picked native",
                operand_ranges=dec.operand_ranges,
                result_range=dec.result_range,
                policy=dec.policy,
                wrap_int_min_div=dec.wrap_int_min_div,
                warning=dec.warning,
            )
        return dec

    policy_mod.decide = faulty_decide
    try:
        yield
    finally:
        policy_mod.decide = orig_decide

@contextmanager
def patch_fault_f3_generator_mod() -> Iterator[None]:
    orig_build = pygen_mod.IRToPythonGenerator._build_ast_for_instr

    def faulty_build(self: Any, instr: Any) -> Any:
        if instr.opcode == Opcode.MOD:

            dummy_span = instr.span
            left = self._build_ast_expr(instr.operands[0])
            right = self._build_ast_expr(instr.operands[1])
            return ast.BinaryExpr("%", left, right, dummy_span)
        return orig_build(self, instr)

    pygen_mod.IRToPythonGenerator._build_ast_for_instr = faulty_build
    try:
        yield
    finally:
        pygen_mod.IRToPythonGenerator._build_ast_for_instr = orig_build

@contextmanager
def patch_fault_f4_builder_swap_sub() -> Iterator[None]:
    orig_lower_expr = builder_mod.IRBuilder._lower_expr

    def faulty_lower_expr(self: Any, expr: Any) -> Any:
        if isinstance(expr, ast.BinaryExpr) and expr.op == "-":
            left_val = self._lower_expr(expr.left)
            right_val = self._lower_expr(expr.right)
            left_type = getattr(left_val, "type", IRType.I32)
            right_type = getattr(right_val, "type", IRType.I32)
            common_type = IRType.I64 if (left_type == IRType.I64 or right_type == IRType.I64) else IRType.I32
            left_val = self._emit_cast_if_needed(left_val, common_type, expr.left.span)
            right_val = self._emit_cast_if_needed(right_val, common_type, expr.right.span)

            temp = TempRef(self._allocator.next_temp_id(), common_type)

            self._instructions.append(
                Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.SUB,
                    dst=temp,
                    operands=(right_val, left_val),
                    span=expr.span,
                )
            )
            return temp
        return orig_lower_expr(self, expr)

    builder_mod.IRBuilder._lower_expr = faulty_lower_expr
    try:
        yield
    finally:
        builder_mod.IRBuilder._lower_expr = orig_lower_expr

@contextmanager
def patch_fault_f5_fold_mul_as_add() -> Iterator[None]:
    orig_run = fold_mod.ConstantFoldPass.run

    def patched_run(self: Any, func: Any, rw: Any, ctx: Any) -> None:
        target = ctx.config.target
        for instr in list(func.body):
            if instr.opcode == Opcode.MUL:
                if len(instr.operands) == 2 and isinstance(instr.operands[0], Const) and isinstance(instr.operands[1], Const):
                    a = instr.operands[0].value
                    b = instr.operands[1].value

                    res = a + b
                    res_type = instr.dst.type if (instr.dst and hasattr(instr.dst, "type")) else IRType.I32
                    new_instr = Instruction(
                        op_id=instr.op_id,
                        opcode=Opcode.ASSIGN,
                        dst=instr.dst,
                        operands=(Const(res, res_type),),
                        span=instr.span,
                    )
                    rw.replace(func, instr, new_instr, reason=f"fault F5: {a}+{b}={res}")
        orig_run(self, func, rw, ctx)

    fold_mod.ConstantFoldPass.run = patched_run
    try:
        yield
    finally:
        fold_mod.ConstantFoldPass.run = orig_run
