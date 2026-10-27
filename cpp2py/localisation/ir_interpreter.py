from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cpp2py.config import OverflowPolicy, TargetModel
from cpp2py.ir.model import (
    Const,
    IRFunction,
    IRModule,
    IRType,
    Instruction,
    LabelRef,
    Opcode,
    Operand,
    StrConst,
    TempRef,
    VarRef,
)
from cpp2py.source import SourceSpan

@dataclass(slots=True)
class TraceEntry:
    step: int
    op_id: str
    opcode: Opcode
    dst: str | None
    operand_names: tuple[str, ...]
    operand_values: list[Any]
    result: Any
    span: SourceSpan | None
    output_chunk: str | None = None
    func_name: str = ""

@dataclass
class InterpretationResult:
    stdout: str
    exit_code: int
    success: bool
    step_count: int
    trace: list[TraceEntry]
    error: str | None = None
    ub_events: list[str] = field(default_factory=list)

def wrap_int(val: int, bits: int) -> int:
    mask = (1 << bits) - 1
    val = val & mask
    max_val = (1 << (bits - 1)) - 1
    if val > max_val:
        val -= (1 << bits)
    return val

def in_range(val: int, bits: int) -> bool:
    min_val = -(1 << (bits - 1))
    max_val = (1 << (bits - 1)) - 1
    return min_val <= val <= max_val

def get_type_bits(ir_type: IRType | str, target: TargetModel) -> int:
    type_str = ir_type.value if isinstance(ir_type, IRType) else str(ir_type)
    if type_str == "i64":
        return target.long_long_bits
    return target.int_bits

