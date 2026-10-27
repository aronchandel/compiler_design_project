import pytest

from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.testing.comparator import Outcome
from cpp2py.testing.cxx_runner import CxxBuildCache, probe_cxx_capabilities
from cpp2py.testing.difftest import run_case
from cpp2py.testing.testgen.programs import generate_suite

capabilities = probe_cxx_capabilities()
cxx_skip = pytest.mark.skipif(
    not capabilities.available,
    reason=f"g++ compiler not available/functional: {capabilities.reason}",
)

def test_generated_suite_reproducibility():
    suite1 = generate_suite(count=50, base_seed=1)
    suite2 = generate_suite(count=50, base_seed=1)

    assert len(suite1) == len(suite2) == 50
    for c1, c2 in zip(suite1, suite2):
        assert c1.case_id == c2.case_id
        assert c1.program_source == c2.program_source
        assert c1.inputs == c2.inputs

@pytest.mark.requires_cxx
@cxx_skip
def test_generated_suite_acceptance():
    suite = generate_suite(count=200, base_seed=1)
    config = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    cache = CxxBuildCache()

    for idx, case in enumerate(suite):
        results = run_case(case, config, capabilities, cache=cache)
        for r in results:
            assert r.outcome != Outcome.CPP_COMPILE_ERROR, f"g++ compile error in {r.case_id}: {r.reason}"
            assert r.outcome != Outcome.TRANSLATE_REJECTED, f"Translator rejected generated program {r.case_id}: {r.reason}"
