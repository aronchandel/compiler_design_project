import pytest

from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.testing.comparator import Outcome
from cpp2py.testing.corpus import load_curated_cases, load_example_cases
from cpp2py.testing.cxx_runner import CxxBuildCache, compile_cxx, probe_cxx_capabilities, run_cxx
from cpp2py.testing.difftest import run_case, run_suite

capabilities = probe_cxx_capabilities()
cxx_skip = pytest.mark.skipif(
    not capabilities.available,
    reason=f"g++ compiler not available/functional: {capabilities.reason}",
)

@pytest.mark.requires_cxx
@cxx_skip
def test_mutation_sanity_negative_operands():
    all_curated = load_curated_cases()

    neg_cases = [c for c in all_curated if any(c.case_id.startswith(f"case_0{i}") for i in range(1, 7))]
    assert len(neg_cases) == 6

    cache = CxxBuildCache()

    naive_config = CompilerConfig(compat_mode=CompatMode.NAIVE)
    naive_mismatches = 0
    for c in neg_cases:
        results = run_case(c, naive_config, capabilities, cache=cache)
        for r in results:
            if r.outcome == Outcome.MISMATCH_STDOUT:
                naive_mismatches += 1

    assert naive_mismatches >= 1, f"Expected naive mode to fail on negative division/mod, but got {naive_mismatches} mismatches"

    always_config = CompilerConfig(compat_mode=CompatMode.ALWAYS)
    for c in neg_cases:
        results = run_case(c, always_config, capabilities, cache=cache)
        for r in results:
            assert r.outcome == Outcome.PASS, f"Always mode failed on {r.case_id}: {r.reason}"

    rg_config = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    for c in neg_cases:
        results = run_case(c, rg_config, capabilities, cache=cache)
        for r in results:
            assert r.outcome == Outcome.PASS, f"Range-guided mode failed on {r.case_id}: {r.reason}"

@pytest.mark.requires_cxx
@cxx_skip
def test_curated_suite_range_guided():
    summary = run_suite(suite="curated", compat_mode="range_guided")
    assert not summary.has_mismatches(), f"Mismatches in curated suite: {[r.case_id for r in summary.results if r.is_mismatch()]}"
    assert summary.counts[Outcome.PASS] >= 40
    assert summary.agreement_rate == 1.0

@pytest.mark.requires_cxx
@cxx_skip
def test_curated_suite_always():
    summary = run_suite(suite="curated", compat_mode="always")
    assert not summary.has_mismatches()
    assert summary.counts[Outcome.PASS] >= 40
    assert summary.agreement_rate == 1.0

@pytest.mark.requires_cxx
@cxx_skip
def test_examples_cross_validation_against_real_cxx():
    examples = load_example_cases()
    assert len(examples) > 10

    cache = CxxBuildCache()
    for ex in examples:
        build_res = compile_cxx(
            source_code=ex.program_source,
            overflow_policy="assume_no_overflow",
            cache=cache,
            compiler=capabilities.compiler,
        )
        assert build_res.success, f"Failed to build example {ex.case_id}: {build_res.compile_error}"

        stdin_text = ex.inputs[0] if ex.inputs else ""
        exec_res = run_cxx(build_res.binary_path, stdin_text=stdin_text)
        assert exec_res.exit_code == 0, f"Example {ex.case_id} failed with exit code {exec_res.exit_code}"

        cxx_stdout = exec_res.stdout.replace("\r\n", "\n")
        expected_stdout = (ex.expected_stdout or "").replace("\r\n", "\n")

        assert cxx_stdout == expected_stdout, f"Example {ex.case_id} C++ output does not match .expected file"
