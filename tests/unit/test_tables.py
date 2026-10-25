"""Unit tests for Markdown and CSV evaluation table renderers (ARCH §J.2)."""

from __future__ import annotations

import csv
import io
import pytest
from cpp2py.evaluation.tables import (
    render_comparison_csv,
    render_comparison_markdown,
    render_localisation_csv,
    render_localisation_markdown,
)


@pytest.fixture
def sample_metrics_data() -> dict:
    return {
        "suite_info": {
            "suite": "benchmark",
            "seed": 1,
            "count": 22,
            "N": 22,
        },
        "translators": {
            "B0": {
                "agreement_rate": 0.45,
                "numerator": 9,
                "denominator": 20,
                "mismatch_count": 11,
                "excluded_counts": {"UB_EXCLUDED": 2, "SKIPPED": 0, "COMPILE_OR_TRANSLATE_ERROR": 0},
                "helper_sites": 0,
                "size_proxy": {"lines": 15.0, "helpers": 0.0},
            },
            "B1": {
                "agreement_rate": 1.0,
                "numerator": 20,
                "denominator": 20,
                "mismatch_count": 0,
                "excluded_counts": {"UB_EXCLUDED": 2, "SKIPPED": 0, "COMPILE_OR_TRANSLATE_ERROR": 0},
                "helper_sites": 30,
                "size_proxy": {"lines": 22.0, "helpers": 1.36},
            },
            "E": {
                "agreement_rate": 1.0,
                "numerator": 20,
                "denominator": 20,
                "mismatch_count": 0,
                "excluded_counts": {"UB_EXCLUDED": 2, "SKIPPED": 0, "COMPILE_OR_TRANSLATE_ERROR": 0},
                "helper_sites": 12,
                "size_proxy": {"lines": 18.0, "helpers": 0.55},
            },
        },
        "static_unnecessary_helpers": {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "helpers_e": 12,
            "helpers_b1": 30,
            "ratio_e_to_b1": 0.4,
            "unnecessary_helpers_count": 0,
            "unnecessary_sites": [],
        },
        "dynamic_unnecessary_helpers": {
            "total_executions": 50,
            "differs_from_native": 10,
            "equals_native": 40,
            "empirically_unnecessary_ratio": 0.8,
            "label": "empirically unnecessary on this corpus",
        },
        "soundness_violations": [],
    }


def test_comparison_markdown_structure(sample_metrics_data: dict) -> None:
    """Verify that render_comparison_markdown outputs complete table with headers and rows."""
    md = render_comparison_markdown(sample_metrics_data)
    assert "# Evaluation Results: Comparative Summary" in md
    assert "| Metric | B0 (Naive) | B1 (Always-Protect) | E (Range-Guided) |" in md
    assert "**Agreement Rate**" in md
    assert "9/20 (45.00%)" in md
    assert "20/20 (100.00%)" in md
    assert "**Helper Ratio (E / B1)**" in md
    assert "0.4000" in md
    assert "**Soundness Violations**" in md
    assert "No soundness violations detected." in md


def test_comparison_markdown_with_violations(sample_metrics_data: dict) -> None:
    """Verify that soundness violations are listed in their own table if present."""
    data = dict(sample_metrics_data)
    data["soundness_violations"] = [
        {
            "case_id": "test_bug",
            "category": "div",
            "e_outcome": "MISMATCH_STDOUT",
            "b1_outcome": "PASS",
            "details": "Wrong truncating division",
        }
    ]
    md = render_comparison_markdown(data)
    assert "| `test_bug` | div | `MISMATCH_STDOUT` | `PASS` | Wrong truncating division |" in md


def test_comparison_csv_structure(sample_metrics_data: dict) -> None:
    """Verify that render_comparison_csv generates valid CSV with correct headers and metrics."""
    csv_str = render_comparison_csv(sample_metrics_data)
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    header = rows[0]
    assert header == ["metric", "B0_naive", "B1_always", "E_range_guided"]

    metric_names = [r[0] for r in rows[1:]]
    assert "agreement_rate" in metric_names
    assert "helper_sites" in metric_names
    assert "helper_ratio_vs_b1" in metric_names
    assert "static_precision" in metric_names
    assert "soundness_violations" in metric_names


def test_localisation_markdown_structure() -> None:
    """Verify that render_localisation_markdown formats top-k, MRR, and per-fault table."""
    loc_data = {
        "n": 2,
        "top1_hits": 2,
        "top1_rate": 1.0,
        "top3_hits": 2,
        "top3_rate": 1.0,
        "mrr": 1.0,
        "fault_ranks": [
            {
                "id": "F01",
                "name": "floor_div",
                "expected_stage": "after_constant_fold",
                "diagnosed_stage": "after_constant_fold",
                "expected_suspect": "div",
                "rank": 1,
                "reciprocal_rank": 1.0,
                "top1": True,
                "top3": True,
            },
            {
                "id": "F02",
                "name": "mod_sign",
                "expected_stage": "codegen_or_plan",
                "diagnosed_stage": "codegen_or_plan",
                "expected_suspect": "mod",
                "rank": 1,
                "reciprocal_rank": 1.0,
                "top1": True,
                "top3": True,
            },
        ],
    }
    md = render_localisation_markdown(loc_data)
    assert "# Failure Localisation Evaluation Report" in md
    assert "Top-1 Hit Rate:** 2/2 (100.00%)" in md
    assert "Mean Reciprocal Rank (MRR):** 1.0000" in md
    assert "| `F01` | floor_div | `after_constant_fold` |" in md
    assert "| `F02` | mod_sign | `codegen_or_plan` |" in md


def test_localisation_csv_structure() -> None:
    """Verify that render_localisation_csv outputs valid CSV columns."""
    loc_data = {
        "n": 1,
        "fault_ranks": [
            {
                "id": "F01",
                "name": "floor_div",
                "expected_stage": "after_constant_fold",
                "diagnosed_stage": "after_constant_fold",
                "expected_suspect": "div",
                "rank": 1,
                "reciprocal_rank": 1.0,
                "top1": True,
                "top3": True,
            }
        ]
    }
    csv_str = render_localisation_csv(loc_data)
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    assert rows[0] == [
        "fault_id", "name", "expected_stage", "diagnosed_stage",
        "expected_suspect", "rank", "reciprocal_rank", "top1", "top3"
    ]
    assert rows[1][0] == "F01"
    assert rows[1][5] == "1"
