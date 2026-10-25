"""Differential testing orchestration and summary reporting."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cpp2py
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.testing.comparator import (
    DiffResult,
    Outcome,
    compare_results,
    compute_agreement_rate,
)
from cpp2py.testing.corpus import TestCase, load_curated_cases, load_example_cases
from cpp2py.testing.cxx_runner import (
    CxxBuildCache,
    CxxCapabilities,
    ExecutionResult,
    compile_cxx,
    compile_cxx_ubsan,
    probe_cxx_capabilities,
    run_cxx,
)
from cpp2py.testing.py_runner import run_python
from cpp2py.testing.regression import save_regression_case
from cpp2py.testing.testgen.programs import GENERATOR_VERSION, generate_suite


@dataclass
class DiffSummary:
    """Summary of a differential testing run."""
    suite: str
    total_runs: int
    counts: dict[Outcome, int]
    agreement_rate: float | None
    numerator: int
    denominator: int
    results: list[DiffResult]
    capabilities: CxxCapabilities
    config: dict[str, Any]
    generator_version: str = GENERATOR_VERSION
    seed: int | None = None

    def has_mismatches(self) -> bool:
        return any(r.is_mismatch() for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": cpp2py.__version__,
            "python_version": sys.version,
            "generator_version": self.generator_version,
            "suite": self.suite,
            "seed": self.seed,
            "capabilities": self.capabilities.to_dict(),
            "config": self.config,
            "total_runs": self.total_runs,
            "counts": {k.value: v for k, v in self.counts.items()},
            "agreement_rate": {
                "rate": self.agreement_rate,
                "numerator": self.numerator,
                "denominator": self.denominator,
            },
            "excluded_counts": {
                Outcome.UB_EXCLUDED.value: self.counts.get(Outcome.UB_EXCLUDED, 0),
                Outcome.TRANSLATE_REJECTED.value: self.counts.get(Outcome.TRANSLATE_REJECTED, 0),
                Outcome.CPP_COMPILE_ERROR.value: self.counts.get(Outcome.CPP_COMPILE_ERROR, 0),
                Outcome.BOTH_FAILED_AGREE.value: self.counts.get(Outcome.BOTH_FAILED_AGREE, 0),
                Outcome.SKIPPED.value: self.counts.get(Outcome.SKIPPED, 0),
            },
            "mismatches": [r.to_dict() for r in self.results if r.is_mismatch()],
        }

    def print_summary(self) -> None:
        """Print human-readable summary table to stdout."""
        print("=" * 60)
        print(f"Differential Testing Summary (Suite: {self.suite})")
        print("=" * 60)
        print(f"Compiler: {self.capabilities.compiler} ({self.capabilities.version or 'not available'})")
        print(f"Sanitizer available: {self.capabilities.sanitizer_available}")
        print(f"Total test executions: {self.total_runs}")
        print("-" * 60)
        print("Outcome counts:")
        for outcome in Outcome:
            cnt = self.counts.get(outcome, 0)
            if cnt > 0:
                print(f"  {outcome.value:<28} : {cnt:>5}")
        print("-" * 60)
        if self.denominator > 0 and self.agreement_rate is not None:
            pct = self.agreement_rate * 100.0
            print(f"Agreement Rate: {self.numerator}/{self.denominator} ({pct:.2f}%)")
        else:
            print("Agreement Rate: N/A (no comparable cases)")

        excluded_total = (
            self.counts.get(Outcome.UB_EXCLUDED, 0)
            + self.counts.get(Outcome.TRANSLATE_REJECTED, 0)
            + self.counts.get(Outcome.CPP_COMPILE_ERROR, 0)
            + self.counts.get(Outcome.BOTH_FAILED_AGREE, 0)
            + self.counts.get(Outcome.SKIPPED, 0)
        )
        print(f"Excluded from denominator: {excluded_total}")
        print("=" * 60)


def run_case(
    case: TestCase,
    config: CompilerConfig,
    capabilities: CxxCapabilities,
    cache: CxxBuildCache | None = None,
    timeout: float = 5.0,
    output_cap: int = 1048576,
    out_dir: Path | None = None,
) -> list[DiffResult]:
    """Run differential testing on a single TestCase across all its inputs."""
    results: list[DiffResult] = []

    # Check compiler availability
    if not capabilities.available:
        for idx, _ in enumerate(case.inputs):
            cid = f"{case.case_id}[{idx}]"
            res = compare_results(
                case_id=cid,
                skipped=True,
                skip_reason=capabilities.reason or "C++ compiler not available",
            )
            results.append(res)
        return results

    # Compile C++ program
    overflow_pol = config.target.overflow_policy.value
    cxx_build = compile_cxx(
        source_code=case.program_source,
        overflow_policy=overflow_pol,
        cache=cache,
        compiler=capabilities.compiler,
    )

    if not cxx_build.success:
        for idx, _ in enumerate(case.inputs):
            cid = f"{case.case_id}[{idx}]"
            res = compare_results(
                case_id=cid,
                cxx_compile_success=False,
                cxx_compile_error=cxx_build.compile_error,
            )
            results.append(res)
        return results

    # Optional UBSan build
    ubsan_build = None
    if capabilities.sanitizer_available:
        ubsan_build = compile_cxx_ubsan(
            source_code=case.program_source,
            overflow_policy=overflow_pol,
            cache=cache,
            compiler=capabilities.compiler,
        )

    # Translate with cpp2py
    trans_res = compile_source(
        text=case.program_source,
        filename=f"{case.case_id}.cpp",
        config=config,
    )

    if not trans_res.success:
        diags = [f"{d.code}: {d.message}" for d in trans_res.diagnostics]
        for idx, _ in enumerate(case.inputs):
            cid = f"{case.case_id}[{idx}]"
            res = compare_results(
                case_id=cid,
                translate_success=False,
                translate_diagnostics=diags,
            )
            results.append(res)
        return results

    py_source = trans_res.python_source or ""

    # Execute both on each input
    for idx, in_text in enumerate(case.inputs):
        cid = f"{case.case_id}[{idx}]" if len(case.inputs) > 1 else case.case_id

        cxx_exec = run_cxx(
            binary_path=cxx_build.binary_path,  # type: ignore
            stdin_text=in_text,
            timeout=timeout,
            output_cap=output_cap,
        )

        ubsan_exec = None
        if ubsan_build and ubsan_build.success and ubsan_build.binary_path:
            ubsan_exec = run_cxx(
                binary_path=ubsan_build.binary_path,
                stdin_text=in_text,
                timeout=timeout,
                output_cap=output_cap,
            )

        py_exec = run_python(
            source_or_file=py_source,
            stdin_text=in_text,
            timeout=timeout,
            output_cap=output_cap,
            is_file=False,
        )

        diff_res = compare_results(
            case_id=cid,
            cxx_result=cxx_exec,
            py_result=py_exec,
            ubsan_result=ubsan_exec,
            translate_success=True,
            cxx_compile_success=True,
            overflow_policy=overflow_pol,
        )

        # On mismatch, capture snapshots and persist regression case
        if diff_res.is_mismatch():
            snap_dir = None
            if out_dir is not None:
                case_dir = out_dir / "failures" / cid
                snap_dir = case_dir / "snapshots"
                snap_dir.mkdir(parents=True, exist_ok=True)
                snap_config = CompilerConfig(
                    target=config.target,
                    compat_mode=config.compat_mode,
                    snapshot_dir=str(snap_dir),
                    transform_log_path=str(snap_dir / "transform_log.jsonl"),
                    fold_constants=config.fold_constants,
                    idiomatic_loops=config.idiomatic_loops,
                )
                compile_source(case.program_source, f"{cid}.cpp", snap_config)

                # Save case artifacts in out_dir / "failures" / cid for localisation
                (case_dir / "program.cpp").write_text(case.program_source, encoding="utf-8")
                (case_dir / "input.txt").write_text(in_text, encoding="utf-8")
                if cxx_exec is not None:
                    (case_dir / "cxx_output.txt").write_text(cxx_exec.stdout, encoding="utf-8")
                meta_data = {
                    "case_id": cid,
                    "outcome": diff_res.outcome.value,
                    "reason": diff_res.reason,
                    "cxx_result": cxx_exec.to_dict() if cxx_exec else None,
                    "py_result": py_exec.to_dict() if py_exec else None,
                }
                (case_dir / "meta.json").write_text(
                    json.dumps(meta_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )

            save_regression_case(
                case=case,
                input_text=in_text,
                result=diff_res,
                snapshot_source_dir=snap_dir,
            )

        results.append(diff_res)

    return results


def run_suite(
    suite: str = "curated",
    seed: int = 1,
    count: int = 200,
    compat_mode: str = "range_guided",
    overflow_policy: str = "assume_no_overflow",
    timeout: float = 5.0,
    output_cap: int = 1048576,
    out_dir: str | Path | None = None,
    compiler: str | None = None,
) -> DiffSummary:
    """Run a differential testing suite ('curated', 'generated', or 'all')."""
    out_path = Path(out_dir) if out_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)

    capabilities = probe_cxx_capabilities(compiler)
    cache = CxxBuildCache()

    config = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy(overflow_policy)),
        compat_mode=CompatMode(compat_mode),
    )

    cases: list[TestCase] = []
    if suite in ("curated", "all"):
        cases.extend(load_curated_cases())
    if suite in ("generated", "all"):
        cases.extend(generate_suite(count=count, base_seed=seed))

    all_results: list[DiffResult] = []
    for c in cases:
        # Check if case has config overrides
        case_cfg = config
        if c.config_overrides:
            override_pol = c.config_overrides.get("overflow_policy")
            if override_pol:
                case_cfg = CompilerConfig(
                    target=TargetModel(overflow_policy=OverflowPolicy(override_pol)),
                    compat_mode=config.compat_mode,
                )
        results = run_case(
            case=c,
            config=case_cfg,
            capabilities=capabilities,
            cache=cache,
            timeout=timeout,
            output_cap=output_cap,
            out_dir=out_path,
        )
        all_results.extend(results)

    counts: dict[Outcome, int] = {o: 0 for o in Outcome}
    for r in all_results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1

    rate, num, denom = compute_agreement_rate(counts)

    summary = DiffSummary(
        suite=suite,
        total_runs=len(all_results),
        counts=counts,
        agreement_rate=rate,
        numerator=num,
        denominator=denom,
        results=all_results,
        capabilities=capabilities,
        config={
            "compat_mode": compat_mode,
            "overflow_policy": overflow_policy,
            "timeout": timeout,
            "output_cap": output_cap,
        },
        seed=seed if suite in ("generated", "all") else None,
    )

    if out_path:
        summary_file = out_path / "summary.json"
        summary_file.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return summary
