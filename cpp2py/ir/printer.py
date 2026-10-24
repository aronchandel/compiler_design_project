"""Deterministic textual formatting for the cpp2py Intermediate Representation (IR).

Conforms to ARCH §D.3.7 and §D.4 Stage 3.
"""

from __future__ import annotations

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
    Operand,
)


def format_module(module: IRModule) -> str:
    """Format an entire IRModule as text."""
    parts: list[str] = []
    for func in module.functions:
        parts.append(format_function(func))
    return "\n\n".join(parts) + "\n" if parts else ""


def format_function(func: IRFunction) -> str:
    """Format a single IRFunction as text."""
    if func.params:
        param_strs = [f"{p.ir_name} : {p.type}" for p in func.params]
        params_str = ", ".join(param_strs)
        header = f"function {func.name}({params_str}) -> {func.return_type} {{"
    else:
        header = f"function {func.name}() -> {func.return_type} {{"

    lines: list[str] = [header]

    for instr in func.body:
        lines.append(format_instruction(instr))

    lines.append("}")
    return "\n".join(lines)


def format_instruction(instr: Instruction) -> str:
    """Format a single Instruction line with column alignment."""
    body = _format_instruction_body(instr)

    # Prefix: 2 spaces indentation + op_id left-justified in 7 chars
    prefix = f"  {instr.op_id:<7}"

    # Pad body to 32 characters for fixed-width alignment
    if len(body) < 32:
        body_padded = body + " " * (32 - len(body))
    else:
        body_padded = body + " "

    line = prefix + body_padded

    # Comment section: spans, metadata, origin
    comment_parts: list[str] = []

    if instr.span is not None:
        loc = f"L{instr.span.start.line}:{instr.span.start.col}"
        comment_parts.append(loc)
    elif instr.role is not None and instr.region_id is not None:
        comment_parts.append(f"role={instr.role} region={instr.region_id}")

    if instr.origin:
        derived = f"[derived from {', '.join(instr.origin)}]"
        if comment_parts:
            comment_text = comment_parts[0] + "     " + derived
        else:
            comment_text = derived
    else:
        comment_text = comment_parts[0] if comment_parts else ""

    if comment_text:
        line += "; " + comment_text

    return line.rstrip()


def _format_instruction_body(instr: Instruction) -> str:
    opcode = instr.opcode

    if opcode == Opcode.DECLARE:
        var = instr.dst or instr.operands[0]
        var_type = var.type if hasattr(var, "type") else "i32"
        return f"declare {var} : {var_type}"

    elif opcode == Opcode.ASSIGN:
        src = instr.operands[0]
        return f"{instr.dst} = assign {src}"

    elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD):
        left, right = instr.operands[0], instr.operands[1]
        return f"{instr.dst} = {opcode.value} {left}, {right}"

    elif opcode == Opcode.NEG:
        operand = instr.operands[0]
        return f"{instr.dst} = neg {operand}"

    elif opcode == Opcode.READ:
        target = instr.dst or instr.operands[0]
        return f"read {target}"

    elif opcode == Opcode.PRINT:
        items = [str(op) for op in instr.operands]
        if instr.newline:
            items.append("endl")
        return f"print {', '.join(items)}"

    elif opcode == Opcode.RETURN:
        if instr.operands:
            return f"return {instr.operands[0]}"
        return "return"

    elif opcode == Opcode.LABEL:
        label = instr.label_name or (str(instr.operands[0]) if instr.operands else "L")
        return f"{label}:"

    elif opcode == Opcode.JUMP:
        target = instr.label_name or str(instr.operands[0])
        return f"jump {target}"

    elif opcode == Opcode.BRANCH:
        cond = str(instr.operands[0])
        t_label = instr.operands[1] if len(instr.operands) > 1 else ""
        f_label = instr.operands[2] if len(instr.operands) > 2 else ""
        return f"branch {cond}, {t_label}, {f_label}"

    elif opcode == Opcode.CMP:
        cmp_op = instr.cmp_op or "eq"
        left, right = str(instr.operands[0]), str(instr.operands[1])
        return f"{instr.dst} = cmp {cmp_op} {left}, {right}"

    elif opcode == Opcode.CALL:
        func = instr.func_name or "f"
        args = ", ".join(str(op) for op in instr.operands)
        if instr.dst:
            return f"{instr.dst} = call {func}({args})"
        return f"call {func}({args})"

    return f"{opcode.value}"
