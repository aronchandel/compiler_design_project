"""Experiment runners and evaluation orchestrator (ARCH §J.3, §J.4).

Executes comparative evaluation suites (benchmark, generated, all) for B0, B1, E
and fault-injection localisation evaluation.
Outputs:
- manifest.json
- raw.json
- metrics.json
- timing.json
- tables.md
- tables.csv
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import cpp2py
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.analysis.intervals import Interval
from cpp2py.compat.helpers import (
    get_instrumentation_counts,
    get_instrumentation_prelude,
    helper_source,
    reset_instrumentation,
)
from cpp2py.evaluation.faults import FAULTS, run_fault_evaluation
from cpp2py.evaluation.metrics import (
    compute_agreement_rate,
    compute_dynamic_helper_metrics,
    compute_localisation_metrics,
    compute_static_helper_metrics,
    compute_timing_stats,
    find_soundness_violations,
)
from cpp2py.evaluation.presets import b0_config, b1_config, e_config
from cpp2py.evaluation.tables import (
    render_comparison_csv,
    render_comparison_markdown,
    render_localisation_csv,
    render_localisation_markdown,
)
from cpp2py.testing.comparator import Outcome, compare_results
from cpp2py.testing.corpus import TestCase
from cpp2py.testing.cxx_runner import CxxBuildCache, compile_cxx, probe_cxx_capabilities, run_cxx
from cpp2py.testing.py_runner import run_python
from cpp2py.testing.testgen.programs import generate_suite


def _repo_root() -> Path:
    """Find repository root."""
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        if (curr / "pyproject.toml").exists():
            return curr
        curr = curr.parent
    return Path.cwd()


def load_benchmark_cases(benchmarks_dir: str | Path | None = None) -> tuple[list[TestCase], list[dict[str, Any]]]:
    """Load benchmark test cases and ground-truth labels."""
    if benchmarks_dir is None:
        bdir = _repo_root() / "benchmarks"
    else:
        bdir = Path(benchmarks_dir)

    labels_file = bdir / "labels.json"
    labels: list[dict[str, Any]] = []
    if labels_file.exists():
        labels = json.loads(labels_file.read_text(encoding="utf-8"))

    progs_dir = bdir / "programs"
    cases: list[TestCase] = []
    if not progs_dir.exists():
        return cases, labels

    # Build assumed ranges per file
    assumed_by_file: dict[str, dict[str, Any]] = {}
    for lbl in labels:
        f = lbl.get("file", "")
        ar = lbl.get("assumed_ranges", {})
        if ar:
            converted = {}
            for k, v in ar.items():
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    converted[k] = Interval(v[0], v[1])
                elif isinstance(v, Interval):
                    converted[k] = v
            assumed_by_file.setdefault(f, {}).update(converted)

    for cpp_file in sorted(progs_dir.glob("*.cpp"), key=lambda p: p.name):
        src = cpp_file.read_text(encoding="utf-8")
        in_file = cpp_file.with_suffix(".in")
        inputs = [in_file.read_text(encoding="utf-8")] if in_file.exists() else [""]

        cfg_overrides = {}
        if cpp_file.name in assumed_by_file:
            cfg_overrides["assumed_ranges"] = assumed_by_file[cpp_file.name]

        cases.append(TestCase(
            case_id=cpp_file.stem,
            program_source=src,
            inputs=inputs,
            origin="benchmark",
            config_overrides=cfg_overrides,
            cpp_path=cpp_file,
        ))

    return cases, labels


def _count_helpers_and_lines(source: str) -> tuple[int, int]:
    """Count helper function occurrences and total lines in generated Python."""
    if not source:
        return 0, 0
    lines = source.splitlines()
    line_count = len(lines)
    # Count call sites of helpers in generated code
    helper_calls = 0
    for h in ("_cpp_div(", "_cpp_mod(", "_wrap_i32(", "_wrap_i64(", "_check_i32(", "_check_i64("):
        helper_calls += source.count(h)
    return helper_calls, line_count


def _extract_plan_decisions(
    cpp_source: str,
    case_id: str,
    config: CompilerConfig,
) -> tuple[list[dict[str, Any]], int]:
    """Compile with cpp2py and extract per-instruction helper decisions with source spans."""
    res = compile_source(cpp_source, f"{case_id}.cpp", config=config)
    decisions: list[dict[str, Any]] = []
    helper_count = 0

    if not res.success or res.ir is None or res.plan is None:
        return decisions, helper_count

    plan_by_id = res.plan.decisions

    for fn in res.ir.functions:
        for instr in fn.body:
            if instr.opcode.name in ("DIV", "MOD"):
                pdec = plan_by_id.get(instr.op_id)
                inserted = False
                if pdec and pdec.action.name in ("HELPER", "WRAP", "CHECK"):
                    inserted = True
                    helper_count += 1

                line = instr.span.start.line if instr.span else 0
                col = instr.span.start.col if instr.span else 0
                op_char = "/" if instr.opcode.name == "DIV" else "%"
                decisions.append({
                    "file": f"{case_id}.cpp",
                    "line": line,
                    "col": col,
                    "op": op_char,
                    "inserted_helper": inserted,
                    "action": pdec.action.value if pdec else "native",
                })

    return decisions, helper_count


def run_suite_evaluation(
    suite: str = "benchmark",
    seed: int = 1,
    count: int = 200,
    out_dir: str | Path | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Execute complete comparative evaluation across B0, B1, and E presets."""
    out_path = Path(out_dir) if out_dir else _repo_root() / "out" / "eval"
    out_path.mkdir(parents=True, exist_ok=True)

    caps = probe_cxx_capabilities()
    cache = CxxBuildCache()

    # Load corpus
    cases: list[TestCase] = []
    labels: list[dict[str, Any]] = []

    if suite in ("benchmark", "all"):
        bench_cases, bench_labels = load_benchmark_cases()
        cases.extend(bench_cases)
        labels.extend(bench_labels)

    if suite in ("generated", "all"):
        gen_cases = generate_suite(count=count, base_seed=seed)
        cases.extend(gen_cases)

    total_n = len(cases)

    # 1. Manifest
    manifest = {
        "tool_version": cpp2py.__version__,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "suite": suite,
        "seed": seed,
        "count": count,
        "total_cases": total_n,
        "cxx_capabilities": caps.to_dict(),
        "configs": {
            "B0": {"compat_mode": "naive", "fold_constants": True, "overflow_policy": "assume_no_overflow"},
            "B1": {"compat_mode": "always", "fold_constants": True, "overflow_policy": "assume_no_overflow"},
            "E": {"compat_mode": "range_guided", "fold_constants": True, "overflow_policy": "assume_no_overflow"},
        },
    }
    (out_path / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    # Tracking containers
    raw_results: dict[str, Any] = {}
    translator_stats: dict[str, dict[str, Any]] = {
        "B0": {"runs": [], "helper_sites": 0, "total_lines": 0},
        "B1": {"runs": [], "helper_sites": 0, "total_lines": 0},
        "E": {"runs": [], "helper_sites": 0, "total_lines": 0},
    }

    all_e_decisions: list[dict[str, Any]] = []
    dynamic_total = 0
    dynamic_differs = 0

    # Execute translation and tests
    for case in cases:
        case_id = case.case_id
        raw_case: dict[str, Any] = {
            "case_id": case_id,
            "origin": case.origin,
            "inputs": case.inputs,
            "results": {},
        }

        # 1. Compile C++ if compiler is available
        cxx_build = None
        if caps.available:
            cxx_build = compile_cxx(
                source_code=case.program_source,
                cache=cache,
                compiler=caps.compiler,
            )

        # 2. Run for each preset B0, B1, E
        for p_name, cfg_factory in (("B0", b0_config), ("B1", b1_config), ("E", e_config)):
            cfg = cfg_factory(assumed_ranges=case.config_overrides.get("assumed_ranges", {}))
            comp_res = compile_source(case.program_source, f"{case_id}.cpp", config=cfg)

            if not comp_res.success or comp_res.python_source is None:
                # Translation rejected or error
                for idx, in_text in enumerate(case.inputs):
                    run_id = f"{case_id}[{idx}]" if len(case.inputs) > 1 else case_id
                    diff_res = compare_results(
                        case_id=run_id,
                        translate_success=False,
                        translate_diagnostics=[d.message for d in comp_res.diagnostics],
                    )
                    translator_stats[p_name]["runs"].append(diff_res.to_dict())
                continue

            py_src = comp_res.python_source
            h_count, l_count = _count_helpers_and_lines(py_src)
            translator_stats[p_name]["helper_sites"] += h_count
            translator_stats[p_name]["total_lines"] += l_count

            # Track decisions for E
            if p_name == "E" and case.origin == "benchmark":
                decisions, _ = _extract_plan_decisions(case.program_source, case_id, cfg)
                all_e_decisions.extend(decisions)

            preset_case_runs = []

            for idx, in_text in enumerate(case.inputs):
                run_id = f"{case_id}[{idx}]" if len(case.inputs) > 1 else case_id

                # If C++ compiler not available, skip differential run cleanly
                if not caps.available or cxx_build is None or not cxx_build.success:
                    diff_res = compare_results(
                        case_id=run_id,
                        skipped=True,
                        skip_reason=caps.reason or "C++ compiler not available",
                    )
                    translator_stats[p_name]["runs"].append(diff_res.to_dict())
                    preset_case_runs.append(diff_res.to_dict())
                    continue

                # Run C++
                cxx_exec = run_cxx(
                    binary_path=cxx_build.binary_path,  # type: ignore
                    stdin_text=in_text,
                    timeout=timeout,
                )

                # Run Python
                py_exec = run_python(
                    source_or_file=py_src,
                    stdin_text=in_text,
                    timeout=timeout,
                    is_file=False,
                )

                diff_res = compare_results(
                    case_id=run_id,
                    cxx_result=cxx_exec,
                    py_result=py_exec,
                    translate_success=True,
                    cxx_compile_success=True,
                )
                translator_stats[p_name]["runs"].append(diff_res.to_dict())
                preset_case_runs.append(diff_res.to_dict())

            raw_case["results"][p_name] = {
                "helper_count": h_count,
                "line_count": l_count,
                "runs": preset_case_runs,
            }

        # 3. Dynamic instrumentation measurement for E
        instr_file = out_path / "_temp_instr.json"
        instr_env = {"CPP2PY_INSTR_OUT": str(instr_file)}
        # Build instrumented Python source for E
        e_cfg = e_config(assumed_ranges=case.config_overrides.get("assumed_ranges", {}))
        e_comp = compile_source(case.program_source, f"{case_id}.cpp", config=e_cfg)
        if e_comp.success and e_comp.python_source:
            # Inject instrumented helpers
            instr_py = get_instrumentation_prelude() + "\n"
            for line in e_comp.python_source.splitlines():
                if "_cpp_div(a: int, b: int) -> int:" in line:
                    instr_py += helper_source("_cpp_div", instrumented=True) + "\n"
                elif "_cpp_mod(a: int, b: int) -> int:" in line:
                    instr_py += helper_source("_cpp_mod", instrumented=True) + "\n"
                else:
                    instr_py += line + "\n"

            for in_text in case.inputs:
                try:
                    if instr_file.exists():
                        instr_file.unlink()
                except Exception:
                    pass

                old_env = os.environ.get("CPP2PY_INSTR_OUT")
                try:
                    os.environ["CPP2PY_INSTR_OUT"] = str(instr_file)
                    run_python(instr_py, stdin_text=in_text, timeout=timeout)
                    if instr_file.exists():
                        counts = json.loads(instr_file.read_text(encoding="utf-8"))
                        dynamic_total += counts.get("total", 0)
                        dynamic_differs += counts.get("differs", 0)
                except Exception:
                    pass
                finally:
                    if old_env is not None:
                        os.environ["CPP2PY_INSTR_OUT"] = old_env
                    elif "CPP2PY_INSTR_OUT" in os.environ:
                        del os.environ["CPP2PY_INSTR_OUT"]
                    try:
                        if instr_file.exists():
                            instr_file.unlink()
                    except Exception:
                        pass

        raw_results[case_id] = raw_case

    # Save raw.json (deterministic sort_keys)
    (out_path / "raw.json").write_text(json.dumps(raw_results, indent=2, sort_keys=True), encoding="utf-8")

    # 4. Compute Metrics per translator
    translators_metrics: dict[str, Any] = {}
    for p_name in ("B0", "B1", "E"):
        runs = translator_stats[p_name]["runs"]
        tot = len(runs)
        pass_cnt = sum(1 for r in runs if r.get("outcome") == "PASS")
        mismatch_cnt = sum(1 for r in runs if "MISMATCH" in r.get("outcome", ""))
        ub_cnt = sum(1 for r in runs if r.get("outcome") == "UB_EXCLUDED")
        skip_cnt = sum(1 for r in runs if r.get("outcome") == "SKIPPED")
        err_cnt = sum(1 for r in runs if r.get("outcome") in ("CPP_COMPILE_ERROR", "TRANSLATE_REJECTED"))

        # Denominator = total - excluded
        denominator = tot - (ub_cnt + skip_cnt + err_cnt)
        numerator = pass_cnt
        rate = compute_agreement_rate(numerator, denominator)

        # Mismatches by category
        mismatches_by_cat: dict[str, int] = {}
        for r in runs:
            if "MISMATCH" in r.get("outcome", ""):
                cat = r.get("category", "arithmetic")
                mismatches_by_cat[cat] = mismatches_by_cat.get(cat, 0) + 1

        avg_lines = round(translator_stats[p_name]["total_lines"] / max(total_n, 1), 1)
        avg_helpers = round(translator_stats[p_name]["helper_sites"] / max(total_n, 1), 2)

        translators_metrics[p_name] = {
            "total_runs": tot,
            "numerator": numerator,
            "denominator": denominator,
            "agreement_rate": round(rate, 4) if rate is not None else None,
            "mismatch_count": mismatch_cnt,
            "mismatches_by_category": mismatches_by_cat,
            "excluded_counts": {
                "UB_EXCLUDED": ub_cnt,
                "SKIPPED": skip_cnt,
                "COMPILE_OR_TRANSLATE_ERROR": err_cnt,
            },
            "helper_sites": translator_stats[p_name]["helper_sites"],
            "size_proxy": {
                "lines": avg_lines,
                "helpers": avg_helpers,
            },
        }

    # 5. Static Unnecessary Helpers (against labels.json)
    b1_helper_count = translator_stats["B1"]["helper_sites"]
    static_metrics = compute_static_helper_metrics(
        eval_decisions=all_e_decisions,
        labels=labels,
        helpers_b1_count=b1_helper_count,
    )

    # 6. Dynamic Unnecessary Helpers
    dynamic_metrics = compute_dynamic_helper_metrics(
        total_executions=dynamic_total,
        differs_from_native=dynamic_differs,
    )

    # 7. Soundness Violations
    violations = find_soundness_violations(
        results_e=translator_stats["E"]["runs"],
        results_b1=translator_stats["B1"]["runs"],
    )

    # Combined metrics data
    metrics_data = {
        "suite_info": {
            "suite": suite,
            "seed": seed,
            "count": count,
            "N": total_n,
        },
        "translators": translators_metrics,
        "static_unnecessary_helpers": static_metrics.to_dict(),
        "dynamic_unnecessary_helpers": dynamic_metrics.to_dict(),
        "soundness_violations": [v.to_dict() for v in violations],
    }

    # Save metrics.json (deterministic sort_keys)
    (out_path / "metrics.json").write_text(json.dumps(metrics_data, indent=2, sort_keys=True), encoding="utf-8")

    # 8. Tables
    md_content = render_comparison_markdown(metrics_data)
    (out_path / "tables.md").write_text(md_content, encoding="utf-8")

    csv_content = render_comparison_csv(metrics_data)
    (out_path / "tables.csv").write_text(csv_content, encoding="utf-8")

    # 9. Timing json (median of >= 5 runs, stored ONLY in timing.json)
    timing_data: dict[str, Any] = {"runs_per_translator": 5, "timings": {}}
    for p_name, cfg_factory in (("B0", b0_config), ("B1", b1_config), ("E", e_config)):
        times: list[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            for c in cases[:10]:
                cfg = cfg_factory()
                compile_source(c.program_source, f"{c.case_id}.cpp", config=cfg)
            t1 = time.perf_counter()
            times.append(t1 - t0)
        t_stats = compute_timing_stats(times)
        timing_data["timings"][p_name] = t_stats.to_dict()

    (out_path / "timing.json").write_text(json.dumps(timing_data, indent=2, sort_keys=True), encoding="utf-8")

    return metrics_data


def run_localisation_suite(
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Execute localisation evaluation over all catalogue faults."""
    out_path = Path(out_dir) if out_dir else _repo_root() / "out" / "eval_loc"
    out_path.mkdir(parents=True, exist_ok=True)

    fault_results: list[dict[str, Any]] = []
    for fault in FAULTS:
        f_res = run_fault_evaluation(fault, out_path)
        fault_results.append(f_res)

    loc_metrics = compute_localisation_metrics(fault_results)
    loc_data = loc_metrics.to_dict()

    # Write localisation_metrics.json
    (out_path / "localisation_metrics.json").write_text(
        json.dumps(loc_data, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Write tables
    md_table = render_localisation_markdown(loc_data)
    (out_path / "localisation_table.md").write_text(md_table, encoding="utf-8")

    csv_table = render_localisation_csv(loc_data)
    (out_path / "localisation_table.csv").write_text(csv_table, encoding="utf-8")

    # Print to stdout
    print(md_table)
    return loc_data
