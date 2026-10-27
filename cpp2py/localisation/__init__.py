from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cpp2py.config import TargetModel
from cpp2py.localisation.ranking import RankingWeights, Suspect, rank_operations
from cpp2py.localisation.replay import ReplayResult, normalise_output, replay_case_snapshots
from cpp2py.localisation.slicing import (
    compute_backward_slice,
    find_first_differing_line,
    find_output_trace_index,
)
from cpp2py.testing.cxx_runner import CxxBuildCache, compile_cxx, probe_cxx_capabilities, run_cxx
from cpp2py.testing.py_runner import run_python

DISCLAIMER: str = "Localisation is heuristic diagnosis, not guaranteed automatic diagnosis or repair."
DISCLAIMER_SENTENCE: str = DISCLAIMER

@dataclass
class LocalisationReport:
    case_dir: str
    stage_verdict: str
    first_divergent_stage: str | None
    first_divergent_pass: str | None
    suspects: list[Suspect]
    differing_line_index: int | None = None
    actual_line: str = ""
    expected_line: str = ""
    confidence: str = "heuristic"
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_dir": self.case_dir,
            "stage_verdict": self.stage_verdict,
            "first_divergent_stage": self.first_divergent_stage,
            "first_divergent_pass": self.first_divergent_pass,
            "confidence": self.confidence,
            "disclaimer": self.disclaimer,
            "differing_line": {
                "line_index": self.differing_line_index,
                "actual": self.actual_line,
                "expected": self.expected_line,
            },
            "suspects": [s.to_dict() for s in self.suspects],
        }

    def format_text(self) -> str:
        lines: list[str] = [
            "=" * 60,
            "Failure Localisation Report",
            "=" * 60,
            f"Case directory: {self.case_dir}",
            f"Stage verdict:  {self.stage_verdict}",
            f"First divergent stage: {self.first_divergent_stage or 'none'}",
            f"Confidence:     {self.confidence}",
            "-" * 60,
            f"Disclaimer: {self.disclaimer}",
            "-" * 60,
        ]

        if self.differing_line_index is not None:
            lines.append(f"First differing line #{self.differing_line_index}:")
            lines.append(f"  Actual:   {repr(self.actual_line)}")
            lines.append(f"  Expected: {repr(self.expected_line)}")
            lines.append("-" * 60)

        lines.append("Ranked Suspect Operations:")
        if not self.suspects:
            lines.append("  (No specific suspect operations identified)")
        else:
            for s in self.suspects:
                loc = f" ({s.span.file}:{s.span.start.line}:{s.span.start.col})" if s.span else ""
                lines.append(f"  #{s.rank} [{s.op_id}]{loc} - Score: {s.score}")
                for ev in s.evidence:
                    lines.append(f"      * {ev}")

        lines.append("=" * 60)
        return "\n".join(lines)

