from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import cpp2py.codegen.python_gen as pygen_mod
import cpp2py.compat.helpers as helpers_mod
import cpp2py.compat.policy as policy_mod
import cpp2py.ir.builder as builder_mod
import cpp2py.transforms.constant_fold as fold_mod
from cpp2py.frontend import ast_nodes as ast
from cpp2py.analysis.intervals import Interval
from cpp2py.analysis.risk import Risk
from cpp2py.compat.plan import CompatAction, CompatDecision
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.ir.model import Const, Instruction, IRType, Opcode, TempRef
from cpp2py.localisation import LocalisationReport, localise
from cpp2py.testing.cxx_runner import compile_cxx, probe_cxx_capabilities, run_cxx
from cpp2py.testing.py_runner import run_python

@dataclass(frozen=True)
class FaultDef:
    id: str
    name: str
    description: str
    expected_stage: str
    expected_suspect_opcode: str
    sample_program: str
    sample_input: str
    expected_cxx_output: str
    patch_manager: Callable[[], Iterator[None]]

@contextmanager
def patch_f01_floor_div() -> Iterator[None]:
    orig_run = fold_mod.ConstantFoldPass.run

    def faulty_run(self: Any, func: Any, rw: Any, ctx: Any) -> None:
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
                        reason = f"fault F01: {a_val}//{b_val}={faulty_res}"
            orig_replace(f, old, new, reason, derived_from)

        rw.replace = faulty_replace
        orig_run(self, func, rw, ctx)

    fold_mod.ConstantFoldPass.run = faulty_run
    try:
        yield
    finally:
        fold_mod.ConstantFoldPass.run = orig_run

@contextmanager
def patch_f02_mod_plan_native() -> Iterator[None]:
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
                reason="fault F02: mod picked native",
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
def patch_f03_generator_mod() -> Iterator[None]:
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
def patch_f04_builder_swap_sub() -> Iterator[None]:
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
def patch_f05_fold_mul_as_add() -> Iterator[None]:
    orig_run = fold_mod.ConstantFoldPass.run

    def faulty_run(self: Any, func: Any, rw: Any, ctx: Any) -> None:
        orig_replace = rw.replace

        def faulty_replace(f: Any, old: Any, new: Any, reason: str = "", derived_from: Any = ()) -> None:
            if derived_from is None:
                derived_from = ()
            if old.opcode == Opcode.MUL and len(old.operands) == 2:
                if isinstance(old.operands[0], Const) and isinstance(old.operands[1], Const):
                    a_val = old.operands[0].value
                    b_val = old.operands[1].value
                    faulty_res = a_val + b_val
                    res_type = new.operands[0].type if new.operands else IRType.I32
                    new.operands = (Const(faulty_res, res_type),)
                    reason = f"fault F05: {a_val}*{b_val}->{faulty_res}"
            orig_replace(f, old, new, reason, derived_from)

        rw.replace = faulty_replace
        orig_run(self, func, rw, ctx)

    fold_mod.ConstantFoldPass.run = faulty_run
    try:
        yield
    finally:
        fold_mod.ConstantFoldPass.run = orig_run

@contextmanager
def patch_f06_generator_div() -> Iterator[None]:
    orig_build = pygen_mod.IRToPythonGenerator._build_ast_for_instr

    def faulty_build(self: Any, instr: Any) -> Any:
        if instr.opcode == Opcode.DIV:
            dummy_span = instr.span
            left = self._build_ast_expr(instr.operands[0])
            right = self._build_ast_expr(instr.operands[1])
            return ast.BinaryExpr("/", left, right, dummy_span)
        return orig_build(self, instr)

    pygen_mod.IRToPythonGenerator._build_ast_for_instr = faulty_build
    try:
        yield
    finally:
        pygen_mod.IRToPythonGenerator._build_ast_for_instr = orig_build

@contextmanager
def patch_f07_builder_swap_div() -> Iterator[None]:
    orig_lower_expr = builder_mod.IRBuilder._lower_expr

    def faulty_lower_expr(self: Any, expr: Any) -> Any:
        if isinstance(expr, ast.BinaryExpr) and expr.op == "/":
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
                    opcode=Opcode.DIV,
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
def patch_f08_builder_swap_mod() -> Iterator[None]:
    orig_lower_expr = builder_mod.IRBuilder._lower_expr

    def faulty_lower_expr(self: Any, expr: Any) -> Any:
        if isinstance(expr, ast.BinaryExpr) and expr.op == "%":
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
                    opcode=Opcode.MOD,
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
def patch_f09_fold_sub_as_add() -> Iterator[None]:
    orig_run = fold_mod.ConstantFoldPass.run

    def faulty_run(self: Any, func: Any, rw: Any, ctx: Any) -> None:
        orig_replace = rw.replace

        def faulty_replace(f: Any, old: Any, new: Any, reason: str = "", derived_from: Any = ()) -> None:
            if derived_from is None:
                derived_from = ()
            if old.opcode == Opcode.SUB and len(old.operands) == 2:
                if isinstance(old.operands[0], Const) and isinstance(old.operands[1], Const):
                    a_val = old.operands[0].value
                    b_val = old.operands[1].value
                    faulty_res = a_val + b_val
                    res_type = new.operands[0].type if new.operands else IRType.I32
                    new.operands = (Const(faulty_res, res_type),)
                    reason = f"fault F09: {a_val}-{b_val}->{faulty_res}"
            orig_replace(f, old, new, reason, derived_from)

        rw.replace = faulty_replace
        orig_run(self, func, rw, ctx)

    fold_mod.ConstantFoldPass.run = faulty_run
    try:
        yield
    finally:
        fold_mod.ConstantFoldPass.run = orig_run

