"""Unit tests for Interval transfer function properties and edge cases."""

import pytest
from cpp2py.analysis.intervals import (
    Interval,
    BOTTOM,
    add,
    sub,
    mul,
    neg,
    div,
    mod,
    cast,
)


def test_interval_contains():
    iv = Interval(-5, 10)
    assert iv.contains(-5)
    assert iv.contains(0)
    assert iv.contains(10)
    assert not iv.contains(-6)
    assert not iv.contains(11)


def test_interval_unbounded():
    iv = Interval(None, None)
    assert iv.contains(-999999999)
    assert iv.contains(999999999)

    iv_lo = Interval(0, None)
    assert iv_lo.contains(0)
    assert iv_lo.contains(100)
    assert not iv_lo.contains(-1)

    iv_hi = Interval(None, 0)
    assert iv_hi.contains(0)
    assert iv_hi.contains(-100)
    assert not iv_hi.contains(1)


def test_interval_point_and_bottom():
    pt = Interval.point(5)
    assert pt.lo == 5 and pt.hi == 5
    assert not pt.is_bottom
    assert BOTTOM.is_bottom
    assert not BOTTOM.contains(0)


def test_interval_bottom_operations():
    iv = Interval(1, 5)
    assert add(BOTTOM, iv) == BOTTOM
    assert add(iv, BOTTOM) == BOTTOM
    assert sub(BOTTOM, iv) == BOTTOM
    assert sub(iv, BOTTOM) == BOTTOM
    assert mul(BOTTOM, iv) == BOTTOM
    assert mul(iv, BOTTOM) == BOTTOM
    assert div(BOTTOM, iv) == BOTTOM
    assert div(iv, BOTTOM) == BOTTOM
    assert mod(BOTTOM, iv) == BOTTOM
    assert mod(iv, BOTTOM) == BOTTOM
    assert neg(BOTTOM) == BOTTOM
    assert BOTTOM.join(iv) == iv
    assert iv.join(BOTTOM) == iv
    assert BOTTOM.intersect(iv) == BOTTOM
    assert iv.intersect(BOTTOM) == BOTTOM


def test_add_unbounded():
    assert add(Interval(1, None), Interval(2, 3)) == Interval(3, None)
    assert add(Interval(None, 5), Interval(1, 2)) == Interval(None, 7)
    assert add(Interval(None, None), Interval(1, 2)) == Interval(None, None)


def test_sub_unbounded():
    assert sub(Interval(1, None), Interval(2, 3)) == Interval(-2, None)
    assert sub(Interval(None, 5), Interval(1, 2)) == Interval(None, 4)
    assert sub(Interval(1, 2), Interval(None, 5)) == Interval(-4, None)


def test_mul_negative_intervals():
    # Both strictly negative
    assert mul(Interval(-4, -2), Interval(-5, -3)) == Interval(6, 20)
    # One strictly negative, one strictly positive
    assert mul(Interval(-4, -2), Interval(3, 5)) == Interval(-20, -6)
    # Crossing zero
    assert mul(Interval(-2, 3), Interval(-4, 5)) == Interval(-12, 15)
    # Zero in one
    assert mul(Interval(0, 3), Interval(-2, 4)) == Interval(-6, 12)


def test_mul_unbounded():
    assert mul(Interval(1, None), Interval(2, 3)) == Interval(None, None)
    assert mul(Interval(-3, -1), Interval(1, None)) == Interval(None, None)


def test_div_exact_and_negative():
    assert div(Interval(8, 16), Interval(2, 4)) == Interval(2, 8)
    assert div(Interval(-16, -8), Interval(2, 4)) == Interval(-8, -2)
    assert div(Interval(-16, -8), Interval(-4, -2)) == Interval(2, 8)
    assert div(Interval(8, 16), Interval(-4, -2)) == Interval(-8, -2)


def test_div_crossing_zero():
    # Numerator crosses zero
    assert div(Interval(-10, 10), Interval(2, 5)) == Interval(-5, 5)
    # Divisor contains only 0 (UB in C++)
    assert div(Interval(5, 10), Interval(0, 0)) == Interval(None, None)
    # Divisor crosses zero [-2, 3] -> split into [-2, -1] and [1, 3]
    res = div(Interval(6, 12), Interval(-2, 3))
    assert res == Interval(-12, 12)


def test_div_unbounded():
    assert div(Interval(10, None), Interval(2, 2)) == Interval(None, None)
    assert div(Interval(None, -10), Interval(2, 2)) == Interval(None, None)


def test_mod_cases():
    # Positive
    assert mod(Interval(0, 15), Interval(4, 4)) == Interval(0, 3)
    # Exact smaller range
    assert mod(Interval(1, 3), Interval(5, 5)) == Interval(0, 3)
    # Divisor is 0
    assert mod(Interval(1, 5), Interval(0, 0)) == Interval(None, None)
    # Negative dividend: mod takes sign of dividend in C++
    res_neg = mod(Interval(-7, 7), Interval(4, 4))
    assert res_neg.lo == -3
    assert res_neg.hi == 3


def test_neg_cases():
    assert neg(Interval(2, 5)) == Interval(-5, -2)
    assert neg(Interval(-5, -2)) == Interval(2, 5)
    assert neg(Interval(-3, 4)) == Interval(-4, 3)
    assert neg(Interval(1, None)) == Interval(None, -1)
    assert neg(Interval(None, 2)) == Interval(-2, None)


def test_join_properties():
    a = Interval(1, 4)
    b = Interval(3, 8)
    assert a.join(b) == b.join(a)
    assert a.join(b) == Interval(1, 8)
    assert a.join(a) == a
    assert Interval(1, 2).join(Interval(5, 6)) == Interval(1, 6)


def test_intersect_properties():
    a = Interval(1, 5)
    b = Interval(3, 8)
    assert a.intersect(b) == b.intersect(a)
    assert a.intersect(b) == Interval(3, 5)
    assert a.intersect(a) == a
    assert Interval(1, 2).intersect(Interval(5, 6)) == BOTTOM


def test_widen_to_type_bounds():
    # Bounds didn't grow
    assert Interval(0, 10).widen_to_type_bounds(Interval(2, 8), -100, 100) == Interval(0, 10)
    # Lower bound grew downward
    assert Interval(0, 10).widen_to_type_bounds(Interval(-1, 8), -100, 100) == Interval(-100, 10)
    # Upper bound grew upward
    assert Interval(0, 10).widen_to_type_bounds(Interval(2, 15), -100, 100) == Interval(0, 100)


def test_cast_transfer():
    # Narrowing within bounds
    assert cast(Interval(0, 100), -128, 127) == Interval(0, 100)
    # Exceeding bounds wraps to full target range
    assert cast(Interval(0, 200), -128, 127) == Interval(-128, 127)
    # Unbounded wraps to full target range
    assert cast(Interval(None, None), -128, 127) == Interval(-128, 127)
