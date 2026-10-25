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
from cpp2py.ir.serialization import module_to_json
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
        self._stage_idx: int = 0
        self._stages: list[dict[str, Any]] = []

    def save_initial_ir(self, module: IRModule) -> None:
        """Save the 00_ir_initial snapshot."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stage_name = f"{self._stage_idx:02d}_ir_initial"
        self._write_ir_stage(stage_name, module)
        self._stages.append({"name": stage_name, "changed": False})
        self._stage_idx += 1

    def save_pass_snapshot(self, pass_name: str, module: IRModule) -> None:
        """Save a snapshot after a pass that modified the IR."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stage_name = f"{self._stage_idx:02d}_after_{pass_name}"
        self._write_ir_stage(stage_name, module)
        self._stages.append({"name": stage_name, "changed": True})
        self._stage_idx += 1

    def save_final_ir(self, module: IRModule) -> None:
        """Save the NN_ir_final snapshot."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stage_name = f"{self._stage_idx:02d}_ir_final"
        self._write_ir_stage(stage_name, module)
        self._stages.append({"name": stage_name, "changed": False})
        self._stage_idx += 1

    def save_ranges_and_plan(self, ranges: Any, plan: Any) -> None:
        """Save ranges.json and plan.json."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        ranges_file = self.out_dir / "ranges.json"
        ranges_file.write_text(json.dumps(ranges.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        plan_file = self.out_dir / "plan.json"
        plan_file.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def save_output_and_manifest(
        self,
        source_text: str,
        python_source: str,
        config: CompilerConfig,
        diagnostics: tuple[Diagnostic, ...] = (),
    ) -> None:
        """Save the generated Python output and manifest.json."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        output_file = self.out_dir / "output.py"
        output_file.write_text(python_source, encoding="utf-8")

        sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        manifest = {
            "tool_version": cpp2py.__version__,
            "source_sha256": sha256,
            "config": {
                "int_bits": config.target.int_bits,
                "long_long_bits": config.target.long_long_bits,
                "overflow_policy": config.target.overflow_policy.value,
                "compat_mode": config.compat_mode.value,
            },
            "stages": self._stages,
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

    def save_phase2_snapshots(
        self,
        source_text: str,
        initial_ir: IRModule,
        final_ir: IRModule,
        python_source: str,
        config: CompilerConfig,
        diagnostics: tuple[Diagnostic, ...] = (),
    ) -> None:
        """Legacy helper for Phase 2 snapshot tests."""
        self.save_initial_ir(initial_ir)
        self.save_final_ir(final_ir)
        self.save_output_and_manifest(source_text, python_source, config, diagnostics)

    def _write_ir_stage(self, stage_name: str, module: IRModule) -> None:
        txt_file = self.out_dir / f"{stage_name}.ir.txt"
        txt_file.write_text(format_module(module), encoding="utf-8")

        json_file = self.out_dir / f"{stage_name}.ir.json"
        json_data = _serialize_module(module)
        json_text = json.dumps(json_data, indent=2, sort_keys=True) + "\n"
        json_file.write_text(json_text, encoding="utf-8")


def _serialize_module(module: IRModule) -> dict[str, Any]:
    return module_to_json(module)
