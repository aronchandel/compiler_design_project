"""Intra-procedural interval range analysis on cpp2py IR.

Conforms to ARCH §E.4 and IMPLEMENTATION_PLAN.md:
- Forward worklist dataflow per function over CFG basic blocks.
- Entry state: parameters full type range; reads full type range unless assumed.
- Join at basic block entries; widening to type bounds at loop heads.
- Branch refinement on simple comparisons along true/false edges.
- Transfer functions on mathematical integers; clamping / policy handling for overflow.
- Produces RangeResult(by_op, assumptions, converged, iterations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cpp2py.analysis.intervals import (
    Interval,
    BOTTOM,
    add,
    sub,
    mul,
    neg,
    div,
    mod,
    cast,
)
from cpp2py.analysis.cfg import CFG, BasicBlock
from cpp2py.analysis.risk import Risk, classify_risks
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    VarRef,
    TempRef,
    Operand,
    IRType,
)
from cpp2py.config import OverflowPolicy

if TYPE_CHECKING:
    from cpp2py.config import CompilerConfig, TargetModel


@dataclass(frozen=True, slots=True)
class OpRangeInfo:
    op_id: str
    opcode: Opcode
    operand_ranges: tuple[Interval, ...]
    exact_result_range: Interval
    result_range: Interval
    risks: set[Risk]

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_id": self.op_id,
            "opcode": self.opcode.value,
            "operand_ranges": [r.to_dict() for r in self.operand_ranges],
            "exact_result_range": self.exact_result_range.to_dict(),
            "result_range": self.result_range.to_dict(),
            "risks": sorted(r.value for r in self.risks),
        }


@dataclass
class RangeResult:
    by_op: dict[str, OpRangeInfo] = field(default_factory=dict)
    assumptions: list[tuple[str, Interval]] = field(default_factory=list)
    converged: bool = True
    iterations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "converged": self.converged,
            "iterations": self.iterations,
            "assumptions": [
                {"target": target, "range": r.to_dict()}
                for target, r in sorted(self.assumptions, key=lambda x: x[0])
            ],
            "by_op": {
                op_id: self.by_op[op_id].to_dict()
                for op_id in sorted(self.by_op.keys())
            },
        }


def _type_bounds(t: IRType, target: TargetModel) -> tuple[int, int]:
    if t == IRType.I64:
        return target.long_long_min, target.long_long_max
    return target.int_min, target.int_max


def _op_key(op: Operand) -> str:
    if isinstance(op, VarRef):
        return f"var_{op.ir_name}"
    elif isinstance(op, TempRef):
        return f"temp_{op.temp_id}"
    return str(op)


State = dict[str, Interval]


def _join_states(s1: State | None, s2: State) -> State:
    if s1 is None:
        return dict(s2)
    keys = set(s1.keys()) | set(s2.keys())
    res: State = {}
    for k in keys:
        v1 = s1.get(k, BOTTOM)
        v2 = s2.get(k, BOTTOM)
        res[k] = v1.join(v2)
    return res


def _states_equal(s1: State | None, s2: State | None) -> bool:
    if s1 is None or s2 is None:
        return s1 == s2
    if set(s1.keys()) != set(s2.keys()):
        return False
    for k in s1:
        if s1[k] != s2[k]:
            return False
    return True


def _refine_comparison(
    cmp_op: str,
    left_key: str | None,
    right_key: str | None,
    left_int: Interval,
    right_int: Interval,
    state: State,
    is_true_branch: bool,
) -> State:
    """Refine left and right operand intervals along a branch edge."""
    res = dict(state)
    op = cmp_op

    if not is_true_branch:
        inv_map = {
            "lt": "ge",
            "le": "gt",
            "gt": "le",
            "ge": "lt",
            "eq": "ne",
            "ne": "eq",
        }
        op = inv_map.get(op, op)

    new_left = left_int
    new_right = right_int

    if op == "lt":
        # x < y  =>  x <= y.hi - 1,  y >= x.lo + 1
        if right_int.hi is not None:
            new_left = new_left.intersect(Interval(None, right_int.hi - 1))
        if left_int.lo is not None:
            new_right = new_right.intersect(Interval(left_int.lo + 1, None))

    elif op == "le":
        # x <= y  =>  x <= y.hi,  y >= x.lo
        if right_int.hi is not None:
            new_left = new_left.intersect(Interval(None, right_int.hi))
        if left_int.lo is not None:
            new_right = new_right.intersect(Interval(left_int.lo, None))

    elif op == "gt":
        # x > y  =>  x >= y.lo + 1,  y <= x.hi - 1
        if right_int.lo is not None:
            new_left = new_left.intersect(Interval(right_int.lo + 1, None))
        if left_int.hi is not None:
            new_right = new_right.intersect(Interval(None, left_int.hi - 1))

    elif op == "ge":
        # x >= y  =>  x >= y.lo,  y <= x.hi
        if right_int.lo is not None:
            new_left = new_left.intersect(Interval(right_int.lo, None))
        if left_int.hi is not None:
            new_right = new_right.intersect(Interval(None, left_int.hi))

    elif op == "eq":
        # x == y  =>  x in x ∩ y,  y in x ∩ y
        common = left_int.intersect(right_int)
        new_left = common
        new_right = common

    elif op == "ne":
        # x != y: refine if one operand is a known singleton
        if right_int.lo is not None and right_int.lo == right_int.hi:
            c = right_int.lo
            if new_left.lo == c:
                new_left = new_left.intersect(Interval(c + 1, None))
            elif new_left.hi == c:
                new_left = new_left.intersect(Interval(None, c - 1))
        elif left_int.lo is not None and left_int.lo == left_int.hi:
            c = left_int.lo
            if new_right.lo == c:
                new_right = new_right.intersect(Interval(c + 1, None))
            elif new_right.hi == c:
                new_right = new_right.intersect(Interval(None, c - 1))

    # If any operand becomes empty, the entire branch is unreachable
    if new_left.is_bottom or new_right.is_bottom:
        return {k: BOTTOM for k in res}

    if left_key is not None:
        res[left_key] = new_left
    if right_key is not None:
        res[right_key] = new_right

    return res


def analyze_ranges(module: IRModule, config: CompilerConfig) -> RangeResult:
    """Run range analysis over all functions in the module."""
    all_by_op: dict[str, OpRangeInfo] = {}
    all_assumptions: list[tuple[str, Interval]] = []
    total_iterations = 0
    all_converged = True

    target = config.target
    overflow_policy = target.overflow_policy

    for func in module.functions:
        fn_res = _analyze_function_ranges(func, config)
        all_by_op.update(fn_res.by_op)
        all_assumptions.extend(fn_res.assumptions)
        total_iterations += fn_res.iterations
        if not fn_res.converged:
            all_converged = False

    return RangeResult(
        by_op=all_by_op,
        assumptions=all_assumptions,
        converged=all_converged,
        iterations=total_iterations,
    )


def _analyze_function_ranges(func: IRFunction, config: CompilerConfig) -> RangeResult:
    target = config.target
    overflow_policy = target.overflow_policy
    cfg = CFG(func)

    if not cfg.blocks:
        return RangeResult()

    # Track definition instructions for temps (especially CMP)
    temp_defs: dict[str, Instruction] = {}
    for instr in func.body:
        if instr.dst is not None and isinstance(instr.dst, TempRef):
            temp_defs[instr.dst.temp_id] = instr

    # Initial entry state
    entry_state: State = {}
    for p in func.params:
        t_min, t_max = _type_bounds(p.type, target)
        entry_state[_op_key(p)] = Interval(t_min, t_max)

    # Assumed ranges tracking
    assumptions: list[tuple[str, Interval]] = []

    # Map block_id -> in_state, out_state
    in_states: dict[int, State] = {cfg.entry.block_id: entry_state}
    out_states: dict[int, State] = {}
    edge_out_states: dict[tuple[int, int], State] = {}

    # Worklist using RPO
    rpo = cfg.reverse_post_order()
    worklist: list[BasicBlock] = list(rpo)
    in_worklist: set[int] = {b.block_id for b in worklist}

    iterations = 0
    max_iterations = max(50, len(cfg.blocks) * 10)

    by_op: dict[str, OpRangeInfo] = {}

    while worklist and iterations < max_iterations:
        iterations += 1
        bb = worklist.pop(0)
        in_worklist.discard(bb.block_id)

        # 1. Compute in_state
        if bb == cfg.entry:
            cur_in = dict(entry_state)
            if cfg.entry.block_id in in_states:
                # Merge if loops back to entry (rare)
                cur_in = _join_states(in_states[cfg.entry.block_id], entry_state)
        else:
            merged: State | None = None
            for pred in bb.predecessors:
                edge_state = edge_out_states.get((pred.block_id, bb.block_id))
                if edge_state is not None:
                    merged = _join_states(merged, edge_state)
            cur_in = merged if merged is not None else {}

        # If bb is a loop head, apply widening to type bounds
        if bb.is_loop_head and bb.block_id in in_states:
            prev_in = in_states[bb.block_id]
            widened: State = {}
            for k, cur_val in cur_in.items():
                prev_val = prev_in.get(k, BOTTOM)
                # Look up variable type bounds if known
                var_t = IRType.I64 if "i64" in k else IRType.I32
                t_min, t_max = _type_bounds(var_t, target)
                widened[k] = prev_val.widen_to_type_bounds(cur_val, t_min, t_max)
            cur_in = widened

        in_states[bb.block_id] = cur_in

        # 2. Execute block instructions sequentially
        state = dict(cur_in)

        def get_op_range(op: Operand) -> Interval:
            if isinstance(op, Const):
                return Interval(op.value, op.value)
            key = _op_key(op)
            if key in state:
                return state[key]
            op_t = getattr(op, "type", IRType.I32)
            t_min, t_max = _type_bounds(op_t, target)
            return Interval(t_min, t_max)

        for instr in bb.instructions:
            opcode = instr.opcode

            if opcode == Opcode.DECLARE:
                var = instr.dst or instr.operands[0]
                var_t = getattr(var, "type", IRType.I32)
                t_min, t_max = _type_bounds(var_t, target)
                # Before assignment, range is type bounds
                state[_op_key(var)] = Interval(t_min, t_max)

            elif opcode == Opcode.ASSIGN:
                src = instr.operands[0]
                src_range = get_op_range(src)
                if instr.dst:
                    state[_op_key(instr.dst)] = src_range

            elif opcode == Opcode.READ:
                var = instr.dst or instr.operands[0]
                var_name = var.ir_name if isinstance(var, VarRef) else str(var)
                # Check for assumed range: "function.var"
                assumed_key = f"{func.name}.{var_name}"
                if assumed_key in config.assumed_ranges:
                    assumed_int = config.assumed_ranges[assumed_key]
                    state[_op_key(var)] = assumed_int
                    if (assumed_key, assumed_int) not in assumptions:
                        assumptions.append((assumed_key, assumed_int))
                else:
                    var_t = getattr(var, "type", IRType.I32)
                    t_min, t_max = _type_bounds(var_t, target)
                    state[_op_key(var)] = Interval(t_min, t_max)

            elif opcode == Opcode.CALL:
                if instr.dst:
                    dst_t = getattr(instr.dst, "type", IRType.I32)
                    t_min, t_max = _type_bounds(dst_t, target)
                    state[_op_key(instr.dst)] = Interval(t_min, t_max)

            elif opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD, Opcode.NEG, Opcode.CAST):
                operand_ranges: tuple[Interval, ...] = tuple(get_op_range(op) for op in instr.operands)
                exact_res = Interval(None, None)

                if opcode == Opcode.ADD:
                    exact_res = add(operand_ranges[0], operand_ranges[1])
                elif opcode == Opcode.SUB:
                    exact_res = sub(operand_ranges[0], operand_ranges[1])
                elif opcode == Opcode.MUL:
                    exact_res = mul(operand_ranges[0], operand_ranges[1])
                elif opcode == Opcode.DIV:
                    exact_res = div(operand_ranges[0], operand_ranges[1])
                elif opcode == Opcode.MOD:
                    exact_res = mod(operand_ranges[0], operand_ranges[1])
                elif opcode == Opcode.NEG:
                    exact_res = neg(operand_ranges[0])
                elif opcode == Opcode.CAST:
                    dst_t = instr.dst.type if instr.dst else IRType.I32
                    t_min, t_max = _type_bounds(dst_t, target)
                    exact_res = cast(operand_ranges[0], t_min, t_max)

                # Classify risks
                risks = classify_risks(instr, operand_ranges, exact_res, target)

                # Determine stored result range
                dst_t = instr.dst.type if instr.dst else IRType.I32
                t_min, t_max = _type_bounds(dst_t, target)
                t_range = Interval(t_min, t_max)

                if t_range.contains_interval(exact_res):
                    stored_res = exact_res
                else:
                    # Overflow occurred or possible
                    if overflow_policy == OverflowPolicy.ASSUME_NO_OVERFLOW:
                        stored_res = exact_res.intersect(t_range)
                    else:  # wrap or trap
                        stored_res = t_range

                if instr.dst:
                    state[_op_key(instr.dst)] = stored_res

                # Record by_op information
                by_op[instr.op_id] = OpRangeInfo(
                    op_id=instr.op_id,
                    opcode=opcode,
                    operand_ranges=operand_ranges,
                    exact_result_range=exact_res,
                    result_range=stored_res,
                    risks=risks,
                )

        out_states[bb.block_id] = state

        # 3. Propagate to edges with branch refinement
        for edge in bb.outgoing_edges:
            succ = edge.target
            edge_state = dict(state)

            if edge.kind in ("true", "false") and bb.instructions:
                last_instr = bb.instructions[-1]
                if last_instr.opcode == Opcode.BRANCH:
                    cond_op = last_instr.operands[0]
                    if isinstance(cond_op, TempRef) and cond_op.temp_id in temp_defs:
                        cmp_instr = temp_defs[cond_op.temp_id]
                        if cmp_instr.opcode == Opcode.CMP and len(cmp_instr.operands) == 2:
                            left_op, right_op = cmp_instr.operands[0], cmp_instr.operands[1]
                            l_key = _op_key(left_op) if not isinstance(left_op, Const) else None
                            r_key = _op_key(right_op) if not isinstance(right_op, Const) else None
                            l_int = get_op_range(left_op)
                            r_int = get_op_range(right_op)
                            is_true = (edge.kind == "true")
                            edge_state = _refine_comparison(
                                cmp_op=cmp_instr.cmp_op or "eq",
                                left_key=l_key,
                                right_key=r_key,
                                left_int=l_int,
                                right_int=r_int,
                                state=state,
                                is_true_branch=is_true,
                            )

            old_edge_state = edge_out_states.get((bb.block_id, succ.block_id))
            if not _states_equal(old_edge_state, edge_state):
                edge_out_states[(bb.block_id, succ.block_id)] = edge_state
                if succ.block_id not in in_worklist:
                    worklist.append(succ)
                    in_worklist.add(succ.block_id)

    converged = (iterations < max_iterations)

    return RangeResult(
        by_op=by_op,
        assumptions=assumptions,
        converged=converged,
        iterations=iterations,
    )
