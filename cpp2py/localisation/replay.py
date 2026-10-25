"""Snapshot replay and bisection against reference C++ execution.

Conforms to ARCH §G.4 and §I.2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cpp2py.config import OverflowPolicy, TargetModel
from cpp2py.ir.model import IRModule
from cpp2py.ir.serialization import module_from_json
from cpp2py.localisation.ir_interpreter import InterpretationResult, TraceEntry, interpret_module
from cpp2py.transforms.log import TransformLog


@dataclass
class StageReplay:
    """Replay outcome for a single IR snapshot stage."""
    stage_name: str
    pass_name: str | None
    agrees_with_cxx: bool
    stdout: str
    exit_code: int
    ir_module: IRModule
    trace: list[TraceEntry]
    ub_events: list[str] = field(default_factory=list)


@dataclass
class ReplayResult:
    """Outcome of replaying all snapshots of a case."""
    stage_verdict: str  # "ir_generation" | "after_<pass>" | "codegen_or_plan" | "none"
    first_divergent_stage: str | None
    first_divergent_pass: str | None
    changed_ops_in_pass: list[str]
    stage_replays: list[StageReplay]
    final_stage_replay: StageReplay | None


def normalise_output(text: str) -> str:
    """Normalise CRLF to LF and strip trailing whitespace on each line."""
    lines = text.replace("\r\n", "\n").splitlines()
    return "\n".join(lines).strip()


def replay_case_snapshots(
    snapshot_dir: str | Path,
    stdin_text: str = "",
    cxx_stdout: str = "",
    cxx_exit_code: int = 0,
    py_stdout: str | None = None,
    py_exit_code: int | None = None,
    target_model: TargetModel | None = None,
    overflow_policy: OverflowPolicy | str | None = None,
) -> ReplayResult:
    """Run reference IR interpreter across all snapshots in order, comparing with C++ output."""
    snap_path = Path(snapshot_dir)
    manifest_path = snap_path / "manifest.json"

    stages: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            stages = m_data.get("stages", [])
            if target_model is None and "config" in m_data:
                cfg = m_data["config"]
                target_model = TargetModel(
                    int_bits=cfg.get("int_bits", 32),
                    long_long_bits=cfg.get("long_long_bits", 64),
                )
            if overflow_policy is None and "config" in m_data:
                overflow_policy = m_data["config"].get("overflow_policy", "assume_no_overflow")
        except Exception:
            pass

    # If manifest not found or had no stages, scan directory for *.ir.json
    if not stages:
        json_files = sorted(list(snap_path.glob("*.ir.json")), key=lambda p: p.name)
        for jf in json_files:
            stage_name = jf.name[:-len(".ir.json")]
            stages.append({"name": stage_name, "changed": "after_" in stage_name})

    # Read transform log if present
    log_path = snap_path / "transform_log.jsonl"
    if not log_path.exists():
        log_path = snap_path.parent / "transform_log.jsonl"

    transform_log = TransformLog()
    if log_path.exists():
        try:
            transform_log = TransformLog.read_jsonl(log_path)
        except Exception:
            pass

    stage_replays: list[StageReplay] = []
    norm_cxx_stdout = normalise_output(cxx_stdout)

    for st in stages:
        st_name = st["name"]
        ir_file = snap_path / f"{st_name}.ir.json"
        if not ir_file.exists():
            continue

        try:
            mod_data = json.loads(ir_file.read_text(encoding="utf-8"))
            ir_mod = module_from_json(mod_data)
        except Exception:
            continue

        pass_name: str | None = None
        if "_after_" in st_name:
            pass_name = st_name.split("_after_", 1)[1]

        interp_res = interpret_module(
            module=ir_mod,
            stdin_text=stdin_text,
            target=target_model,
            overflow_policy=overflow_policy,
            record_trace=True,
        )

        norm_stdout = normalise_output(interp_res.stdout)
        agrees = (norm_stdout == norm_cxx_stdout) and (interp_res.exit_code == cxx_exit_code)

        stage_replays.append(
            StageReplay(
                stage_name=st_name,
                pass_name=pass_name,
                agrees_with_cxx=agrees,
                stdout=interp_res.stdout,
                exit_code=interp_res.exit_code,
                ir_module=ir_mod,
                trace=interp_res.trace,
                ub_events=interp_res.ub_events,
            )
        )

    # Determine verdict by finding first divergent stage
    stage_verdict = "none"
    first_div_stage: str | None = None
    first_div_pass: str | None = None
    changed_ops: list[str] = []

    for idx, sr in enumerate(stage_replays):
        if not sr.agrees_with_cxx:
            first_div_stage = sr.stage_name
            if idx == 0 or "initial" in sr.stage_name:
                stage_verdict = "ir_generation"
            elif sr.pass_name is not None:
                stage_verdict = f"after_{sr.pass_name}"
                first_div_pass = sr.pass_name
                # Find changed ops in this pass from transform_log
                changed_ops = [
                    r.op_id for r in transform_log.records if r.pass_name == sr.pass_name
                ]
                # If transform log had no records, compute diff with previous stage
                if not changed_ops and idx > 0:
                    prev_ops = {
                        i.op_id: (i.opcode, str(i.dst), tuple(str(o) for o in i.operands))
                        for f in stage_replays[idx - 1].ir_module.functions
                        for i in f.body
                    }
                    curr_ops = {
                        i.op_id: (i.opcode, str(i.dst), tuple(str(o) for o in i.operands))
                        for f in sr.ir_module.functions
                        for i in f.body
                    }
                    for op_id, sig in curr_ops.items():
                        if op_id not in prev_ops or prev_ops[op_id] != sig:
                            changed_ops.append(op_id)
            else:
                stage_verdict = "codegen_or_plan"
            break

    # If all IR stages agreed with C++, but Python output differed from C++:
    if first_div_stage is None:
        if py_stdout is not None:
            norm_py_stdout = normalise_output(py_stdout)
            if norm_py_stdout != norm_cxx_stdout or (py_exit_code is not None and py_exit_code != cxx_exit_code):
                stage_verdict = "codegen_or_plan"
                first_div_stage = "codegen_or_plan"

    final_sr = stage_replays[-1] if stage_replays else None

    return ReplayResult(
        stage_verdict=stage_verdict,
        first_divergent_stage=first_div_stage,
        first_divergent_pass=first_div_pass,
        changed_ops_in_pass=changed_ops,
        stage_replays=stage_replays,
        final_stage_replay=final_sr,
    )
