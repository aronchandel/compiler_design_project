"""Unit tests for test generator (determinism, boundaries, termination)."""

import random
import pytest

from cpp2py.testing.testgen.inputs import (
    BOUNDARY_VALUES,
    INT_MAX_32,
    INT_MIN_32,
    generate_input_stream,
    generate_input_value,
)
from cpp2py.testing.testgen.programs import (
    GENERATOR_VERSION,
    generate_program_case,
    generate_suite,
)


def test_generator_version():
    assert GENERATOR_VERSION == "1.0"


def test_generator_determinism():
    # Same seed must produce byte-identical program source and inputs
    case1 = generate_program_case(seed=12345, case_id="c1")
    case2 = generate_program_case(seed=12345, case_id="c1")

    assert case1.program_source == case2.program_source
    assert case1.inputs == case2.inputs


def test_generator_different_seeds():
    c1 = generate_program_case(seed=100, case_id="c1")
    c2 = generate_program_case(seed=200, case_id="c2")
    assert c1.program_source != c2.program_source


def test_generate_suite_determinism():
    s1 = generate_suite(count=5, base_seed=42)
    s2 = generate_suite(count=5, base_seed=42)
    assert len(s1) == 5
    for a, b in zip(s1, s2):
        assert a.program_source == b.program_source
        assert a.inputs == b.inputs


def test_input_generator_boundaries():
    rng = random.Random(999)
    values = [generate_input_value(rng) for _ in range(100)]
    # At least some values must be in BOUNDARY_VALUES
    boundary_hits = [v for v in values if v in BOUNDARY_VALUES]
    assert len(boundary_hits) > 20


def test_input_generator_assumed_range():
    rng = random.Random(42)
    lo, hi = 10, 50
    for _ in range(100):
        val = generate_input_value(rng, assumed_range=(lo, hi))
        assert lo <= val <= hi, f"Generated {val} outside [{lo}, {hi}]"


def test_generate_input_stream():
    rng = random.Random(7)
    stream = generate_input_stream(rng, num_inputs=3)
    tokens = stream.strip().split()
    assert len(tokens) == 3
    # Check each token is an integer
    for t in tokens:
        int(t)


def test_programs_contain_no_syntactic_zero_division():
    # Check over 50 generated programs that / 0 or % 0 is never generated
    suite = generate_suite(count=50, base_seed=1)
    for c in suite:
        assert "/ 0" not in c.program_source
        assert "% 0" not in c.program_source
        assert "/ (0)" not in c.program_source
        assert "% (0)" not in c.program_source
