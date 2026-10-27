from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig
from cpp2py.localisation import DISCLAIMER
from cpp2py.reporting.fidelity import (
    SCHEMA_VERSION,
    build_difftest_fidelity_report,
    build_translation_fidelity_report,
)
from cpp2py.testing.comparator import DiffResult, Outcome
from cpp2py.testing.cxx_runner import CxxCapabilities
from cpp2py.testing.difftest import DiffSummary

def test_translation_fidelity_report_div_needs_helper():
    cpp_path = Path("examples/phase5/div_needs_helper.cpp")
    source_text = cpp_path.read_text(encoding="utf-8")
    config = CompilerConfig()
    result = compile_source(source_text, cpp_path.name, config)
    assert result.success

    rep = build_translation_fidelity_report(source_text, cpp_path.name, config, result)
    d = rep.to_dict()

    assert d["schema_version"] == SCHEMA_VERSION
    assert d["run_metadata"]["tool_version"] == "0.0.0"
    assert d["translation_summary"]["function_count"] >= 1

    helpers = d["compatibility_helpers"]
    assert helpers is not None
    assert helpers["inserted_count"] >= 1
    assert any("_cpp_div" in h["helper"] or "_cpp_mod" in h["helper"] for h in helpers["inserted"])

    assert result.plan is not None
    inserted_in_plan = sum(1 for dec in result.plan.decisions.values() if dec.action.value.lower() == "helper")
    assert helpers["inserted_count"] == inserted_in_plan

def test_rejected_program_fidelity_report():
    cpp_path = Path("examples/phase1/errors/undeclared_var.cpp")
    source_text = cpp_path.read_text(encoding="utf-8")
    config = CompilerConfig()
    result = compile_source(source_text, cpp_path.name, config)
    assert not result.success

    rep = build_translation_fidelity_report(source_text, cpp_path.name, config, result)
    d = rep.to_dict()

    assert d["unsupported_constructs"]["translated"] is False
    assert "rejected" in d["unsupported_constructs"]["rejection_reason"].lower()
    diags = d["unsupported_constructs"]["diagnostics"]
    assert len(diags) >= 1
    assert any("E3001" in diag["code"] for diag in diags)

def test_rejected_program_e4xxx_fidelity_report():
    cpp_path = Path("examples/phase1/errors/unsupported_float.cpp")
    source_text = cpp_path.read_text(encoding="utf-8")
    config = CompilerConfig()
    result = compile_source(source_text, cpp_path.name, config)
    assert not result.success

    rep = build_translation_fidelity_report(source_text, cpp_path.name, config, result)
    d = rep.to_dict()

    assert d["unsupported_constructs"]["translated"] is False
    assert "rejected" in d["unsupported_constructs"]["rejection_reason"].lower()
    diags = d["unsupported_constructs"]["diagnostics"]
    assert len(diags) >= 1
    assert any(diag["code"].startswith("E4") for diag in diags)

def test_difftest_fidelity_report_structure_and_disclaimer():
    caps = CxxCapabilities(available=True, compiler="g++", version="10.0")
    results = [
        DiffResult(case_id="case_1", outcome=Outcome.PASS, reason="Outputs match"),
        DiffResult(case_id="case_2", outcome=Outcome.MISMATCH_STDOUT, reason="Output differs"),
        DiffResult(case_id="case_3", outcome=Outcome.UB_EXCLUDED, reason="Sanitizer UB detected"),
    ]
    counts = {
        Outcome.PASS: 1,
        Outcome.MISMATCH_STDOUT: 1,
        Outcome.UB_EXCLUDED: 1,
    }

    summary = DiffSummary(
        suite="curated",
        total_runs=3,
        counts=counts,
        agreement_rate=0.5,
        numerator=1,
        denominator=2,
        results=results,
        capabilities=caps,
        config={"compat_mode": "range_guided"},
    )

    rep = build_difftest_fidelity_report(summary)
    d = rep.to_dict()

    assert d["schema_version"] == SCHEMA_VERSION
    assert d["disclaimer"] == DISCLAIMER
    assert "Localisation is heuristic diagnosis, not guaranteed automatic diagnosis or repair." in d["disclaimer"]

    tr = d["test_results"]
    assert tr is not None
    assert tr["agreement_rate"]["numerator"] == 1
    assert tr["agreement_rate"]["denominator"] == 2
    assert tr["agreement_rate"]["rate"] == 0.5
    assert tr["excluded_counts"]["UB_EXCLUDED"] == 1
