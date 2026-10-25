"""Unit tests for corpus loading (curated cases and example cases)."""

import pytest

from cpp2py.testing.corpus import load_curated_cases, load_example_cases


def test_load_curated_cases():
    cases = load_curated_cases()
    assert len(cases) >= 40, f"Expected at least 40 curated cases, got {len(cases)}"
    for c in cases:
        assert c.case_id
        assert c.program_source.strip()
        assert c.origin == "curated"
        assert len(c.inputs) >= 1


def test_curated_cases_cover_section_e7():
    cases = load_curated_cases()
    case_ids = {c.case_id for c in cases}

    # Verify coverage of ARCH §E.7 boundary categories:
    # 1. Negative division and remainder
    assert any("div_neg" in cid for cid in case_ids)
    assert any("mod_neg" in cid for cid in case_ids)
    # 2. Zero numerator
    assert any("zero_num" in cid for cid in case_ids)
    # 3. Division/mod by 1 and -1
    assert any("by_one" in cid for cid in case_ids)
    assert any("by_neg_one" in cid for cid in case_ids)
    # 4. INT_MIN and INT_MAX literals
    assert any("int_min_literal" in cid for cid in case_ids)
    assert any("int_max_literal" in cid for cid in case_ids)
    # 5. INT_MAX + 1 and INT_MIN - 1
    assert any("int_max_plus_one" in cid for cid in case_ids)
    assert any("int_min_minus_one" in cid for cid in case_ids)
    # 6. INT_MIN / -1 and INT_MIN % -1
    assert any("int_min_div_neg_one" in cid for cid in case_ids)
    assert any("int_min_mod_neg_one" in cid for cid in case_ids)
    # 7. Products near ±2^31 and ±2^63
    assert any("prod_near_i32" in cid for cid in case_ids)
    assert any("prod_near_i64" in cid for cid in case_ids)
    # 8. Narrowing long long -> int
    assert any("narrowing" in cid for cid in case_ids)


def test_load_example_cases():
    examples = load_example_cases()
    assert len(examples) > 10, f"Expected example cases, found {len(examples)}"
    for ex in examples:
        assert ex.case_id.startswith("example_")
        assert ex.origin == "example"
        assert ex.expected_stdout is not None
        assert ex.program_source.strip()


def test_corpus_missing_directory():
    cases = load_curated_cases(cases_dir="non_existent_directory_for_test")
    assert cases == []


def test_curated_cases_program_structure():
    cases = load_curated_cases()
    for c in cases:
        assert "#include <iostream>" in c.program_source
        assert "main(" in c.program_source

