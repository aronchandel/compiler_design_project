"""Unit tests for cpp2py/ir/serialization.py.

Verifies AC7.2: IR snapshot JSON round-trips for all examples (printed text identical).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig
from cpp2py.ir.printer import format_module
from cpp2py.ir.serialization import (
    module_from_json,
    module_to_json,
    instruction_from_json,
    instruction_to_json,
    operand_from_json,
    operand_to_json,
)
from cpp2py.ir.model import (
    Const,
    IRFunction,
    IRModule,
    IRType,
    Instruction,
    LabelRef,
    Opcode,
    RegionInfo,
    StrConst,
    TempRef,
    VarRef,
)
from cpp2py.source import Pos, SourceSpan


def test_operand_roundtrip():
    operands = [
        Const(42, IRType.I32),
        Const(-100, IRType.I64),
        VarRef(symbol_id=1, ir_name="x", type=IRType.I32),
        VarRef(symbol_id=2, ir_name="count_1", type=IRType.I64),
        TempRef(temp_id="t0", type=IRType.I32),
        TempRef(temp_id="t5", type=IRType.BOOL),
        StrConst("Hello, world!\\n"),
        LabelRef("L_loop_body"),
    ]
    for op in operands:
        js = operand_to_json(op)
        res = operand_from_json(js)
        assert res == op, f"Failed round-trip for {op}: got {res}"


def test_instruction_roundtrip():
    span = SourceSpan("test.cpp", Pos(1, 2, 0), Pos(1, 10, 8))
    instr = Instruction(
        op_id="op_12",
        opcode=Opcode.CMP,
        dst=TempRef("t1", IRType.BOOL),
        operands=(VarRef(0, "a", IRType.I32), Const(10, IRType.I32)),
        span=span,
        origin=("op_10", "op_11"),
        cmp_op="lt",
    )
    js = instruction_to_json(instr)
    res = instruction_from_json(js)
    assert res.op_id == instr.op_id
    assert res.opcode == instr.opcode
    assert res.dst == instr.dst
    assert res.operands == instr.operands
    assert res.span == instr.span
    assert res.origin == instr.origin
    assert res.cmp_op == instr.cmp_op


def test_synthetic_module_roundtrip():
    fn = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction(op_id="op_0", opcode=Opcode.DECLARE, dst=VarRef(0, "x", IRType.I32), operands=(VarRef(0, "x", IRType.I32),)),
            Instruction(op_id="op_1", opcode=Opcode.ASSIGN, dst=VarRef(0, "x", IRType.I32), operands=(Const(5, IRType.I32),)),
            Instruction(op_id="op_2", opcode=Opcode.PRINT, operands=(VarRef(0, "x", IRType.I32),), newline=True),
            Instruction(op_id="op_3", opcode=Opcode.RETURN, operands=(Const(0, IRType.I32),)),
        ],
    )
    mod = IRModule([fn], source_name="synthetic.cpp")
    js = module_to_json(mod)
    reconstructed = module_from_json(js)
    assert format_module(reconstructed) == format_module(mod)


EXAMPLE_FILES = sorted([
    f for f in Path("examples").glob("**/*.cpp")
    if "errors" not in f.parts
], key=lambda p: str(p))


@pytest.mark.parametrize("cpp_file", EXAMPLE_FILES, ids=lambda p: f"{p.parent.name}_{p.stem}")
def test_roundtrip_example_cpp_file(cpp_file: Path) -> None:
    """Verify AC7.2: format_module(module_from_json(module_to_json(ir))) == format_module(ir) across all examples."""
    code = cpp_file.read_text(encoding="utf-8")
    res = compile_source(code, cpp_file.name, CompilerConfig())
    assert res.success, f"Compilation failed for {cpp_file}"
    assert res.ir is not None

    orig_text = format_module(res.ir)
    js = module_to_json(res.ir)
    js_text = json.dumps(js, indent=2, sort_keys=True)
    js_reloaded = json.loads(js_text)

    reconstructed_mod = module_from_json(js_reloaded)
    reconstructed_text = format_module(reconstructed_mod)

    assert reconstructed_text == orig_text, f"Text mismatch after JSON roundtrip for {cpp_file}!"
