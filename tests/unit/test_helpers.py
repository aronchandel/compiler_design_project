from fractions import Fraction
import math
import pytest

from cpp2py.compat.helpers import (
    _cpp_div,
    _cpp_mod,
    _wrap_i32,
    _wrap_i64,
    _check_i32,
    _check_i64,
    helper_source,
)

def ref_div(a: int, b: int) -> int:
    return math.trunc(Fraction(a, b))

def ref_mod(a: int, b: int) -> int:
    q = math.trunc(Fraction(a, b))
    return a - b * q

def test_div_mod_exhaustive_range_50():
    for a in range(-50, 51):
        for b in range(-50, 51):
            if b == 0:
                with pytest.raises(ZeroDivisionError):
                    _cpp_div(a, b)
                with pytest.raises(ZeroDivisionError):
                    _cpp_mod(a, b)
            else:
                expected_q = ref_div(a, b)
                expected_r = ref_mod(a, b)

                act_q = _cpp_div(a, b)
                act_r = _cpp_mod(a, b)

                assert act_q == expected_q, f"_cpp_div({a}, {b}) != {expected_q}"
                assert act_r == expected_r, f"_cpp_mod({a}, {b}) != {expected_r}"

                assert a == b * act_q + act_r

def test_wrap_i32_boundaries():
    int_min = -2147483648
    int_max = 2147483647

    assert _wrap_i32(0) == 0
    assert _wrap_i32(int_max) == int_max
    assert _wrap_i32(int_min) == int_min
    assert _wrap_i32(int_max + 1) == int_min
    assert _wrap_i32(int_min - 1) == int_max
    assert _wrap_i32(int_max + 2) == int_min + 1

def test_wrap_i64_boundaries():
    ll_min = -9223372036854775808
    ll_max = 9223372036854775807

    assert _wrap_i64(0) == 0
    assert _wrap_i64(ll_max) == ll_max
    assert _wrap_i64(ll_min) == ll_min
    assert _wrap_i64(ll_max + 1) == ll_min
    assert _wrap_i64(ll_min - 1) == ll_max
    assert _wrap_i64(ll_max + 2) == ll_min + 1

def test_check_i32_boundaries():
    int_min = -2147483648
    int_max = 2147483647

    assert _check_i32(0) == 0
    assert _check_i32(int_max) == int_max
    assert _check_i32(int_min) == int_min

    with pytest.raises(OverflowError):
        _check_i32(int_max + 1)
    with pytest.raises(OverflowError):
        _check_i32(int_min - 1)

def test_check_i64_boundaries():
    ll_min = -9223372036854775808
    ll_max = 9223372036854775807

    assert _check_i64(0) == 0
    assert _check_i64(ll_max) == ll_max
    assert _check_i64(ll_min) == ll_min

    with pytest.raises(OverflowError):
        _check_i64(ll_max + 1)
    with pytest.raises(OverflowError):
        _check_i64(ll_min - 1)

def test_helper_source_compilable():
    for name in ("_cpp_div", "_cpp_mod", "_wrap_i32", "_wrap_i64", "_check_i32", "_check_i64"):
        src = helper_source(name)
        compiled = compile(src, f"<{name}>", "exec")
        assert compiled is not None
