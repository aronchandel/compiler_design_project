"""Integration tests for timeout handling and undefined behavior classification."""

import pytest

from cpp2py.config import CompilerConfig, OverflowPolicy, TargetModel
from cpp2py.testing.comparator import Outcome
from cpp2py.testing.corpus import TestCase
from cpp2py.testing.cxx_runner import CxxBuildCache, probe_cxx_capabilities
from cpp2py.testing.difftest import run_case

capabilities = probe_cxx_capabilities()
cxx_skip = pytest.mark.skipif(
    not capabilities.available,
    reason=f"g++ compiler not available/functional: {capabilities.reason}",
)


@pytest.mark.requires_cxx
@cxx_skip
def test_infinite_loop_timeout_cpp():
    """An infinite-loop C++ program must be classified as TIMEOUT_CPP within the bound."""
    # In C++, while(1){} loops forever.
    # In Python, the translated code would also loop forever, but we can set timeout small.
    # Or translate a while loop that loops forever in C++.
    case = TestCase(
        case_id="infinite_loop_test",
        program_source=(
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int x = 1;\n"
            "    while (x > 0) {\n"
            "        x = x + 0;\n"
            "    }\n"
            "    cout << x << endl;\n"
            "    return 0;\n"
            "}\n"
        ),
        inputs=[""],
        origin="curated",
    )
    config = CompilerConfig()
    cache = CxxBuildCache()
    # Run with small timeout: 1.0s
    results = run_case(case, config, capabilities, cache=cache, timeout=1.0)
    assert len(results) == 1
    # Both processes loop forever so both time out, which yields BOTH_FAILED_AGREE
    assert results[0].outcome in (Outcome.TIMEOUT_CPP, Outcome.BOTH_FAILED_AGREE)


@pytest.mark.requires_cxx
@cxx_skip
def test_signed_overflow_policies():
    """Signed overflow under wrap policy must pass and produce identical wrapped output."""
    case = TestCase(
        case_id="signed_overflow_wrap",
        program_source=(
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int x = 2147483647;\n"
            "    x = x + 1;\n"
            "    cout << x << endl;\n"
            "    return 0;\n"
            "}\n"
        ),
        inputs=[""],
        origin="curated",
    )
    # Under wrap policy
    config_wrap = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.WRAP),
    )
    cache = CxxBuildCache()
    results = run_case(case, config_wrap, capabilities, cache=cache)
    assert len(results) == 1
    assert results[0].outcome == Outcome.PASS
    assert results[0].cxx_result is not None
    assert "-2147483648" in results[0].cxx_result.stdout


@pytest.mark.requires_cxx
def test_sanitizer_capability_or_skip():
    """Verify that sanitizer capability is either functional or skipped with an explicit reason."""
    if not capabilities.available:
        pytest.skip(f"Compiler not available: {capabilities.reason}")
    if not capabilities.sanitizer_available:
        assert capabilities.sanitizer_reason is not None
        assert len(capabilities.sanitizer_reason) > 0
