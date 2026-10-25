"""Integration tests for eval suite execution and byte-identical reproducibility (AC8.2, AC8.3)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.evaluation.experiments import run_suite_evaluation


def test_eval_suite_benchmark_artifacts_written(tmp_path: Path) -> None:
    """AC8.2: eval --suite benchmark writes raw.json, metrics.json, tables.md, tables.csv, manifest.json, timing.json."""
    out_dir = tmp_path / "eval1"
    run_suite_evaluation(suite="benchmark", seed=1, out_dir=out_dir)

    assert (out_dir / "raw.json").exists()
    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "tables.md").exists()
    assert (out_dir / "tables.csv").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "timing.json").exists()

    # Validate metrics structure (AC8.6)
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "soundness_violations" in metrics
    assert isinstance(metrics["soundness_violations"], list)
    for p_name in ("B0", "B1", "E"):
        assert p_name in metrics["translators"]
        t_data = metrics["translators"][p_name]
        assert "denominator" in t_data
        assert "excluded_counts" in t_data


def test_eval_reproducibility_byte_identical(tmp_path: Path) -> None:
    """AC8.3: Two consecutive eval runs with the same parameters yield byte-identical raw.json and metrics.json."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    run_suite_evaluation(suite="benchmark", seed=42, out_dir=out1)
    run_suite_evaluation(suite="benchmark", seed=42, out_dir=out2)

    raw1 = (out1 / "raw.json").read_bytes()
    raw2 = (out2 / "raw.json").read_bytes()
    assert raw1 == raw2, "raw.json differs between runs with identical seeds!"

    metrics1 = (out1 / "metrics.json").read_bytes()
    metrics2 = (out2 / "metrics.json").read_bytes()
    assert metrics1 == metrics2, "metrics.json differs between runs with identical seeds!"
