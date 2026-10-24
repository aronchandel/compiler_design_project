"""Snapshot store for saving deterministic IR and compilation artifacts.

Conforms to ARCH §G.3.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cpp2py
from cpp2py.ir.printer import format_module
from cpp2py.ir.model import (
    IRModule,
    Instruction,
    Const,
    VarRef,
    TempRef,
    StrConst,
    LabelRef,
    Operand,
)

if TYPE_CHECKING:
    from cpp2py.config import CompilerConfig
    from cpp2py.diagnostics import Diagnostic


class SnapshotStore:
    """Manages saving intermediate compiler artifacts and snapshots."""

    def __init__(self, out_dir: str | Path) -> None:
        self.out_dir = Path(out_dir)

    def save_phase2_snapshots(
        self,
        source_text: str,
        initial_ir: IRModule,
        final_ir: IRModule,
        python_source: str,
        config: CompilerConfig,
        diagnostics: tuple[Diagnostic, ...] = (),
    ) -> None:
        """Write all Phase 2 snapshot files deterministically."""
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # 1. 00_ir_initial
        self._write_ir_stage("00_ir_initial", initial_ir)

        # 2. 01_ir_final
        self._write_ir_stage("01_ir_final", final_ir)

        # 3. output.py
        output_file = self.out_dir / "output.py"
        output_file.write_text(python_source, encoding="utf-8")

        # 4. manifest.json (timestamp-free!)
        sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

        manifest = {
            "tool_version": cpp2py.__version__,
            "source_sha256": sha256,
            "config": {
                "int_bits": config.target.int_bits,
            },
            "stages": [
                {"name": "00_ir_initial", "changed": False},
                {"name": "01_ir_final", "changed": False},
            ],
            "diagnostics": [
                {
                    "severity": d.severity.value,
                    "code": d.code,
                    "message": d.message,
                }
                for d in diagnostics
            ],
        }

        manifest_file = self.out_dir / "manifest.json"
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        manifest_file.write_text(manifest_text, encoding="utf-8")

    def _write_ir_stage(self, stage_name: str, module: IRModule) -> None:
        txt_file = self.out_dir / f"{stage_name}.ir.txt"
        txt_file.write_text(format_module(module), encoding="utf-8")

        json_file = self.out_dir / f"{stage_name}.ir.json"
        json_data = _serialize_module(module)
        json_text = json.dumps(json_data, indent=2, sort_keys=True) + "\n"
        json_file.write_text(json_text, encoding="utf-8")


def _serialize_module(module: IRModule) -> dict[str, Any]:
    return {
        "source_name": module.source_name,
        "functions": [_serialize_function(f) for f in module.functions],
    }


def _serialize_function(func: Any) -> dict[str, Any]:
    return {
        "name": func.name,
        "return_type": str(func.return_type),
        "params": [str(p) for p in func.params],
        "body": [_serialize_instruction(i) for i in func.body],
    }


def _serialize_instruction(instr: Instruction) -> dict[str, Any]:
    res: dict[str, Any] = {
        "op_id": instr.op_id,
        "opcode": instr.opcode.value,
        "dst": str(instr.dst) if instr.dst is not None else None,
        "operands": [_serialize_operand(op) for op in instr.operands],
    }
    if instr.span is not None:
        res["span"] = {
            "file": instr.span.file,
            "start": {"line": instr.span.start.line, "col": instr.span.start.col},
            "end": {"line": instr.span.end.line, "col": instr.span.end.col},
        }
    if instr.origin:
        res["origin"] = list(instr.origin)
    return res


def _serialize_operand(op: Operand) -> dict[str, Any]:
    if isinstance(op, Const):
        return {"kind": "const", "value": op.value, "type": str(op.type)}
    elif isinstance(op, VarRef):
        return {"kind": "var", "name": op.ir_name, "symbol_id": op.symbol_id, "type": str(op.type)}
    elif isinstance(op, TempRef):
        return {"kind": "temp", "temp_id": op.temp_id, "type": str(op.type)}
    elif isinstance(op, StrConst):
        return {"kind": "str", "text": op.text}
    elif isinstance(op, LabelRef):
        return {"kind": "label", "name": op.name}
    return {"kind": "unknown", "text": str(op)}
