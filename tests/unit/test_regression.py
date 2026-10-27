import json
import tempfile
from pathlib import Path
import pytest

from cpp2py.testing.comparator import DiffResult, Outcome
from cpp2py.testing.corpus import TestCase
from cpp2py.testing.cxx_runner import ExecutionResult, CxxBuildCache, probe_cxx_capabilities
from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.testing.difftest import run_case
from cpp2py.testing.regression import (
    compute_case_sha8,
    load_regression_cases,
    save_regression_case,
)

def test_compute_case_sha8():
    src = "int main() { return 0; }"
    inp = "123\n"
    h1 = compute_case_sha8(src, inp)
    h2 = compute_case_sha8(src, inp)
    assert h1 == h2
    assert len(h1) == 8

def test_regression_round_trip():
    with tempfile.TemporaryDirectory() as td:
        reg_dir = Path(td) / "regression"
        case = TestCase(
            case_id="fail_test_01",
            program_source="#include <iostream>\nint main() { std::cout << 42 << std::endl; return 0; }\n",
            inputs=["10 20\n"],
            origin="generated",
            seed=777,
            config_overrides={"overflow_policy": "wrap"},
            notes="Testing mismatch",
        )
        diff_res = DiffResult(
            case_id="fail_test_01",
            outcome=Outcome.MISMATCH_STDOUT,
            reason="Stdout mismatch",
            cxx_result=ExecutionResult(stdout="42\n", stderr="", exit_code=0),
            py_result=ExecutionResult(stdout="43\n", stderr="", exit_code=0),
        )

        saved_path = save_regression_case(
            case=case,
            input_text="10 20\n",
            result=diff_res,
            regression_base_dir=reg_dir,
        )

        assert saved_path.exists()
        assert (saved_path / "program.cpp").exists()
        assert (saved_path / "input.txt").exists()
        assert (saved_path / "meta.json").exists()
        assert (saved_path / "snapshots").exists()

        meta = json.loads((saved_path / "meta.json").read_text(encoding="utf-8"))
        assert meta["outcome"] == "MISMATCH_STDOUT"
        assert meta["seed"] == 777
        assert meta["generator_version"] == "1.0"
        assert meta["status"] == "open"

        loaded = load_regression_cases(regression_base_dir=reg_dir)
        assert len(loaded) == 1
        l_case = loaded[0]
        assert l_case.program_source == case.program_source
        assert l_case.inputs == ["10 20\n"]
        assert l_case.origin == "regression"
        assert l_case.seed == 777

def test_persisted_regression_discovery():
    cases = load_regression_cases()

    for c in cases:
        assert c.origin == "regression"
        assert len(c.inputs) >= 1
        assert c.program_source.strip()

def test_regression_known_limitation_status():
    with tempfile.TemporaryDirectory() as td:
        reg_dir = Path(td) / "regression"
        case = TestCase(
            case_id="limitation_01",
            program_source="int main() { return 0; }",
            inputs=[""],
            origin="generated",
            seed=42,
        )
        diff_res = DiffResult(
            case_id="limitation_01",
            outcome=Outcome.MISMATCH_STDOUT,
            reason="Overflow under assume_no_overflow",
        )
        saved = save_regression_case(
            case=case,
            input_text="",
            result=diff_res,
            regression_base_dir=reg_dir,
            status="known_limitation",
        )
        meta = json.loads((saved / "meta.json").read_text(encoding="utf-8"))
        assert meta["status"] == "known_limitation"
        assert meta["notes"] == "Overflow under assume_no_overflow"
