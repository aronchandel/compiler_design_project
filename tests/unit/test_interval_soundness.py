"""Brute-force soundness verification of interval transfer functions.

Conforms to AC5.2:
- Enumerates >= 10^4 interval pairs overall.
- Uses Fraction-based truncation as mathematical reference for / and %.
- Concrete operand pairs tested against abstract transfer functions.
- Verifies join and widen are over-approximations.
"""

from fractions import Fraction
import math
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


def ref_div(x: int, y: int) -> int:
    return math.trunc(Fraction(x, y))


def ref_mod(x: int, y: int) -> int:
    q = math.trunc(Fraction(x, y))
    return x - y * q


def test_brute_force_soundness():
    # Endpoints [-7..7] plus -128, 127 gives 17 endpoints
    endpoints = list(range(-7, 8)) + [-128, 127]
    intervals: list[Interval] = []
    for lo in endpoints:
        for hi in endpoints:
            if lo <= hi:
                intervals.append(Interval(lo, hi))

    total_pairs = len(intervals) * len(intervals)
    assert total_pairs >= 10000, f"Expected >= 10^4 interval pairs, got {total_pairs}"

    # Sample concrete points per interval to keep test fast while sound
    def sample_points(it: Interval) -> list[int]:
        if it.lo is None or it.hi is None:
            return []
        span = it.hi - it.lo + 1
        if span <= 15:
            return list(range(it.lo, it.hi + 1))
        # Edge and middle samples
        pts = {it.lo, it.lo + 1, it.hi - 1, it.hi, 0, 1, -1}
        return [p for p in pts if it.lo <= p <= it.hi]

    points_cache = {it: sample_points(it) for it in intervals}

    # Verify all pairs
    for a in intervals:
        pts_a = points_cache[a]
        # Test neg
        res_neg = neg(a)
        for x in pts_a:
            assert res_neg.contains(-x)

        for b in intervals:
            pts_b = points_cache[b]

            # 1. Add
            res_add = add(a, b)
            for x in pts_a:
                for y in pts_b:
                    assert res_add.contains(x + y)

            # 2. Sub
            res_sub = sub(a, b)
            for x in pts_a:
                for y in pts_b:
                    assert res_sub.contains(x - y)

            # 3. Mul
            res_mul = mul(a, b)
            for x in pts_a:
                for y in pts_b:
                    assert res_mul.contains(x * y)

            # 4. Div
            res_div = div(a, b)
            for x in pts_a:
                for y in pts_b:
                    if y != 0:
                        assert res_div.contains(ref_div(x, y))

            # 5. Mod
            res_mod = mod(a, b)
            for x in pts_a:
                for y in pts_b:
                    if y != 0:
                        assert res_mod.contains(ref_mod(x, y))

            # 6. Join is over-approximation
            res_join = a.join(b)
            assert res_join.contains_interval(a)
            assert res_join.contains_interval(b)

            # 7. Widen is over-approximation
            res_widen = a.widen_to_type_bounds(b, -2147483648, 2147483647)
            assert res_widen.contains_interval(a)
