import json
from pathlib import Path
import pytest
from cpp2py.source import SourceSpan, Pos
from cpp2py.ir.printer import format_module
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
from cpp2py.transforms.log import TransformRecord, TransformLog

def test_transform_record_to_from_dict():
    span = SourceSpan("test.cpp", Pos(5, 13, 100), Pos(5, 18, 105))
    rec = TransformRecord(
        seq=1,
        pass_name="constant_fold",
        op_id="op_1",
        kind="REPLACE",
        before="t0 = mul 6, 7",
        after="t0 = assign 42",
        span=span,
        reason="both operands constant; 6*7=42 within i32",
        derived_from=["op_0"],
    )

    d = rec.to_dict()
    assert d["seq"] == 1
    assert d["pass"] == "constant_fold"
    assert d["pass_name"] == "constant_fold"
    assert d["op_id"] == "op_1"
    assert d["kind"] == "REPLACE"
    assert d["before"] == "t0 = mul 6, 7"
    assert d["after"] == "t0 = assign 42"
    assert d["line"] == 5
    assert d["reason"] == "both operands constant; 6*7=42 within i32"
    assert d["derived_from"] == ["op_0"]

    rec2 = TransformRecord.from_dict(d)
    assert rec2.seq == rec.seq
    assert rec2.pass_name == rec.pass_name
    assert rec2.op_id == rec.op_id
    assert rec2.kind == rec.kind
    assert rec2.before == rec.before
    assert rec2.after == rec.after
    assert rec2.reason == rec.reason
    assert rec2.derived_from == rec.derived_from
    assert rec2.line == 5
    assert rec2.span is not None
    assert rec2.span.file == "test.cpp"
    assert rec2.span.start.line == 5

def test_transform_log_jsonl_roundtrip(tmp_path):
    log_file = tmp_path / "transforms.jsonl"
    log = TransformLog()
    log.add_record(
        pass_name="constant_fold",
        op_id="op_1",
        kind="REPLACE",
        before="t0 = mul 6, 7",
        after="t0 = assign 42",
        span=None,
        reason="both operands constant; 6*7=42 within i32",
        derived_from=[],
    )
    log.add_record(
        pass_name="dead_temps",
        op_id="op_1",
        kind="DELETE",
        before="t0 = assign 42",
        after=None,
        span=None,
        reason="t0 has no remaining uses",
        derived_from=[],
    )

    log.write_jsonl(log_file)
    assert log_file.exists()

    log2 = TransformLog.read_jsonl(log_file)
    assert len(log2.records) == 2
    assert log2.records[0].seq == 1
    assert log2.records[0].kind == "REPLACE"
    assert log2.records[0].after == "t0 = assign 42"
    assert log2.records[1].seq == 2
    assert log2.records[1].kind == "DELETE"
    assert log2.records[1].after is None

def test_transform_log_replay_matches_final_ir():

    initial_module = IRModule(
        functions=[
            IRFunction(
                name="main",
                params=(),
                return_type=IRType.I32,
                body=[
                    Instruction(
                        op_id="op_1",
                        opcode=Opcode.MUL,
                        dst=TempRef("t0", IRType.I32),
                        operands=(Const(6, IRType.I32), Const(7, IRType.I32)),
                    ),
                    Instruction(
                        op_id="op_2",
                        opcode=Opcode.ASSIGN,
                        dst=VarRef(1, "a", IRType.I32),
                        operands=(TempRef("t0", IRType.I32),),
                    ),
                ],
            )
        ],
        source_name="test.cpp",
    )

    log = TransformLog()
    log.add_record(
        pass_name="constant_fold",
        op_id="op_1",
        kind="REPLACE",
        before="t0 = mul 6, 7",
        after="t0 = assign 42",
        span=None,
        reason="6*7=42",
        derived_from=[],
    )
    log.add_record(
        pass_name="constant_fold",
        op_id="op_2",
        kind="REPLACE",
        before="a = assign t0",
        after="a = assign 42",
        span=None,
        reason="substitute t0",
        derived_from=["op_1"],
    )
    log.add_record(
        pass_name="dead_temps",
        op_id="op_1",
        kind="DELETE",
        before="t0 = assign 42",
        after=None,
        span=None,
        reason="dead",
        derived_from=[],
    )

    replayed = log.replay(initial_module)
    assert len(replayed.functions[0].body) == 1
    final_instr = replayed.functions[0].body[0]
    assert final_instr.op_id == "op_2"
    assert final_instr.opcode == Opcode.ASSIGN
    assert final_instr.dst == VarRef(1, "a", IRType.I32)
    assert final_instr.operands == (Const(42, IRType.I32),)
    assert final_instr.origin == ("op_1",)

def test_transform_log_determinism(tmp_path):
    p1 = tmp_path / "log1.jsonl"
    p2 = tmp_path / "log2.jsonl"

    for p in (p1, p2):
        log = TransformLog()
        log.add_record("constant_fold", "op_1", "REPLACE", "t0 = mul 2, 3", "t0 = assign 6", None, "reason")
        log.add_record("dead_temps", "op_1", "DELETE", "t0 = assign 6", None, None, "dead")
        log.write_jsonl(p)

    assert p1.read_bytes() == p2.read_bytes()
