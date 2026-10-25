"""Unit tests for cpp2py/reporting/render.py.

Verifies JSON and Markdown output generation, section headings, and formatting.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.localisation import DISCLAIMER
from cpp2py.reporting.fidelity import FidelityReport
from cpp2py.reporting.render import render_fidelity_json, render_fidelity_md


def test_render_json_and_md(tmp_path):
    report = FidelityReport(
        run_metadata={"tool_version": "0.0.0", "date": "2026-10-25"},
        translation_summary={"function_count": 1, "operation_counts": {"add": 2}, "passes_changed": {}},
        compatibility_helpers={"inserted_count": 1, "avoided_count": 2, "inserted": [], "avoided": []},
        reported_risks={"overflow_possibilities": [], "possible_division_by_zero": [], "lossy_narrowing": []},
        assumptions=["main.x in [0, 100]"],
        unsupported_constructs={"translated": True, "diagnostics": []},
        test_results={
            "total_executions": 10,
            "counts": {"PASS": 8, "MISMATCH_STDOUT": 2},
            "agreement_rate": {"rate": 0.8, "numerator": 8, "denominator": 10},
            "excluded_counts": {"UB_EXCLUDED": 0},
        },
        mismatches=[
            {
                "case_id": "test_mismatch",
                "outcome": "MISMATCH_STDOUT",
                "reason": "stdout mismatch",
                "localisation": {
                    "stage_verdict": "codegen_or_plan",
                    "first_divergent_stage": "codegen_or_plan",
                    "confidence": "heuristic",
                    "suspects": [{"rank": 1, "op_id": "op_5", "score": 7, "evidence": ["test evidence"]}],
                },
            }
        ],
    )

    json_path = render_fidelity_json(report, tmp_path)
    md_path = render_fidelity_md(report, tmp_path)

    assert json_path.exists()
    assert md_path.exists()

    # Verify JSON content
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["test_results"]["agreement_rate"]["denominator"] == 10

    # Verify Markdown headings and content
    md_text = md_path.read_text(encoding="utf-8")
    headings = [
        "# Fidelity Report",
        "## Run Metadata",
        "## Translation Summary",
        "## Compatibility Helpers",
        "## Reported-not-handled Risks",
        "## Assumptions",
        "## Unsupported Constructs",
        "## Potential Semantic Differences",
        "## Test Results",
        "## Mismatches and Localisation Suspects",
        "## Limitations",
    ]
    for h in headings:
        assert h in md_text, f"Missing heading '{h}' in fidelity.md"

    # Verbatim disclaimer check
    assert DISCLAIMER in md_text
    assert "8/10 (80.00%)" in md_text
