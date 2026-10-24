"""Unit tests for constant folding pass (cpp2py/transforms/constant_fold.py)."""

import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, TargetModel
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.ir.builder import build_ir
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.frontend.ast_nodes import reset_node_ids
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    TempRef,
    VarRef,
    IRType,
)
from cpp2py.transforms.constant_fold import ConstantFoldPass
from cpp2py.transforms.manager import IRRewriter, PassContext
from cpp2py.transforms.log import TransformLog


def run_fold(func: IRFunction, config: CompilerConfig | None = None) -> tuple[IRFunction, DiagnosticSink, TransformLog]:
    """Helper to run ConstantFoldPass on an IRFunction."""
    if config is None:
        config = CompilerConfig()
    sink = DiagnosticSink()
    log = TransformLog()
    from cpp2py.transforms.manager import _create_allocator_for_module
    mod = IRModule(functions=[func], source_name="test.cpp")
    allocator = _create_allocator_for_module(mod)
    rw = IRRewriter(log=log, allocator=allocator)
    rw.current_pass = "constant_fold"
    ctx = PassContext(config=config, sink=sink)
    ConstantFoldPass().run(func, rw, ctx)
    return func, sink, log


# ---------------------------------------------------------------------------
# Folding Table Tests (>= 25 cases)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a, op, b, expected_val",
    [
        (6, Opcode.MUL, 7, 42),
        (-7, Opcode.DIV, 2, -3),
        (7, Opcode.DIV, -2, -3),
        (-7, Opcode.DIV, -2, 3),
        (-7, Opcode.MOD, 2, -1),
        (7, Opcode.MOD, -2, 1),
        (-7, Opcode.MOD, -2, -1),
        (0, Opcode.DIV, 5, 0),
        (0, Opcode.MOD, 5, 0),
        (100, Opcode.SUB, 35, 65),
        (123, Opcode.ADD, 456, 579),
        (-6, Opcode.MUL, 7, -42),
        (-6, Opcode.MUL, -7, 42),
        (0, Opcode.MUL, 999, 0),
        (15, Opcode.DIV, 4, 3),
        (15, Opcode.MOD, 4, 3),
        (-15, Opcode.DIV, 4, -3),
        (-15, Opcode.MOD, 4, -3),
        (10, Opcode.SUB, 10, 0),
        (5, Opcode.SUB, 10, -5),
        (-2147483647, Opcode.SUB, 1, -2147483648),  # INT_MIN boundary
        (-2147483648, Opcode.ADD, 0, -2147483648),
        (2147483646, Opcode.ADD, 1, 2147483647),   # INT_MAX boundary
    ],
)
def test_constant_fold_binops(a, op, b, expected_val):
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=op,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(a, IRType.I32), Const(b, IRType.I32)),
            )
        ],
    )
    run_fold(func)
    assert len(func.body) == 1
    instr = func.body[0]
    assert instr.opcode == Opcode.ASSIGN
    assert len(instr.operands) == 1
    assert isinstance(instr.operands[0], Const)
    assert instr.operands[0].value == expected_val


@pytest.mark.parametrize(
    "val, expected_val",
    [
        (42, -42),
        (-42, 42),
        (0, 0),
        (2147483647, -2147483647),
    ],
)
def test_constant_fold_unop_neg(val, expected_val):
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.NEG,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(val, IRType.I32),),
            )
        ],
    )
    run_fold(func)
    assert len(func.body) == 1
    instr = func.body[0]
    assert instr.opcode == Opcode.ASSIGN
    assert isinstance(instr.operands[0], Const)
    assert instr.operands[0].value == expected_val


def test_constant_fold_add_overflow_skipped_w6004():
    # 2147483647 + 1 not folded + W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.ADD,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(2147483647, IRType.I32), Const(1, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    # Instruction is kept
    assert func.body[0].opcode == Opcode.ADD


def test_constant_fold_div_by_zero_skipped_w6004():
    # 1 / 0 not folded + W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.DIV,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(1, IRType.I32), Const(0, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.DIV


def test_constant_fold_mod_by_zero_skipped_w6004():
    # 1 % 0 not folded + W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.MOD,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(1, IRType.I32), Const(0, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.MOD


def test_constant_fold_mul_overflow_skipped_w6004():
    # mul overflow not folded + W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.MUL,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(2000000000, IRType.I32), Const(2, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.MUL


def test_constant_fold_sub_underflow_skipped_w6004():
    # INT_MIN - 1 not folded + W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.SUB,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(-2147483648, IRType.I32), Const(1, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.SUB


def test_constant_fold_neg_int_min_overflow_skipped_w6004():
    # -(-2147483648) = 2147483648 > INT_MAX -> W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.NEG,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(-2147483648, IRType.I32),),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.NEG


def test_constant_fold_div_int_min_neg1_overflow_w6004():
    # INT_MIN / -1 overflows 32-bit int -> W6004
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.DIV,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(-2147483648, IRType.I32), Const(-1, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.DIV


def test_constant_fold_target_model_16_bit():
    # TargetModel(int_bits=16) changes in-range decision:
    # 30000 + 10000 = 40000 > 32767 -> W6004 under 16-bit
    cfg16 = CompilerConfig(target=TargetModel(int_bits=16))
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.ADD,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(30000, IRType.I32), Const(10000, IRType.I32)),
            )
        ],
    )
    _, sink, _ = run_fold(func, cfg16)
    assert any(w.code == "W6004" for w in sink.warnings)
    assert func.body[0].opcode == Opcode.ADD

    # But 100 + 200 folds under 16-bit
    func2 = IRFunction(
        name="test2",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.ADD,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(100, IRType.I32), Const(200, IRType.I32)),
            )
        ],
    )
    run_fold(func2, cfg16)
    assert func2.body[0].opcode == Opcode.ASSIGN
    assert func2.body[0].operands[0].value == 300


def test_constant_fold_substitute_constant_temp():
    # t0 = assign 42; a = assign t0 -> a = assign 42 [derived from op_1]
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.ASSIGN,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(42, IRType.I32),),
            ),
            Instruction(
                op_id="op_2",
                opcode=Opcode.ASSIGN,
                dst=VarRef(1, "a", IRType.I32),
                operands=(TempRef("t0", IRType.I32),),
            ),
        ],
    )
    _, _, log = run_fold(func)
    assert func.body[1].operands[0] == Const(42, IRType.I32)
    assert func.body[1].origin == ("op_1",)
    assert any(r.kind == "REPLACE" and r.op_id == "op_2" and r.derived_from == ["op_1"] for r in log.records)


def test_constant_fold_never_touches_cmp_branch_control_flow():
    # cmp lt 1, 2 is NEVER folded
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.CMP,
                dst=TempRef("t0", IRType.BOOL),
                operands=(Const(1, IRType.I32), Const(2, IRType.I32)),
                cmp_op="lt",
            ),
            Instruction(
                op_id="op_2",
                opcode=Opcode.BRANCH,
                operands=(TempRef("t0", IRType.BOOL),),
            ),
        ],
    )
    run_fold(func)
    assert func.body[0].opcode == Opcode.CMP
    assert func.body[1].opcode == Opcode.BRANCH
