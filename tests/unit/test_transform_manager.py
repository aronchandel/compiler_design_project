"""Unit tests for transformation manager and IRRewriter (cpp2py/transforms/manager.py)."""

import pytest
from cpp2py.config import CompilerConfig
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.source import SourceSpan, Pos
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    TempRef,
    VarRef,
    IRType,
    IdAllocator,
)
from cpp2py.transforms.log import TransformLog
from cpp2py.transforms.manager import (
    IRRewriter,
    PassContext,
    run_pipeline,
    _create_allocator_for_module,
)
from cpp2py.transforms.constant_fold import ConstantFoldPass
from cpp2py.transforms.dead_temps import DeadTempsPass


def test_rewriter_replace_preserves_id_and_span():
    span = SourceSpan("test.cpp", Pos(5, 5, 50), Pos(5, 10, 55))
    instr = Instruction("op_42", Opcode.MUL, TempRef("t0"), (Const(2), Const(3)), span=span)
    func = IRFunction("main", (), IRType.I32, [instr])

    log = TransformLog()
    allocator = IdAllocator()
    rw = IRRewriter(log, allocator)
    rw.current_pass = "test_pass"

    new_instr = Instruction("will_be_overwritten", Opcode.ASSIGN, TempRef("t0"), (Const(6),))
    rw.replace(func, instr, new_instr, reason="test fold")

    assert len(func.body) == 1
    assert func.body[0].op_id == "op_42"
    assert func.body[0].span == span
    assert len(log.records) == 1
    assert log.records[0].kind == "REPLACE"
    assert log.records[0].op_id == "op_42"


def test_rewriter_delete_retires_id_and_leaves_tombstone():
    span = SourceSpan("test.cpp", Pos(5, 5, 50), Pos(5, 10, 55))
    instr = Instruction("op_10", Opcode.ASSIGN, TempRef("t0"), (Const(6),), span=span)
    func = IRFunction("main", (), IRType.I32, [instr])

    log = TransformLog()
    allocator = IdAllocator()
    rw = IRRewriter(log, allocator)
    rw.current_pass = "dead_temps"

    rw.delete(func, instr, reason="t0 unused")

    assert len(func.body) == 0
    assert len(log.records) == 1
    assert log.records[0].kind == "DELETE"
    assert log.records[0].op_id == "op_10"
    assert log.records[0].after is None
    assert log.records[0].span == span


def test_rewriter_insert_allocates_fresh_id_and_inherits_span():
    span = SourceSpan("test.cpp", Pos(5, 5, 50), Pos(5, 10, 55))
    anchor = Instruction("op_1", Opcode.RETURN, operands=(Const(0),), span=span)
    func = IRFunction("main", (), IRType.I32, [anchor])

    log = TransformLog()
    allocator = IdAllocator()
    allocator._op_counter = 100
    rw = IRRewriter(log, allocator)
    rw.current_pass = "insert_pass"

    new_ins = Instruction("", Opcode.ASSIGN, VarRef(1, "x"), (Const(42),))
    rw.insert_before(func, anchor, new_ins, reason="insert init")

    assert len(func.body) == 2
    assert func.body[0].op_id == "op_100"
    assert func.body[0].span == span
    assert func.body[1].op_id == "op_1"
    assert len(log.records) == 1
    assert log.records[0].kind == "INSERT"
    assert log.records[0].op_id == "op_100"


def test_run_pipeline_idempotent():
    # Running constant_fold + dead_temps twice changes nothing on the second run
    module = IRModule(
        functions=[
            IRFunction(
                name="main",
                params=(),
                return_type=IRType.I32,
                body=[
                    Instruction("op_0", Opcode.DECLARE, operands=(VarRef(1, "a"),)),
                    Instruction("op_1", Opcode.MUL, TempRef("t0"), (Const(6), Const(7))),
                    Instruction("op_2", Opcode.ASSIGN, VarRef(1, "a"), (TempRef("t0"),)),
                    Instruction("op_3", Opcode.RETURN, operands=(Const(0),)),
                ],
            )
        ],
        source_name="test.cpp",
    )
    passes = [ConstantFoldPass(), DeadTempsPass()]
    sink = DiagnosticSink()
    config = CompilerConfig()

    log1 = run_pipeline(module, passes, config, sink)
    assert not sink.has_errors()
    recs_count_run1 = len(log1.records)
    assert recs_count_run1 > 0

    # Second run on the already folded module
    sink2 = DiagnosticSink()
    log2 = run_pipeline(module, passes, config, sink2)
    assert not sink2.has_errors()
    assert len(log2.records) == 0


def test_run_pipeline_catches_invalid_pass_with_e5001():
    # AC4.6: A deliberately invalid pass is rejected with E5001 naming the pass
    class BrokenPass:
        name = "bad_pass_broken_branch"

        def run(self, func: IRFunction, rw: IRRewriter, ctx: PassContext) -> None:
            # Introduce a branch pointing to a non-existent label, violating invariant (5)
            rw.current_pass = self.name
            broken_branch = Instruction(
                op_id="op_broken",
                opcode=Opcode.BRANCH,
                operands=(Const(1), Const(2)),
            )
            func.body.append(broken_branch)
            rw.pass_changed = True

    module = IRModule(
        functions=[
            IRFunction(
                name="main",
                params=(),
                return_type=IRType.I32,
                body=[Instruction("op_0", Opcode.RETURN, operands=(Const(0),))],
            )
        ],
        source_name="test.cpp",
    )

    sink = DiagnosticSink()
    run_pipeline(module, [BrokenPass()], CompilerConfig(), sink)
    assert sink.has_errors()
    e5001 = [e for e in sink.errors if e.code == "E5001"]
    assert len(e5001) > 0
    assert any("bad_pass_broken_branch" in e.message for e in e5001)


def test_run_pipeline_exceeding_iteration_limit_emits_warning():
    # Dummy pass that always alternates a value, causing non-convergence
    class AlternatingPass:
        name = "alternating_pass"

        def run(self, func: IRFunction, rw: IRRewriter, ctx: PassContext) -> None:
            instr = func.body[1]
            val = instr.operands[0].value
            new_val = val + 1 if val % 2 == 0 else val - 1
            new_instr = Instruction(instr.op_id, Opcode.ASSIGN, VarRef(1, "x"), (Const(new_val),))
            rw.replace(func, instr, new_instr, reason="alternate")

    module = IRModule(
        functions=[
            IRFunction(
                name="main",
                params=(),
                return_type=IRType.I32,
                body=[
                    Instruction("op_0", Opcode.DECLARE, operands=(VarRef(1, "x"),)),
                    Instruction("op_1", Opcode.ASSIGN, VarRef(1, "x"), (Const(0),)),
                    Instruction("op_2", Opcode.RETURN, operands=(Const(0),)),
                ],
            )
        ],
        source_name="test.cpp",
    )

    sink = DiagnosticSink()
    run_pipeline(module, [AlternatingPass()], CompilerConfig(), sink, max_iterations=5)
    assert any(w.code == "W6007" for w in sink.warnings)
