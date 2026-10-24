"""Unit tests for dead temporary elimination pass (cpp2py/transforms/dead_temps.py)."""

import pytest
from cpp2py.config import CompilerConfig
from cpp2py.diagnostics import DiagnosticSink
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
from cpp2py.transforms.dead_temps import DeadTempsPass
from cpp2py.transforms.manager import IRRewriter, PassContext, _create_allocator_for_module
from cpp2py.transforms.log import TransformLog


def run_dead_temps(func: IRFunction) -> tuple[IRFunction, TransformLog]:
    sink = DiagnosticSink()
    log = TransformLog()
    mod = IRModule(functions=[func], source_name="test.cpp")
    allocator = _create_allocator_for_module(mod)
    rw = IRRewriter(log=log, allocator=allocator)
    rw.current_pass = "dead_temps"
    ctx = PassContext(config=CompilerConfig(), sink=sink)
    DeadTempsPass().run(func, rw, ctx)
    return func, log


@pytest.mark.parametrize(
    "op",
    [
        Opcode.ASSIGN,
        Opcode.ADD,
        Opcode.SUB,
        Opcode.MUL,
        Opcode.NEG,
        Opcode.CMP,
    ],
)
def test_dead_temp_deleted_for_allowed_opcodes(op):
    operands = (Const(1, IRType.I32),) if op in (Opcode.ASSIGN, Opcode.NEG) else (Const(1, IRType.I32), Const(2, IRType.I32))
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=op,
                dst=TempRef("t0", IRType.I32),
                operands=operands,
            )
        ],
    )
    _, log = run_dead_temps(func)
    assert len(func.body) == 0
    assert len(log.records) == 1
    assert log.records[0].kind == "DELETE"
    assert log.records[0].op_id == "op_1"
    assert log.records[0].after is None
    assert "t0 has no remaining uses" in log.records[0].reason


@pytest.mark.parametrize(
    "op",
    [
        Opcode.DIV,
        Opcode.MOD,
        Opcode.CALL,
        Opcode.READ,
    ],
)
def test_dead_temp_never_deleted_for_disallowed_opcodes(op):
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=op,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(10, IRType.I32), Const(2, IRType.I32)) if op in (Opcode.DIV, Opcode.MOD) else (),
            )
        ],
    )
    _, log = run_dead_temps(func)
    assert len(func.body) == 1
    assert len(log.records) == 0


def test_dead_temps_never_deletes_variable_writes():
    # Variable writes must NEVER be deleted even with 0 subsequent uses
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.ASSIGN,
                dst=VarRef(1, "a", IRType.I32),
                operands=(Const(42, IRType.I32),),
            )
        ],
    )
    _, log = run_dead_temps(func)
    assert len(func.body) == 1
    assert len(log.records) == 0


def test_temp_with_use_not_deleted():
    # t0 is used by op_2 -> NOT deleted
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
    _, log = run_dead_temps(func)
    assert len(func.body) == 2
    assert len(log.records) == 0


def test_dead_temps_idempotent():
    func = IRFunction(
        name="test",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(
                op_id="op_1",
                opcode=Opcode.ASSIGN,
                dst=TempRef("t0", IRType.I32),
                operands=(Const(1, IRType.I32),),
            ),
            Instruction(
                op_id="op_2",
                opcode=Opcode.ASSIGN,
                dst=TempRef("t1", IRType.I32),
                operands=(Const(2, IRType.I32),),
            ),
        ],
    )
    run_dead_temps(func)
    assert len(func.body) == 0
    # Second run does nothing
    _, log2 = run_dead_temps(func)
    assert len(log2.records) == 0
