"""Fidelity report data model and construction.

Conforms to ARCH §I.4.
Generates structured fidelity data for translation and differential testing runs.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cpp2py
from cpp2py.compiler import CompilationResult
from cpp2py.config import CompilerConfig
from cpp2py.diagnostics import Severity
from cpp2py.ir.model import Opcode
from cpp2py.localisation import DISCLAIMER, localise
from cpp2py.testing.comparator import Outcome
from cpp2py.testing.cxx_runner import CxxCapabilities, probe_cxx_capabilities
from cpp2py.testing.difftest import DiffSummary

SCHEMA_VERSION: str = "1.0"

FIXED_SEMANTIC_DIFFERENCES: list[str] = [
    "C++ signed integer overflow is undefined behavior; under default policy (assume_no_overflow), Python evaluates without fixed-width wrapping unless --overflow wrap is selected.",
    "Python integer division and remainder differ from C++ for negative operands; range analysis selectively inserts compatibility helpers where operands may be negative.",
    "Python recursion is stack-limited (~1000 frames); deep C++ recursion may raise RecursionError.",
    "Stream I/O behavior on malformed input differs: C++ cin sets failbit while Python raises ValueError.",
]

LIMITATIONS_REFERENCE: str = (
    "See docs/LIMITATIONS.md for complete specification of supported C++ subset, "
    "assumptions S1-S6, policy semantics, and threats to validity."
)


@dataclass
class FidelityReport:
    """Complete fidelity report structure."""
    schema_version: str = SCHEMA_VERSION
    run_metadata: dict[str, Any] = field(default_factory=dict)
    translation_summary: dict[str, Any] | None = None
    compatibility_helpers: dict[str, Any] | None = None
    reported_risks: dict[str, Any] | None = None
    assumptions: list[str] = field(default_factory=list)
    unsupported_constructs: dict[str, Any] = field(default_factory=dict)
    potential_semantic_differences: list[str] = field(default_factory=lambda: list(FIXED_SEMANTIC_DIFFERENCES))
    test_results: dict[str, Any] | None = None
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    limitations: str = LIMITATIONS_REFERENCE
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_metadata": self.run_metadata,
            "translation_summary": self.translation_summary,
            "compatibility_helpers": self.compatibility_helpers,
            "reported_risks": self.reported_risks,
            "assumptions": self.assumptions,
            "unsupported_constructs": self.unsupported_constructs,
            "potential_semantic_differences": self.potential_semantic_differences,
            "test_results": self.test_results,
            "mismatches": self.mismatches,
            "limitations": self.limitations,
            "disclaimer": self.disclaimer,
        }


def build_translation_fidelity_report(
    source_text: str,
    filename: str,
    config: CompilerConfig,
    result: CompilationResult,
    capabilities: CxxCapabilities | None = None,
) -> FidelityReport:
    """Build a static fidelity report from a translation run."""
    caps = capabilities if capabilities is not None else probe_cxx_capabilities()
    sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    metadata: dict[str, Any] = {
        "tool_version": cpp2py.__version__,
        "date": datetime.date.today().isoformat(),
        "source_file": filename,
        "source_sha256": sha256,
        "reference_compiler": caps.compiler,
        "compiler_version": caps.version or "not available",
        "platform_capabilities": caps.to_dict(),
        "config": {
            "int_bits": config.target.int_bits,
            "long_long_bits": config.target.long_long_bits,
            "overflow_policy": config.target.overflow_policy.value,
            "compat_mode": config.compat_mode.value,
            "fold_constants": config.fold_constants,
            "idiomatic_loops": config.idiomatic_loops,
        },
    }

    if not result.success:
        e4_diags = [
            {
                "code": d.code,
                "message": d.message,
                "location": str(d.span) if d.span else "unknown",
            }
            for d in result.diagnostics
            if d.severity == Severity.ERROR
        ]
        unsupported = {
            "translated": False,
            "rejection_reason": "Source program rejected due to diagnostics / unsupported constructs.",
            "diagnostics": e4_diags,
        }
        return FidelityReport(
            run_metadata=metadata,
            unsupported_constructs=unsupported,
        )

    # Translation succeeded: gather summary, helpers, risks
    ir = result.ir
    op_counts: dict[str, int] = {}
    op_spans: dict[str, Any] = {}
    func_count = 0
    if ir:
        func_count = len(ir.functions)
        for f in ir.functions:
            for instr in f.body:
                op_counts[instr.opcode.value] = op_counts.get(instr.opcode.value, 0) + 1
                if instr.span:
                    op_spans[instr.op_id] = instr.span

    passes_changed: dict[str, int] = {}
    if result.transform_log:
        for r in result.transform_log.records:
            passes_changed[r.pass_name] = passes_changed.get(r.pass_name, 0) + 1

    summary = {
        "function_count": func_count,
        "operation_counts": op_counts,
        "passes_changed": passes_changed,
    }

    helpers_inserted: list[dict[str, Any]] = []
    helpers_avoided: list[dict[str, Any]] = []

    overflow_risks: list[dict[str, Any]] = []
    div_zero_risks: list[dict[str, Any]] = []
    narrowing_risks: list[dict[str, Any]] = []

    if result.plan:
        for op_id, dec in result.plan.decisions.items():
            span = op_spans.get(op_id)
            line_str = f"L{span.start.line}" if span else ""
            ranges_str = f"{dec.operand_ranges} -> {dec.result_range}"
            if dec.action.value.lower() == "helper":
                helpers_inserted.append({
                    "op_id": op_id,
                    "location": line_str,
                    "helper": dec.helper,
                    "reason": dec.reason,
                    "ranges": ranges_str,
                })
            else:
                helpers_avoided.append({
                    "op_id": op_id,
                    "location": line_str,
                    "reason": dec.reason,
                    "ranges": ranges_str,
                })

            for r in dec.risks:
                r_name = r.value if hasattr(r, "value") else str(r)
                risk_item = {"op_id": op_id, "location": line_str, "risk": r_name, "reason": dec.reason}
                if "OVERFLOW" in r_name:
                    overflow_risks.append(risk_item)
                elif "ZERO" in r_name:
                    div_zero_risks.append(risk_item)
                elif "NARROWING" in r_name:
                    narrowing_risks.append(risk_item)

    helpers_info = {
        "inserted_count": len(helpers_inserted),
        "avoided_count": len(helpers_avoided),
        "inserted": helpers_inserted,
        "avoided": helpers_avoided,
    }

    risks_info = {
        "overflow_possibilities": overflow_risks,
        "possible_division_by_zero": div_zero_risks,
        "lossy_narrowing": narrowing_risks,
    }

    assumptions = [
        f"{var} in [{iv.lo}, {iv.hi}]" for var, iv in config.assumed_ranges.items()
    ]

    return FidelityReport(
        run_metadata=metadata,
        translation_summary=summary,
        compatibility_helpers=helpers_info,
        reported_risks=risks_info,
        assumptions=assumptions,
        unsupported_constructs={"translated": True, "diagnostics": []},
    )


def build_difftest_fidelity_report(
    summary: DiffSummary,
    failures_base_dir: str | Path | None = None,
) -> FidelityReport:
    """Build a comprehensive fidelity report from a differential testing run."""
    caps = summary.capabilities
    metadata: dict[str, Any] = {
        "tool_version": cpp2py.__version__,
        "date": datetime.date.today().isoformat(),
        "suite": summary.suite,
        "seed": summary.seed,
        "generator_version": summary.generator_version,
        "reference_compiler": caps.compiler,
        "compiler_version": caps.version or "not available",
        "platform_capabilities": caps.to_dict(),
        "config": summary.config,
    }

    test_results_data = {
        "total_executions": summary.total_runs,
        "counts": {k.value: v for k, v in summary.counts.items()},
        "agreement_rate": {
            "rate": summary.agreement_rate,
            "numerator": summary.numerator,
            "denominator": summary.denominator,
        },
        "excluded_counts": {
            Outcome.UB_EXCLUDED.value: summary.counts.get(Outcome.UB_EXCLUDED, 0),
            Outcome.TRANSLATE_REJECTED.value: summary.counts.get(Outcome.TRANSLATE_REJECTED, 0),
            Outcome.CPP_COMPILE_ERROR.value: summary.counts.get(Outcome.CPP_COMPILE_ERROR, 0),
            Outcome.BOTH_FAILED_AGREE.value: summary.counts.get(Outcome.BOTH_FAILED_AGREE, 0),
            Outcome.SKIPPED.value: summary.counts.get(Outcome.SKIPPED, 0),
        },
    }

    mismatches: list[dict[str, Any]] = []
    base_fail = Path(failures_base_dir) if failures_base_dir else None

    for r in summary.results:
        if r.is_mismatch():
            m_item: dict[str, Any] = {
                "case_id": r.case_id,
                "outcome": r.outcome.value,
                "reason": r.reason,
            }

            # Attempt to localise if failure artifacts are present
            case_path = None
            if base_fail:
                cand = base_fail / "failures" / r.case_id
                if cand.exists():
                    case_path = cand
                else:
                    cand2 = base_fail / r.case_id
                    if cand2.exists():
                        case_path = cand2

            if case_path and case_path.exists():
                try:
                    loc_rep = localise(case_path)
                    m_item["localisation"] = {
                        "stage_verdict": loc_rep.stage_verdict,
                        "first_divergent_stage": loc_rep.first_divergent_stage,
                        "confidence": loc_rep.confidence,
                        "disclaimer": DISCLAIMER,
                        "suspects": [s.to_dict() for s in loc_rep.suspects],
                    }
                except Exception as e:
                    m_item["localisation_error"] = str(e)

            mismatches.append(m_item)

    return FidelityReport(
        run_metadata=metadata,
        test_results=test_results_data,
        mismatches=mismatches,
    )
