"""Integration tests for failure localisation evaluation (AC8.7)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.evaluation.experiments import run_localisation_suite
from cpp2py.evaluation.faults import FAULTS


def test_eval_localisation_suite(tmp_path: Path) -> None:
    """AC8.7: eval localisation runs >= 10 faults and reports top-1, top-3, MRR, N, and per-fault table."""
    out_dir = tmp_path / "eval_loc"
    loc_data = run_localisation_suite(out_dir=out_dir)

    assert (out_dir / "localisation_metrics.json").exists()
    assert (out_dir / "localisation_table.md").exists()
    assert (out_dir / "localisation_table.csv").exists()

    metrics = json.loads((out_dir / "localisation_metrics.json").read_text(encoding="utf-8"))
    assert metrics["n"] >= 10
    assert metrics["n"] == len(FAULTS)
    assert 0.0 <= metrics["top1_rate"] <= 1.0
    assert 0.0 <= metrics["top3_rate"] <= 1.0
    assert 0.0 <= metrics["mrr"] <= 1.0
    assert len(metrics["fault_ranks"]) == len(FAULTS)

    md_table = (out_dir / "localisation_table.md").read_text(encoding="utf-8")
    assert "Top-1 Hit Rate:" in md_table
    assert "Top-3 Hit Rate:" in md_table
    assert "Mean Reciprocal Rank (MRR):" in md_table

    for f in FAULTS:
        assert f.id in md_table