@contextmanager
def patch_f10_div_plan_native() -> Iterator[None]:
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
        if instr.opcode == Opcode.DIV:
            risks_set = set(dec.risks)
            risks_set.add(Risk.DIV_TRUNC_DIFFERS)
            return CompatDecision(
                op_id=dec.op_id,
                risks=risks_set,
                action=CompatAction.NATIVE,
                helper=None,
                reason="fault F10: div picked native",
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
def patch_f11_wrap_off_by_one() -> Iterator[None]:
    orig_wrap = helpers_mod._wrap_i32

    def faulty_wrap(x: int) -> int:
        return ((x + 0x7FFFFFFF) % 0x100000000) - 0x80000000

    helpers_mod._wrap_i32 = faulty_wrap
    try:
        yield
    finally:
        helpers_mod._wrap_i32 = orig_wrap

@contextmanager
def patch_f12_widening_error() -> Iterator[None]:
    orig_widen = Interval.widen_to_type_bounds

    def faulty_widen(self: Interval, other: Interval, type_min: int, type_max: int) -> Interval:
        res = orig_widen(self, other, type_min, type_max)
        if res.hi is not None and res.hi > 0:
            return Interval(res.lo, 0)
        return res

    Interval.widen_to_type_bounds = faulty_widen
    try:
        yield
    finally:
        Interval.widen_to_type_bounds = orig_widen

FAULTS: list[FaultDef] = [
    FaultDef(
        id="F01",
        name="constant_fold_floor_div",
        description="Constant folder folds division using floor division // instead of truncating division",
        expected_stage="after_constant_fold",
        expected_suspect_opcode="div",
        sample_program="""#include <iostream>
int main() {
    int x = -7 / 2;
    std::cout << x << std::endl;
    return 0;
}
""",
        sample_input="",
        expected_cxx_output="-3\n",
        patch_manager=patch_f01_floor_div,
    ),
    FaultDef(
        id="F02",
        name="mod_plan_native",
        description="Range transfer/policy for mod wrongly emits native modulo % on negative operand",
        expected_stage="codegen_or_plan",
        expected_suspect_opcode="mod",
        sample_program="""#include <iostream>
int main() {
    int a = 0;
    std::cin >> a;
    int r = a % 5;
    std::cout << r << std::endl;
    return 0;
}
""",
        sample_input="-12\n",
        expected_cxx_output="-2\n",
        patch_manager=patch_f02_mod_plan_native,
    ),
    FaultDef(
        id="F03",
        name="generator_drop_mod_helper",
        description="Code generator emits native % even when compatibility plan requests _cpp_mod",
        expected_stage="codegen_or_plan",
        expected_suspect_opcode="mod",
        sample_program="""#include <iostream>
int main() {
    int a = 0;
    std::cin >> a;
    int r = a % 3;
    std::cout << r << std::endl;
    return 0;
}
""",
        sample_input="-7\n",
        expected_cxx_output="-1\n",
        patch_manager=patch_f03_generator_mod,
    ),
    FaultDef(
        id="F04",
        name="builder_swap_sub",
        description="IR builder swaps operands in subtraction (a - b -> b - a)",
        expected_stage="ir_generation",
        expected_suspect_opcode="sub",
        sample_program="""#include <iostream>
int main() {
    int a = 0, b = 0;
    std::cin >> a >> b;
    int diff = a - b;
    std::cout << diff << std::endl;
    return 0;
}
""",
        sample_input="10 3\n",
        expected_cxx_output="7\n",
        patch_manager=patch_f04_builder_swap_sub,
    ),
    FaultDef(
        id="F05",
        name="constant_fold_mul_as_add",
        description="Constant folder folds multiplication as addition",
        expected_stage="after_constant_fold",
        expected_suspect_opcode="mul",
        sample_program="""#include <iostream>
int main() {
    int p = 6 * 7;
    std::cout << p << std::endl;
    return 0;
}
""",
        sample_input="",
        expected_cxx_output="42\n",
        patch_manager=patch_f05_fold_mul_as_add,
    ),
    FaultDef(
        id="F06",
        name="generator_drop_div_helper",
        description="Code generator emits native // even when compatibility plan requests _cpp_div",
        expected_stage="codegen_or_plan",
        expected_suspect_opcode="div",
        sample_program="""#include <iostream>
int main() {
    int a = 0;
    std::cin >> a;
    int q = a / 2;
    std::cout << q << std::endl;
    return 0;
}
""",
        sample_input="-7\n",
        expected_cxx_output="-3\n",
        patch_manager=patch_f06_generator_div,
    ),
    FaultDef(
        id="F07",
        name="builder_swap_div",
        description="IR builder swaps operands in division (a / b -> b / a)",
        expected_stage="ir_generation",
        expected_suspect_opcode="div",
        sample_program="""#include <iostream>
int main() {
    int a = 0, b = 0;
    std::cin >> a >> b;
    int q = a / b;
    std::cout << q << std::endl;
    return 0;
}
""",
        sample_input="20 4\n",
        expected_cxx_output="5\n",
        patch_manager=patch_f07_builder_swap_div,
    ),
    FaultDef(
        id="F08",
        name="builder_swap_mod",
        description="IR builder swaps operands in remainder (a % b -> b % a)",
        expected_stage="ir_generation",
        expected_suspect_opcode="mod",
        sample_program="""#include <iostream>
int main() {
    int a = 0, b = 0;
    std::cin >> a >> b;
    int r = a % b;
    std::cout << r << std::endl;
    return 0;
}
""",
        sample_input="25 7\n",
        expected_cxx_output="4\n",
        patch_manager=patch_f08_builder_swap_mod,
    ),
    FaultDef(
        id="F09",
        name="constant_fold_sub_as_add",
        description="Constant folder folds subtraction as addition",
        expected_stage="after_constant_fold",
        expected_suspect_opcode="sub",
        sample_program="""#include <iostream>
int main() {
    int diff = 100 - 30;
    std::cout << diff << std::endl;
    return 0;
}
""",
        sample_input="",
        expected_cxx_output="70\n",
        patch_manager=patch_f09_fold_sub_as_add,
    ),
    FaultDef(
        id="F10",
        name="div_plan_native",
        description="Range transfer/policy for div wrongly emits native // on negative operand",
        expected_stage="codegen_or_plan",
        expected_suspect_opcode="div",
        sample_program="""#include <iostream>
int main() {
    int a = 0;
    std::cin >> a;
    int q = a / 3;
    std::cout << q << std::endl;
    return 0;
}
""",
        sample_input="-10\n",
        expected_cxx_output="-3\n",
        patch_manager=patch_f10_div_plan_native,
    ),
]

def run_fault_evaluation(
    fault: FaultDef,
    base_dir: Path,
) -> dict[str, Any]:
    case_dir = base_dir / fault.id
    case_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = case_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    cxx_out = fault.expected_cxx_output

    caps = probe_cxx_capabilities()
    if caps.available:
        build_res = compile_cxx(fault.sample_program, build_dir=case_dir / "cxx_build")
        if build_res.success and build_res.binary_path:
            cxx_exec = run_cxx(build_res.binary_path, stdin_text=fault.sample_input)
            if not cxx_exec.timed_out:
                cxx_out = cxx_exec.stdout

    cfg = CompilerConfig(
        snapshot_dir=str(snap_dir),
        transform_log_path=str(snap_dir / "transform_log.jsonl"),
        fold_constants=True,
        compat_mode=CompatMode.RANGE_GUIDED,
    )

    with fault.patch_manager():
        comp_res = compile_source(fault.sample_program, f"{fault.id}.cpp", config=cfg)

    py_source = comp_res.python_source or ""

    (case_dir / "program.cpp").write_text(fault.sample_program, encoding="utf-8")
    (case_dir / "input.txt").write_text(fault.sample_input, encoding="utf-8")
    (case_dir / "cxx_output.txt").write_text(cxx_out, encoding="utf-8")
    (case_dir / "output.py").write_text(py_source, encoding="utf-8")

    meta = {
        "case_id": fault.id,
        "cxx_exit_code": 0,
        "category": "fault_injection",
        "has_ub": False,
    }
    (case_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    rep = localise(case_dir, top_k=5)

    rank: int | None = None
    for idx, suspect in enumerate(rep.suspects, start=1):
        if fault.expected_suspect_opcode in suspect.opcode.lower():
            rank = idx
            break

    top1 = (rank == 1)
    top3 = (rank is not None and 1 <= rank <= 3)
    reciprocal_rank = (1.0 / rank) if rank is not None else 0.0

    return {
        "id": fault.id,
        "name": fault.name,
        "expected_stage": fault.expected_stage,
        "diagnosed_stage": rep.stage_verdict,
        "stage_match": (fault.expected_stage in rep.stage_verdict),
        "expected_suspect": fault.expected_suspect_opcode,
        "rank": rank,
        "top1": top1,
        "top3": top3,
        "reciprocal_rank": round(reciprocal_rank, 4),
        "suspects": [s.to_dict() for s in rep.suspects],
    }