def localise(case_dir: str | Path, top_k: int = 5) -> LocalisationReport:
    path = Path(case_dir)
    case_id = path.name

    snap_dir = path / "snapshots" if (path / "snapshots").exists() else path

    stdin_file = path / "input.txt"
    if not stdin_file.exists():
        stdin_file = path / "stdin.txt"
    if not stdin_file.exists():
        curated_input = Path("tests/differential/cases") / case_id / "input.txt"
        if curated_input.exists():
            stdin_file = curated_input
    stdin_text = stdin_file.read_text(encoding="utf-8") if stdin_file.exists() else ""

    cxx_stdout: str = ""
    cxx_exit_code: int = 0

    cxx_out_file = path / "cxx_output.txt"
    meta_file = path / "meta.json"

    if cxx_out_file.exists():
        cxx_stdout = cxx_out_file.read_text(encoding="utf-8")
    elif meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if "cxx_result" in meta and meta["cxx_result"]:
                cxx_stdout = meta["cxx_result"].get("stdout", "")
                cxx_exit_code = meta["cxx_result"].get("exit_code", 0)
        except Exception:
            pass

    if not cxx_stdout and (path.parent.parent / "summary.json").exists():
        try:
            sum_data = json.loads((path.parent.parent / "summary.json").read_text(encoding="utf-8"))
            for m in sum_data.get("mismatches", []):
                if m.get("case_id") == case_id and m.get("cxx_result"):
                    cxx_stdout = m["cxx_result"].get("stdout", "")
                    cxx_exit_code = m["cxx_result"].get("exit_code", 0)
                    break
        except Exception:
            pass

    prog_file = path / "program.cpp"
    if not prog_file.exists():
        curated_prog = Path("tests/differential/cases") / case_id / "program.cpp"
        if curated_prog.exists():
            prog_file = curated_prog

    if not cxx_stdout and prog_file.exists():
        capabilities = probe_cxx_capabilities()
        if capabilities.available:
            build = compile_cxx(prog_file.read_text(encoding="utf-8"), compiler=capabilities.compiler)
            if build.success and build.binary_path:
                cxx_exec = run_cxx(build.binary_path, stdin_text=stdin_text)
                cxx_stdout = cxx_exec.stdout
                cxx_exit_code = cxx_exec.exit_code

    py_stdout: str = ""
    py_exit_code: int = 0
    py_file = snap_dir / "output.py"
    if not py_file.exists():
        py_file = path / "output.py"
    if py_file.exists():
        py_exec = run_python(py_file, stdin_text=stdin_text, is_file=True)
        py_stdout = py_exec.stdout
        py_exit_code = py_exec.exit_code

    plan_dict: dict[str, Any] | None = None
    plan_file = snap_dir / "plan.json"
    if plan_file.exists():
        try:
            plan_dict = json.loads(plan_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    replay_res: ReplayResult = replay_case_snapshots(
        snapshot_dir=snap_dir,
        stdin_text=stdin_text,
        cxx_stdout=cxx_stdout,
        cxx_exit_code=cxx_exit_code,
        py_stdout=py_stdout,
        py_exit_code=py_exit_code,
    )

    trace_stage_replay = None
    if replay_res.first_divergent_stage:
        for sr in replay_res.stage_replays:
            if sr.stage_name == replay_res.first_divergent_stage:
                trace_stage_replay = sr
                break
    if trace_stage_replay is None:
        trace_stage_replay = replay_res.final_stage_replay

    slice_ops: dict[str, int] = {}
    differing_line_idx: int | None = None
    act_line: str = ""
    exp_line: str = ""

    if trace_stage_replay and trace_stage_replay.trace:
        diff_text = py_stdout if replay_res.stage_verdict == "codegen_or_plan" else trace_stage_replay.stdout
        differing_line_idx, act_line, exp_line = find_first_differing_line(diff_text, cxx_stdout)

        out_idx = find_output_trace_index(trace_stage_replay.trace, differing_line_idx)
        if out_idx >= 0:
            slice_ops = compute_backward_slice(trace_stage_replay.trace, out_idx)

    op_spans: dict[str, Any] = {}
    op_opcodes: dict[str, str] = {}
    if trace_stage_replay:
        for f in trace_stage_replay.ir_module.functions:
            for instr in f.body:
                if instr.opcode:
                    op_opcodes[instr.op_id] = instr.opcode.value
                if instr.span:
                    op_spans[instr.op_id] = instr.span

    suspects = rank_operations(
        slice_ops=slice_ops,
        first_divergent_pass=replay_res.first_divergent_pass,
        ops_changed_by_first_pass=replay_res.changed_ops_in_pass,
        plan_dict=plan_dict,
        op_spans=op_spans,
        op_opcodes=op_opcodes,
        top_k=top_k,
    )

    return LocalisationReport(
        case_dir=str(case_dir),
        stage_verdict=replay_res.stage_verdict,
        first_divergent_stage=replay_res.first_divergent_stage,
        first_divergent_pass=replay_res.first_divergent_pass,
        suspects=suspects,
        differing_line_index=differing_line_idx,
        actual_line=act_line,
        expected_line=exp_line,
        confidence="heuristic",
        disclaimer=DISCLAIMER,
    )
