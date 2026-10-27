import subprocess
import sys
from pathlib import Path
import pytest

from cpp2py.testing.comparator import DiffResult, Outcome
from cpp2py.testing.cxx_runner import CxxCapabilities
from cpp2py.testing.difftest import DiffSummary

def test_diff_summary_to_dict_ac6_8_schema():
    caps = CxxCapabilities(
        compiler="g++",
        available=True,
        version="6.3.0",
        cxx17_supported=True,
        sanitizer_available=False,
    )
    counts = {
        Outcome.PASS: 40,
        Outcome.UB_EXCLUDED: 2,
    }
    summary = DiffSummary(
        suite="curated",
        total_runs=42,
        counts=counts,
        agreement_rate=1.0,
        numerator=40,
        denominator=40,
        results=[],
        capabilities=caps,
        config={"compat_mode": "range_guided", "overflow_policy": "assume_no_overflow"},
        seed=1,
    )
    d = summary.to_dict()

    assert "tool_version" in d
    assert "python_version" in d
    assert "generator_version" in d
    assert d["suite"] == "curated"
    assert d["seed"] == 1
    assert "capabilities" in d
    assert d["capabilities"]["compiler"] == "g++"
    assert "config" in d
    assert d["config"]["compat_mode"] == "range_guided"
    assert d["total_runs"] == 42
    assert "counts" in d
    assert d["counts"]["PASS"] == 40
    assert d["counts"]["UB_EXCLUDED"] == 2
    assert "agreement_rate" in d
    assert d["agreement_rate"]["rate"] == 1.0
    assert d["agreement_rate"]["numerator"] == 40
    assert d["agreement_rate"]["denominator"] == 40
    assert "excluded_counts" in d
    assert d["excluded_counts"]["UB_EXCLUDED"] == 2
    assert "mismatches" in d
    assert d["mismatches"] == []

def test_diff_summary_has_mismatches_false_when_clean():
    r1 = DiffResult(case_id="c1", outcome=Outcome.PASS, reason="Passed")
    r2 = DiffResult(case_id="c2", outcome=Outcome.UB_EXCLUDED, reason="UB detected")
    caps = CxxCapabilities(compiler="g++", available=True)
    summary = DiffSummary(
        suite="curated",
        total_runs=2,
        counts={Outcome.PASS: 1, Outcome.UB_EXCLUDED: 1},
        agreement_rate=1.0,
        numerator=1,
        denominator=1,
        results=[r1, r2],
        capabilities=caps,
        config={},
    )
    assert summary.has_mismatches() is False

def test_diff_summary_has_mismatches_true_on_failure():
    r1 = DiffResult(case_id="c1", outcome=Outcome.PASS, reason="Passed")
    r2 = DiffResult(case_id="c2", outcome=Outcome.MISMATCH_STDOUT, reason="Stdout mismatch")
    caps = CxxCapabilities(compiler="g++", available=True)
    summary = DiffSummary(
        suite="curated",
        total_runs=2,
        counts={Outcome.PASS: 1, Outcome.MISMATCH_STDOUT: 1},
        agreement_rate=0.5,
        numerator=1,
        denominator=2,
        results=[r1, r2],
        capabilities=caps,
        config={},
    )
    assert summary.has_mismatches() is True

def test_diff_summary_print_summary(capsys):
    caps = CxxCapabilities(compiler="g++", available=True, version="6.3.0", sanitizer_available=False)
    summary = DiffSummary(
        suite="curated",
        total_runs=42,
        counts={Outcome.PASS: 40, Outcome.UB_EXCLUDED: 2},
        agreement_rate=1.0,
        numerator=40,
        denominator=40,
        results=[],
        capabilities=caps,
        config={},
    )
    summary.print_summary()
    captured = capsys.readouterr()
    assert "Differential Testing Summary" in captured.out
    assert "PASS" in captured.out
    assert "UB_EXCLUDED" in captured.out
    assert "Agreement Rate: 40/40 (100.00%)" in captured.out

def test_difftest_cli_help():
    res = subprocess.run(
        [sys.executable, "-m", "cpp2py", "difftest", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "--suite" in res.stdout
    assert "--compat" in res.stdout
    assert "--overflow" in res.stdout
    assert "--timeout" in res.stdout
    assert "--out" in res.stdout
    assert "--seed" in res.stdout
    assert "--count" in res.stdout

def test_difftest_cli_invalid_arguments():
    res = subprocess.run(
        [sys.executable, "-m", "cpp2py", "difftest", "--suite", "nonexistent_suite"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2

    res2 = subprocess.run(
        [sys.executable, "-m", "cpp2py", "difftest", "--compat", "invalid_compat"],
        capture_output=True,
        text=True,
    )
    assert res2.returncode == 2
