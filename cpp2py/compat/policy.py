"""Decision policy rules constructing a CompatPlan per ARCH §E.5."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cpp2py.analysis.intervals import Interval, add, sub, mul, neg, div, mod, cast
from cpp2py.analysis.risk import Risk, classify_risks
from cpp2py.compat.plan import CompatAction, CompatDecision, CompatPlan
from cpp2py.config import CompatMode, OverflowPolicy
from cpp2py.ir.model import Opcode, IRType, IRModule, Instruction

if TYPE_CHECKING:
    from cpp2py.config import CompilerConfig
    from cpp2py.diagnostics import DiagnosticSink
    from cpp2py.analysis.range_analysis import RangeResult


def decide(
    instr: Instruction,
    risks: set[Risk] | frozenset[Risk],
    config: CompilerConfig,
    operand_ranges: tuple[Interval, ...] = (),
    result_range: Interval | None = None,
    sink: DiagnosticSink | None = None,
) -> CompatDecision:
    """Decide compatibility action, helper, reason, and warnings for an instruction per ARCH §E.5."""
    mode = config.compat_mode
    target = config.target
    policy = target.overflow_policy
    opcode = instr.opcode

    action: CompatAction = CompatAction.NATIVE
    helper: str | None = None
    reason: str = ""
    wrap_int_min_div: bool = False
    warning_code: str | None = None

    def emit_warn(code: str, msg: str) -> None:
        nonlocal warning_code
        warning_code = code
        if sink is not None:
            sink.warning(code, msg, instr.span)

    # ---------- 1. NAIVE MODE ----------
    if mode == CompatMode.NAIVE:
        action = CompatAction.NATIVE
        helper = None
        reason = "naive mode: native operator emitted without range analysis"
        if opcode in (Opcode.DIV, Opcode.MOD):
            op_sym = "/" if opcode == Opcode.DIV else "%"
            emit_warn(
                "W6001",
                f"'{op_sym}' is emitted as Python floor division; the result differs from C++ when an operand is negative",
            )

    # ---------- 2. ALWAYS MODE ----------
    elif mode == CompatMode.ALWAYS:
        if opcode == Opcode.DIV:
            action = CompatAction.HELPER
            helper = "_cpp_div"
            reason = "always mode: protective helper for division"
        elif opcode == Opcode.MOD:
            action = CompatAction.HELPER
            helper = "_cpp_mod"
            reason = "always mode: protective helper for remainder"
        elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.NEG):
            dst_t = instr.dst.type if instr.dst else IRType.I32
            if policy == OverflowPolicy.WRAP:
                action = CompatAction.HELPER
                helper = "_wrap_i64" if dst_t == IRType.I64 else "_wrap_i32"
                reason = "always mode: wrap policy wrapper"
            elif policy == OverflowPolicy.TRAP:
                action = CompatAction.HELPER
                helper = "_check_i64" if dst_t == IRType.I64 else "_check_i32"
                reason = "always mode: trap policy checker"
            else:
                action = CompatAction.NATIVE
                helper = None
                reason = "always mode: assume_no_overflow uses native arithmetic"
        elif opcode == Opcode.CAST:
            dst_t = instr.dst.type if instr.dst else IRType.I32
            if dst_t == IRType.I32:
                action = CompatAction.HELPER
                helper = "_wrap_i32"
                reason = "always mode: wrap helper on narrowing cast"
            else:
                action = CompatAction.NATIVE
                helper = None
                reason = "always mode: widening cast is native"

    # ---------- 3. RANGE_GUIDED MODE ----------
    elif mode == CompatMode.RANGE_GUIDED:
        if opcode == Opcode.DIV:
            if Risk.DIV_BY_ZERO_CERTAIN in risks:
                emit_warn("W6003", "divisor is zero")
            elif Risk.DIV_BY_ZERO_POSSIBLE in risks:
                emit_warn("W6003", "divisor may be zero")

            if Risk.INT_MIN_DIV_MINUS_ONE in risks and policy == OverflowPolicy.WRAP:
                wrap_int_min_div = True

            if (
                Risk.DIV_TRUNC_DIFFERS in risks
                or Risk.DIV_BY_ZERO_CERTAIN in risks
                or Risk.DIV_BY_ZERO_POSSIBLE in risks
                or Risk.INT_MIN_DIV_MINUS_ONE in risks
            ):
                action = CompatAction.HELPER
                helper = "_cpp_div"
                reason = "range allows negative operand; C++ truncating division needed"
            else:
                action = CompatAction.NATIVE
                helper = None
                reason = "proven non-negative dividend and positive divisor: native // is equivalent"

        elif opcode == Opcode.MOD:
            if Risk.DIV_BY_ZERO_CERTAIN in risks:
                emit_warn("W6003", "divisor is zero")
            elif Risk.DIV_BY_ZERO_POSSIBLE in risks:
                emit_warn("W6003", "divisor may be zero")

            if Risk.INT_MIN_DIV_MINUS_ONE in risks and policy == OverflowPolicy.WRAP:
                wrap_int_min_div = True

            if (
                Risk.MOD_SIGN_DIFFERS in risks
                or Risk.DIV_BY_ZERO_CERTAIN in risks
                or Risk.DIV_BY_ZERO_POSSIBLE in risks
                or Risk.INT_MIN_DIV_MINUS_ONE in risks
            ):
                action = CompatAction.HELPER
                helper = "_cpp_mod"
                reason = "range allows negative operand; C++ remainder sign semantics needed"
            else:
                action = CompatAction.NATIVE
                helper = None
                reason = "proven non-negative dividend and positive divisor: native % is equivalent"

        elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.NEG):
            if Risk.SIGNED_OVERFLOW_POSSIBLE in risks:
                dst_t = instr.dst.type if instr.dst else IRType.I32
                if policy == OverflowPolicy.ASSUME_NO_OVERFLOW:
                    emit_warn("W6002", "operation may overflow")
                    action = CompatAction.NATIVE
                    helper = None
                    reason = "assume_no_overflow policy: no helper inserted"
                elif policy == OverflowPolicy.WRAP:
                    action = CompatAction.HELPER
                    helper = "_wrap_i64" if dst_t == IRType.I64 else "_wrap_i32"
                    reason = f"wrap policy: {helper} inserted for possible overflow"
                elif policy == OverflowPolicy.TRAP:
                    action = CompatAction.HELPER
                    helper = "_check_i64" if dst_t == IRType.I64 else "_check_i32"
                    reason = f"trap policy: {helper} inserted for possible overflow"
            else:
                action = CompatAction.NATIVE
                helper = None
                reason = "proven within type bounds: native operator is safe"

        elif opcode == Opcode.CAST:
            if Risk.NARROWING_LOSSY in risks:
                emit_warn("W6006", "possibly lossy narrowing conversion")
                action = CompatAction.HELPER
                helper = "_wrap_i32"
                reason = "possibly lossy narrowing cast: _wrap_i32 applied per TargetModel"
            else:
                action = CompatAction.NATIVE
                helper = None
                reason = "exact cast: range fits target type"

    return CompatDecision(
        op_id=instr.op_id,
        risks=set(risks),
        action=action,
        helper=helper,
        reason=reason,
        operand_ranges=operand_ranges,
        result_range=result_range if result_range is not None else (operand_ranges[0] if operand_ranges else Interval(0, 0)),
        policy=policy,
        wrap_int_min_div=wrap_int_min_div,
        warning=warning_code,
    )


def decide_compat(
    instr: Instruction,
    left_range: Interval | None,
    right_range: Interval | None,
    config: CompilerConfig,
    sink: DiagnosticSink | None = None,
) -> CompatDecision:
    """Helper for testing and single-op decision making."""
    target = config.target
    op_ranges = tuple(r for r in [left_range, right_range] if r is not None)
    res_range = op_ranges[0] if op_ranges else Interval(0, 0)
    if len(op_ranges) == 2:
        if instr.opcode == Opcode.ADD:
            res_range = add(op_ranges[0], op_ranges[1])
        elif instr.opcode == Opcode.SUB:
            res_range = sub(op_ranges[0], op_ranges[1])
        elif instr.opcode == Opcode.MUL:
            res_range = mul(op_ranges[0], op_ranges[1])
        elif instr.opcode == Opcode.DIV:
            res_range = div(op_ranges[0], op_ranges[1])
        elif instr.opcode == Opcode.MOD:
            res_range = mod(op_ranges[0], op_ranges[1])
    elif len(op_ranges) == 1:
        if instr.opcode == Opcode.NEG:
            res_range = neg(op_ranges[0])
        elif instr.opcode == Opcode.CAST:
            res_range = op_ranges[0]
    risks = classify_risks(instr, op_ranges, res_range, target)
    return decide(instr, risks, config, op_ranges, res_range, sink)


def build_plan(
    module: IRModule,
    range_result: RangeResult,
    config: CompilerConfig,
    sink: DiagnosticSink,
) -> CompatPlan:
    """Build a CompatPlan for the module by consulting range analysis results and active policy."""
    mode = config.compat_mode
    target = config.target
    policy = target.overflow_policy

    decisions: dict[str, CompatDecision] = {}
    counts: dict[str, int] = {"native": 0, "helper": 0}

    # Warn if assumptions influenced decisions
    if range_result.assumptions:
        sink.warning("W6005", "an assumed input range influenced a decision", None)

    for func in module.functions:
        for instr in func.body:
            opcode = instr.opcode

            # Only arithmetic, div, mod, neg, and cast are candidate operations
            if opcode not in (Opcode.DIV, Opcode.MOD, Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.NEG, Opcode.CAST):
                continue

            op_info = range_result.by_op.get(instr.op_id)
            op_ranges = op_info.operand_ranges if op_info else ()
            res_range = op_info.result_range if op_info else (op_ranges[0] if op_ranges else None)
            risks = set(op_info.risks) if op_info else set()

            decision = decide(instr, risks, config, op_ranges, res_range, sink)
            if decision.action == CompatAction.HELPER:
                counts["helper"] += 1
            else:
                counts["native"] += 1

            decisions[instr.op_id] = decision

    return CompatPlan(
        mode=mode,
        policy=policy,
        decisions=decisions,
        assumptions=list(range_result.assumptions),
        counts=counts,
    )
