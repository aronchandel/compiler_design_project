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

def test_bottom_invariants():
    assert BOTTOM.is_bottom
    assert not BOTTOM.contains(0)
    assert not BOTTOM.contains_interval(Interval(0, 0))
    assert Interval(0, 0).contains_interval(BOTTOM)

    assert BOTTOM.join(Interval(1, 5)) == Interval(1, 5)
    assert Interval(1, 5).join(BOTTOM) == Interval(1, 5)
    assert BOTTOM.intersect(Interval(1, 5)) == BOTTOM

    assert add(BOTTOM, Interval(1, 2)) == BOTTOM
    assert sub(Interval(1, 2), BOTTOM) == BOTTOM
    assert mul(BOTTOM, Interval(1, 2)) == BOTTOM
    assert div(Interval(1, 2), BOTTOM) == BOTTOM
    assert mod(BOTTOM, Interval(1, 2)) == BOTTOM
    assert neg(BOTTOM) == BOTTOM
    assert cast(BOTTOM, -10, 10) == BOTTOM

def test_intersect_disjoint():
    a = Interval(1, 5)
    b = Interval(6, 10)
    assert a.intersect(b) == BOTTOM
    assert a.intersect(b).is_bottom

def test_unbounded_intervals():
    left_unbounded = Interval(None, 5)
    right_unbounded = Interval(0, None)
    joined = left_unbounded.join(right_unbounded)
    assert joined.lo is None and joined.hi is None
    assert joined.contains(-1000000)
    assert joined.contains(1000000)

    met = left_unbounded.intersect(right_unbounded)
    assert met == Interval(0, 5)

def test_widening_to_type_bounds():
    prev = Interval(0, 5)
    new_growing_hi = Interval(0, 6)
    w = prev.widen_to_type_bounds(new_growing_hi, -100, 100)
    assert w == Interval(0, 100)

    prev2 = Interval(0, 5)
    new_growing_lo = Interval(-1, 5)
    w2 = prev2.widen_to_type_bounds(new_growing_lo, -100, 100)
    assert w2 == Interval(-100, 5)

    new_smaller = Interval(1, 4)
    w3 = prev.widen_to_type_bounds(new_smaller, -100, 100)
    assert w3 == Interval(0, 5)

def test_div_by_zero_only():
    res = div(Interval(1, 10), Interval(0, 0))
    assert res.lo is None and res.hi is None

def test_mod_by_zero_only():
    res = mod(Interval(1, 10), Interval(0, 0))
    assert res.lo is None and res.hi is None

def test_cast_exact_and_lossy():
    a = Interval(0, 100)

    assert cast(a, -128, 127) == a

    b = Interval(0, 200)

    assert cast(b, -128, 127) == Interval(-128, 127)
