"""IR verification pass checking invariants defined in ARCH §D.3.8.

Invariants:
1. Unique op IDs.
2. Every TempRef is defined once and before use.
3. Every VarRef is declared (or a parameter) before use.
4. Operand and result types agree; bool outside branch rejected; branch on non-bool rejected.
5. Jump/branch target labels exist exactly once in the same function.
6. Canonical control-flow shapes (§D.3.6), label role & region consistency, no label region mismatch.
7. Return operand type matches function return type.

All invariant violations report diagnostic code E5001.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    VarRef,
    TempRef,
    StrConst,
    LabelRef,
    IRType,
)
from cpp2py.diagnostics import DiagnosticSink

LABEL_PATTERN = re.compile(r"^(if_then|if_else|if_end|loop_head|loop_body|loop_end)_(r\d+)$")


def verify_module(module: IRModule, sink: DiagnosticSink) -> bool:
    """Verify all functions in the module. Returns True if valid, False if errors found."""
    initial_errors = sink.error_count()
    verifier = IRVerifier(sink)

    # Check module-wide op_id uniqueness
    seen_module_op_ids: set[str] = set()
    for func in module.functions:
        for instr in func.body:
            if instr.op_id in seen_module_op_ids:
                sink.error("E5001", f"duplicate op_id across module: '{instr.op_id}'", instr.span)
            seen_module_op_ids.add(instr.op_id)

    for func in module.functions:
        verifier.verify_function(func)

    return sink.error_count() == initial_errors


class IRVerifier:
    """Verifies a single IRFunction against ARCH §D.3.8 invariants."""

    def __init__(self, sink: DiagnosticSink) -> None:
        self._sink = sink

    def verify_function(self, func: IRFunction) -> None:
        seen_op_ids: set[str] = set()
        defined_temps: set[str] = set()
        declared_vars: set[str] = {p.ir_name for p in func.params}
        var_types: dict[str, IRType] = {p.ir_name: p.type for p in func.params}
        temp_types: dict[str, IRType] = {}

        # First pass: collect labels and check duplicate labels
        label_instrs: dict[str, Instruction] = {}
        for instr in func.body:
            if instr.opcode == Opcode.LABEL:
                label_name = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                if label_name in label_instrs:
                    self._sink.error("E5001", f"duplicate label definition: '{label_name}'", instr.span)
                else:
                    label_instrs[label_name] = instr

        # Second pass: check each instruction
        for instr in func.body:
            # 1. Op ID uniqueness within function
            if instr.op_id in seen_op_ids:
                self._sink.error("E5001", f"duplicate op_id in function: '{instr.op_id}'", instr.span)
            seen_op_ids.add(instr.op_id)

            opcode = instr.opcode

            # 2. Check destination and operands: variables must be declared, temps must be defined before use
            if opcode != Opcode.DECLARE and isinstance(instr.dst, VarRef):
                if instr.dst.ir_name not in declared_vars:
                    self._sink.error("E5001", f"use of undeclared variable: '{instr.dst.ir_name}'", instr.span)

            for op in instr.operands:
                if isinstance(op, VarRef):
                    # In DECLARE opcode, the operand is the variable being declared
                    if opcode != Opcode.DECLARE and op.ir_name not in declared_vars:
                        self._sink.error("E5001", f"use of undeclared variable: '{op.ir_name}'", instr.span)
                elif isinstance(op, TempRef):
                    if op.temp_id not in defined_temps:
                        self._sink.error("E5001", f"use of undefined temporary: '{op.temp_id}'", instr.span)

            # 3. Type agreement and opcode semantics
            if opcode == Opcode.DECLARE:
                var = instr.dst or (instr.operands[0] if instr.operands else None)
                if isinstance(var, VarRef):
                    declared_vars.add(var.ir_name)
                    var_types[var.ir_name] = var.type

            elif opcode == Opcode.ASSIGN:
                src = instr.operands[0] if instr.operands else None
                dst = instr.dst
                src_type = self._get_type(src, temp_types, var_types)
                dst_type = self._get_type(dst, temp_types, var_types)

                if src_type == IRType.BOOL:
                    self._sink.error("E5001", "bool value used outside of branch condition", instr.span)
                if src_type != dst_type:
                    self._sink.error("E5001", f"type mismatch in assign: {dst_type} != {src_type}", instr.span)

            elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD):
                left = instr.operands[0] if len(instr.operands) > 0 else None
                right = instr.operands[1] if len(instr.operands) > 1 else None
                left_type = self._get_type(left, temp_types, var_types)
                right_type = self._get_type(right, temp_types, var_types)

                if left_type == IRType.BOOL or right_type == IRType.BOOL:
                    self._sink.error("E5001", "bool value used in arithmetic binop", instr.span)
                if left_type != right_type:
                    self._sink.error("E5001", f"operand type mismatch in {opcode.value}: {left_type} != {right_type}", instr.span)

                dst_type = self._get_type(instr.dst, temp_types, var_types)
                if dst_type != left_type:
                    self._sink.error("E5001", f"result type mismatch in {opcode.value}: {dst_type} != {left_type}", instr.span)

            elif opcode == Opcode.NEG:
                operand = instr.operands[0] if instr.operands else None
                op_type = self._get_type(operand, temp_types, var_types)
                if op_type == IRType.BOOL:
                    self._sink.error("E5001", "bool value used in neg unop", instr.span)
                dst_type = self._get_type(instr.dst, temp_types, var_types)
                if dst_type != op_type:
                    self._sink.error("E5001", f"result type mismatch in neg: {dst_type} != {op_type}", instr.span)

            elif opcode == Opcode.CMP:
                left = instr.operands[0] if len(instr.operands) > 0 else None
                right = instr.operands[1] if len(instr.operands) > 1 else None
                left_type = self._get_type(left, temp_types, var_types)
                right_type = self._get_type(right, temp_types, var_types)
                if left_type != right_type:
                    self._sink.error("E5001", f"operand type mismatch in cmp: {left_type} != {right_type}", instr.span)
                dst_type = self._get_type(instr.dst, temp_types, var_types)
                if dst_type != IRType.BOOL:
                    self._sink.error("E5001", f"cmp destination must be bool, got {dst_type}", instr.span)

            elif opcode == Opcode.BRANCH:
                cond = instr.operands[0] if instr.operands else None
                cond_type = self._get_type(cond, temp_types, var_types)
                if cond_type != IRType.BOOL:
                    self._sink.error("E5001", f"branch condition must be bool, got {cond_type}", instr.span)

                t_label = str(instr.operands[1]) if len(instr.operands) > 1 else ""
                f_label = str(instr.operands[2]) if len(instr.operands) > 2 else ""

                if t_label not in label_instrs:
                    self._sink.error("E5001", f"branch target label missing: '{t_label}'", instr.span)
                if f_label not in label_instrs:
                    self._sink.error("E5001", f"branch target label missing: '{f_label}'", instr.span)

                # Check label region consistency
                t_match = LABEL_PATTERN.match(t_label)
                f_match = LABEL_PATTERN.match(f_label)
                if t_match and f_match:
                    t_region = t_match.group(2)
                    f_region = f_match.group(2)
                    if t_region != f_region:
                        self._sink.error("E5001", f"branch targets belong to different regions: {t_region} != {f_region}", instr.span)

            elif opcode == Opcode.JUMP:
                target = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                if target not in label_instrs:
                    self._sink.error("E5001", f"jump target label missing: '{target}'", instr.span)

            elif opcode == Opcode.LABEL:
                label_name = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                # Validate label naming convention
                match = LABEL_PATTERN.match(label_name)
                if not match:
                    self._sink.error("E5001", f"non-canonical label name: '{label_name}'", instr.span)

            elif opcode == Opcode.RETURN:
                if instr.operands:
                    ret_val = instr.operands[0]
                    ret_type = self._get_type(ret_val, temp_types, var_types)
                    if ret_type != func.return_type:
                        self._sink.error("E5001", f"return type mismatch: expected {func.return_type}, got {ret_type}", instr.span)
                else:
                    if func.return_type != IRType.VOID:
                        self._sink.error("E5001", f"non-void function must return a value, got void return", instr.span)

            # 4. Check destination temp definition (single assignment)
            if instr.dst is not None and isinstance(instr.dst, TempRef):
                temp_id = instr.dst.temp_id
                if temp_id in defined_temps:
                    self._sink.error("E5001", f"temporary defined more than once: '{temp_id}'", instr.span)
                defined_temps.add(temp_id)
                temp_types[temp_id] = instr.dst.type

        # 5. Check canonical control flow shapes (§D.3.6)
        self._check_canonical_shapes(func.body)

    def _get_type(self, operand: Operand | None, temp_types: dict[str, IRType], var_types: dict[str, IRType]) -> IRType:
        if operand is None:
            return IRType.VOID
        if isinstance(operand, Const):
            return operand.type
        if isinstance(operand, TempRef):
            return temp_types.get(operand.temp_id, operand.type)
        if isinstance(operand, VarRef):
            return var_types.get(operand.ir_name, operand.type)
        if isinstance(operand, StrConst):
            return IRType.STR
        return IRType.I32

    def _check_canonical_shapes(self, body: list[Instruction]) -> None:
        """Verify that control-flow shapes strictly follow ARCH §D.3.6."""
        # Find all branch instructions and verify their shape
        for i, instr in enumerate(body):
            if instr.opcode == Opcode.BRANCH:
                t_label = str(instr.operands[1]) if len(instr.operands) > 1 else ""
                f_label = str(instr.operands[2]) if len(instr.operands) > 2 else ""

                t_match = LABEL_PATTERN.match(t_label)
                f_match = LABEL_PATTERN.match(f_label)
                if not t_match or not f_match:
                    continue

                t_role, region = t_match.group(1), t_match.group(2)
                f_role = f_match.group(1)

                if t_role == "if_then" and f_role == "if_else":
                    # Canonical if/else: branch c, if_then_rN, if_else_rN
                    # Must be followed by if_then_rN: ... jump if_end_rN ... if_else_rN: ... if_end_rN:
                    self._verify_if_shape(body, i, region)
                elif t_role == "loop_body" and f_role == "loop_end":
                    # Canonical loop: branch c, loop_body_rN, loop_end_rN
                    self._verify_loop_shape(body, i, region)
                else:
                    self._sink.error("E5001", f"non-canonical branch shape with targets '{t_label}', '{f_label}'", instr.span)

    def _verify_if_shape(self, body: list[Instruction], branch_idx: int, region: str) -> None:
        expected_then = f"if_then_{region}"
        expected_else = f"if_else_{region}"
        expected_end = f"if_end_{region}"

        # Find positions of labels and jumps
        indices: dict[str, int] = {}
        jump_end_idx = -1
        for idx in range(branch_idx + 1, len(body)):
            instr = body[idx]
            if instr.opcode == Opcode.LABEL:
                name = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                indices[name] = idx
            elif instr.opcode == Opcode.JUMP:
                target = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                if target == expected_end and jump_end_idx == -1:
                    jump_end_idx = idx

        if (expected_then not in indices or
            expected_else not in indices or
            expected_end not in indices or
            jump_end_idx == -1):
            self._sink.error("E5001", f"incomplete canonical if-shape for {region}", body[branch_idx].span)
            return

        then_pos = indices[expected_then]
        else_pos = indices[expected_else]
        end_pos = indices[expected_end]

        # Order must be: then_pos < jump_end_idx < else_pos < end_pos
        if not (branch_idx < then_pos < jump_end_idx < else_pos < end_pos):
            self._sink.error("E5001", f"non-canonical ordering in if-shape for {region}", body[branch_idx].span)

    def _verify_loop_shape(self, body: list[Instruction], branch_idx: int, region: str) -> None:
        expected_head = f"loop_head_{region}"
        expected_body = f"loop_body_{region}"
        expected_end = f"loop_end_{region}"

        head_idx = -1
        body_idx = -1
        end_idx = -1
        jump_head_idx = -1

        for idx, instr in enumerate(body):
            if instr.opcode == Opcode.LABEL:
                name = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                if name == expected_head:
                    head_idx = idx
                elif name == expected_body:
                    body_idx = idx
                elif name == expected_end:
                    end_idx = idx
            elif instr.opcode == Opcode.JUMP:
                target = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                if target == expected_head and idx > branch_idx:
                    jump_head_idx = idx

        if head_idx == -1 or body_idx == -1 or end_idx == -1 or jump_head_idx == -1:
            self._sink.error("E5001", f"incomplete canonical loop-shape for {region}", body[branch_idx].span)
            return

        # Order must be: head < branch < body < jump_head < end
        if not (head_idx < branch_idx < body_idx < jump_head_idx < end_idx):
            self._sink.error("E5001", f"non-canonical ordering in loop-shape for {region}", body[branch_idx].span)