def cpp_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("integer division by zero")
    sign = -1 if (a < 0) ^ (b < 0) else 1
    return sign * (abs(a) // abs(b))

def cpp_mod(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("integer modulo by zero")
    return a - b * cpp_div(a, b)

class IRInterpreter:

    def __init__(
        self,
        module: IRModule,
        target: TargetModel | None = None,
        overflow_policy: OverflowPolicy | str | None = None,
        step_limit: int = 200000,
        record_trace: bool = True,
    ) -> None:
        self.module = module
        self.target = target if target is not None else TargetModel()
        if overflow_policy is not None:
            if isinstance(overflow_policy, str):
                self.policy = OverflowPolicy(overflow_policy)
            else:
                self.policy = overflow_policy
        else:
            self.policy = self.target.overflow_policy

        self.step_limit = step_limit
        self.record_trace = record_trace

        self.functions: dict[str, IRFunction] = {f.name: f for f in module.functions}
        self.stdout_chunks: list[str] = []
        self.trace: list[TraceEntry] = []
        self.ub_events: list[str] = []
        self.step_count = 0

    def run(self, stdin_text: str = "") -> InterpretationResult:
        if "main" not in self.functions:
            return InterpretationResult(
                stdout="",
                exit_code=1,
                success=False,
                step_count=0,
                trace=[],
                error="No main() function found in IR module",
            )

        token_iter = iter(stdin_text.split())

        try:
            exit_code = self._execute_function("main", [], token_iter)
            stdout = "".join(self.stdout_chunks)
            return InterpretationResult(
                stdout=stdout,
                exit_code=exit_code if exit_code is not None else 0,
                success=True,
                step_count=self.step_count,
                trace=self.trace,
                ub_events=self.ub_events,
            )
        except Exception as e:
            stdout = "".join(self.stdout_chunks)
            return InterpretationResult(
                stdout=stdout,
                exit_code=1,
                success=False,
                step_count=self.step_count,
                trace=self.trace,
                error=str(e),
                ub_events=self.ub_events,
            )

    def _execute_function(
        self,
        func_name: str,
        args: list[int],
        token_iter: Any,
    ) -> Any:
        func = self.functions[func_name]

        labels: dict[str, int] = {}
        for idx, instr in enumerate(func.body):
            if instr.opcode == Opcode.LABEL:
                lbl = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                labels[lbl] = idx

        locals_map: dict[str, int] = {}
        temps_map: dict[str, Any] = {}

        for idx, param in enumerate(func.params):
            if idx < len(args):
                locals_map[param.ir_name] = args[idx]

        pc = 0
        body_len = len(func.body)

        while pc < body_len:
            self.step_count += 1
            if self.step_count > self.step_limit:
                raise TimeoutError(f"Step limit {self.step_limit} exceeded in function {func_name}")

            instr = func.body[pc]
            opcode = instr.opcode

            next_pc = pc + 1
            output_chunk: str | None = None
            eval_operands: list[Any] = []
            op_names: tuple[str, ...] = tuple(
                str(op) if not isinstance(op, StrConst) else "" for op in instr.operands
            )
            result_val: Any = None

            def eval_op(op: Operand) -> Any:
                if isinstance(op, Const):
                    return op.value
                elif isinstance(op, VarRef):
                    return locals_map.get(op.ir_name, 0)
                elif isinstance(op, TempRef):
                    return temps_map.get(op.temp_id, 0)
                elif isinstance(op, StrConst):
                    return op.text
                elif isinstance(op, LabelRef):
                    return op.name
                return 0

            if opcode == Opcode.DECLARE:
                var = instr.dst or instr.operands[0]
                if isinstance(var, VarRef):
                    if var.ir_name not in locals_map:
                        locals_map[var.ir_name] = 0
                result_val = 0

            elif opcode == Opcode.ASSIGN:
                src_val = eval_op(instr.operands[0])
                eval_operands = [src_val]
                result_val = src_val
                if isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = src_val
                elif isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = src_val

            elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL):
                v1 = eval_op(instr.operands[0])
                v2 = eval_op(instr.operands[1])
                eval_operands = [v1, v2]

                if opcode == Opcode.ADD:
                    math_val = v1 + v2
                elif opcode == Opcode.SUB:
                    math_val = v1 - v2
                else:
                    math_val = v1 * v2

                bits = get_type_bits(instr.dst.type if instr.dst else IRType.I32, self.target)

                if in_range(math_val, bits):
                    result_val = math_val
                else:
                    if self.policy == OverflowPolicy.TRAP:
                        raise OverflowError(f"signed overflow in {opcode.value}: {v1}, {v2}")
                    elif self.policy == OverflowPolicy.WRAP:
                        result_val = wrap_int(math_val, bits)
                    else:
                        self.ub_events.append(f"signed overflow in {opcode.value}: {math_val} exceeds {bits}-bit range")
                        result_val = math_val

                if isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = result_val
                elif isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = result_val

            elif opcode == Opcode.NEG:
                v = eval_op(instr.operands[0])
                eval_operands = [v]
                math_val = -v
                bits = get_type_bits(instr.dst.type if instr.dst else IRType.I32, self.target)
                if in_range(math_val, bits):
                    result_val = math_val
                else:
                    if self.policy == OverflowPolicy.TRAP:
                        raise OverflowError(f"signed overflow in negation of {v}")
                    elif self.policy == OverflowPolicy.WRAP:
                        result_val = wrap_int(math_val, bits)
                    else:
                        self.ub_events.append(f"signed overflow in neg: -{v}")
                        result_val = math_val

                if isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = result_val
                elif isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = result_val

            elif opcode == Opcode.DIV:
                v1 = eval_op(instr.operands[0])
                v2 = eval_op(instr.operands[1])
                eval_operands = [v1, v2]

                bits = get_type_bits(instr.dst.type if instr.dst else IRType.I32, self.target)
                min_int = -(1 << (bits - 1))

                if v2 == 0:
                    self.ub_events.append("division by zero")
                    raise ZeroDivisionError("division by zero")

                if v1 == min_int and v2 == -1:
                    if self.policy == OverflowPolicy.TRAP:
                        raise OverflowError("signed overflow in division: INT_MIN / -1")
                    elif self.policy == OverflowPolicy.WRAP:
                        result_val = min_int
                    else:
                        self.ub_events.append("signed overflow in division: INT_MIN / -1")
                        result_val = -min_int
                else:
                    result_val = cpp_div(v1, v2)

                if isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = result_val
                elif isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = result_val

            elif opcode == Opcode.MOD:
                v1 = eval_op(instr.operands[0])
                v2 = eval_op(instr.operands[1])
                eval_operands = [v1, v2]

                bits = get_type_bits(instr.dst.type if instr.dst else IRType.I32, self.target)
                min_int = -(1 << (bits - 1))

                if v2 == 0:
                    self.ub_events.append("modulo by zero")
                    raise ZeroDivisionError("modulo by zero")

                if v1 == min_int and v2 == -1:
                    if self.policy == OverflowPolicy.TRAP:
                        raise OverflowError("signed overflow in modulo: INT_MIN % -1")
                    elif self.policy == OverflowPolicy.WRAP:
                        result_val = 0
                    else:
                        self.ub_events.append("signed overflow in modulo: INT_MIN % -1")
                        result_val = 0
                else:
                    result_val = cpp_mod(v1, v2)

                if isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = result_val
                elif isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = result_val

            elif opcode == Opcode.READ:
                target_var = instr.dst or instr.operands[0]
                try:
                    tok = next(token_iter)
                    val = int(tok)
                except StopIteration:
                    val = 0
                eval_operands = [val]
                result_val = val
                if isinstance(target_var, VarRef):
                    locals_map[target_var.ir_name] = val
                elif isinstance(target_var, TempRef):
                    temps_map[target_var.temp_id] = val

            elif opcode == Opcode.PRINT:
                parts = []
                for item in instr.operands:
                    val = eval_op(item)
                    eval_operands.append(val)
                    parts.append(str(val))
                chunk = "".join(parts)
                if instr.newline:
                    chunk += "\n"
                self.stdout_chunks.append(chunk)
                output_chunk = chunk
                result_val = chunk

            elif opcode == Opcode.LABEL:
                pass

            elif opcode == Opcode.JUMP:
                target_label = instr.label_name or str(instr.operands[0])
                eval_operands = [target_label]
                next_pc = labels[target_label]

            elif opcode == Opcode.BRANCH:
                cond_val = eval_op(instr.operands[0])
                t_lbl = instr.operands[1].name if isinstance(instr.operands[1], LabelRef) else str(instr.operands[1])
                f_lbl = instr.operands[2].name if isinstance(instr.operands[2], LabelRef) else str(instr.operands[2])
                eval_operands = [cond_val, t_lbl, f_lbl]
                if bool(cond_val):
                    next_pc = labels[t_lbl]
                else:
                    next_pc = labels[f_lbl]

            elif opcode == Opcode.CMP:
                v1 = eval_op(instr.operands[0])
                v2 = eval_op(instr.operands[1])
                eval_operands = [v1, v2]
                cmp_op = instr.cmp_op or "eq"
                if cmp_op == "eq":
                    res_bool = v1 == v2
                elif cmp_op == "ne":
                    res_bool = v1 != v2
                elif cmp_op == "lt":
                    res_bool = v1 < v2
                elif cmp_op == "le":
                    res_bool = v1 <= v2
                elif cmp_op == "gt":
                    res_bool = v1 > v2
                elif cmp_op == "ge":
                    res_bool = v1 >= v2
                else:
                    res_bool = False
                result_val = 1 if res_bool else 0
                if isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = result_val
                elif isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = result_val

            elif opcode == Opcode.CALL:
                target_fn = instr.func_name or "f"
                call_args = [eval_op(op) for op in instr.operands]
                eval_operands = call_args
                ret_val = self._execute_function(target_fn, call_args, token_iter)
                result_val = ret_val
                if instr.dst:
                    if isinstance(instr.dst, TempRef):
                        temps_map[instr.dst.temp_id] = ret_val
                    elif isinstance(instr.dst, VarRef):
                        locals_map[instr.dst.ir_name] = ret_val

            elif opcode == Opcode.CAST:
                src_val = eval_op(instr.operands[0])
                eval_operands = [src_val]
                target_bits = get_type_bits(instr.dst.type if instr.dst else IRType.I32, self.target)
                result_val = wrap_int(src_val, target_bits)
                if isinstance(instr.dst, TempRef):
                    temps_map[instr.dst.temp_id] = result_val
                elif isinstance(instr.dst, VarRef):
                    locals_map[instr.dst.ir_name] = result_val

            elif opcode == Opcode.RETURN:
                if instr.operands:
                    ret_val = eval_op(instr.operands[0])
                    eval_operands = [ret_val]
                    result_val = ret_val
                else:
                    result_val = 0
                if self.record_trace:
                    self.trace.append(
                        TraceEntry(
                            step=self.step_count,
                            op_id=instr.op_id,
                            opcode=opcode,
                            dst=str(instr.dst) if instr.dst else None,
                            operand_names=op_names,
                            operand_values=eval_operands,
                            result=result_val,
                            span=instr.span,
                            output_chunk=output_chunk,
                            func_name=func_name,
                        )
                    )
                return result_val

            if self.record_trace:
                self.trace.append(
                    TraceEntry(
                        step=self.step_count,
                        op_id=instr.op_id,
                        opcode=opcode,
                        dst=str(instr.dst) if instr.dst else None,
                        operand_names=op_names,
                        operand_values=eval_operands,
                        result=result_val,
                        span=instr.span,
                        output_chunk=output_chunk,
                        func_name=func_name,
                    )
                )

            pc = next_pc

        return 0

def interpret_module(
    module: IRModule,
    stdin_text: str = "",
    target: TargetModel | None = None,
    overflow_policy: OverflowPolicy | str | None = None,
    step_limit: int = 200000,
    record_trace: bool = True,
) -> InterpretationResult:
    interpreter = IRInterpreter(
        module=module,
        target=target,
        overflow_policy=overflow_policy,
        step_limit=step_limit,
        record_trace=record_trace,
    )
    return interpreter.run(stdin_text)
