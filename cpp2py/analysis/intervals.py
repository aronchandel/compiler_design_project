"""Interval domain and transfer functions on mathematical integers.

Conforms to ARCH §E.4:
- Interval(lo, hi) where None represents unbounded on that side.
- BOTTOM represents unreachable state.
- Transfer functions: add, sub, mul, neg, div, mod, cast.
- Join, meet (intersect), and widening to type bounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class Interval:
    """Interval [lo, hi] over mathematical integers, or BOTTOM."""
    lo: int | None
    hi: int | None
    is_bottom: bool = False

    def __post_init__(self) -> None:
        if not self.is_bottom and self.lo is not None and self.hi is not None:
            if self.lo > self.hi:
                # Invariant: empty interval is normalized to BOTTOM
                object.__setattr__(self, "is_bottom", True)
                object.__setattr__(self, "lo", None)
                object.__setattr__(self, "hi", None)

    @classmethod
    def bottom(cls) -> Interval:
        return _BOTTOM

    @classmethod
    def point(cls, value: int) -> Interval:
        return cls(value, value)

    @classmethod
    def range(cls, lo: int | None, hi: int | None) -> Interval:
        if lo is not None and hi is not None and lo > hi:
            return _BOTTOM
        return cls(lo, hi)

    def contains(self, val: int) -> bool:
        if self.is_bottom:
            return False
        if self.lo is not None and val < self.lo:
            return False
        if self.hi is not None and val > self.hi:
            return False
        return True

    def contains_interval(self, other: Interval) -> bool:
        if other.is_bottom:
            return True
        if self.is_bottom:
            return False
        if self.lo is not None:
            if other.lo is None or other.lo < self.lo:
                return False
        if self.hi is not None:
            if other.hi is None or other.hi > self.hi:
                return False
        return True

    def join(self, other: Interval) -> Interval:
        """Interval hull (join / union approximation)."""
        if self.is_bottom:
            return other
        if other.is_bottom:
            return self
        new_lo = None if (self.lo is None or other.lo is None) else min(self.lo, other.lo)
        new_hi = None if (self.hi is None or other.hi is None) else max(self.hi, other.hi)
        return Interval(new_lo, new_hi)

    def intersect(self, other: Interval) -> Interval:
        """Interval intersection (meet)."""
        if self.is_bottom or other.is_bottom:
            return _BOTTOM
        new_lo = other.lo if self.lo is None else (self.lo if other.lo is None else max(self.lo, other.lo))
        new_hi = other.hi if self.hi is None else (self.hi if other.hi is None else min(self.hi, other.hi))
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return _BOTTOM
        return Interval(new_lo, new_hi)

    def widen_to_type_bounds(self, other: Interval, type_min: int, type_max: int) -> Interval:
        """Widening at loop heads: bounds that grow jump straight to type bounds."""
        if self.is_bottom:
            return other
        if other.is_bottom:
            return self

        # If a bound grew, jump to type bound
        if other.lo is None or self.lo is None:
            new_lo = None
        elif other.lo < self.lo:
            new_lo = type_min
        else:
            new_lo = self.lo

        if other.hi is None or self.hi is None:
            new_hi = None
        elif other.hi > self.hi:
            new_hi = type_max
        else:
            new_hi = self.hi

        return Interval(new_lo, new_hi)

    def to_dict(self) -> dict[str, Any]:
        if self.is_bottom:
            return {"bottom": True}
        return {"lo": self.lo, "hi": self.hi}

    def __str__(self) -> str:
        if self.is_bottom:
            return "BOTTOM"
        lo_str = "-inf" if self.lo is None else str(self.lo)
        hi_str = "+inf" if self.hi is None else str(self.hi)
        return f"[{lo_str}, {hi_str}]"


_BOTTOM = Interval(None, None, is_bottom=True)
BOTTOM = _BOTTOM


def add(a: Interval, b: Interval) -> Interval:
    if a.is_bottom or b.is_bottom:
        return _BOTTOM
    lo = None if (a.lo is None or b.lo is None) else a.lo + b.lo
    hi = None if (a.hi is None or b.hi is None) else a.hi + b.hi
    return Interval(lo, hi)


def sub(a: Interval, b: Interval) -> Interval:
    if a.is_bottom or b.is_bottom:
        return _BOTTOM
    lo = None if (a.lo is None or b.hi is None) else a.lo - b.hi
    hi = None if (a.hi is None or b.lo is None) else a.hi - b.lo
    return Interval(lo, hi)


def mul(a: Interval, b: Interval) -> Interval:
    if a.is_bottom or b.is_bottom:
        return _BOTTOM
    if a.lo == 0 and a.hi == 0:
        return Interval(0, 0)
    if b.lo == 0 and b.hi == 0:
        return Interval(0, 0)
    if a.lo is not None and a.hi is not None and b.lo is not None and b.hi is not None:
        corners = [a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi]
        return Interval(min(corners), max(corners))
    return Interval(None, None)


def neg(a: Interval) -> Interval:
    if a.is_bottom:
        return _BOTTOM
    lo = None if a.hi is None else -a.hi
    hi = None if a.lo is None else -a.lo
    return Interval(lo, hi)


def div(a: Interval, b: Interval) -> Interval:
    """C++ integer division truncating toward zero.
    
    Split divisor at 0 into [b.lo, -1] and [1, b.hi] (dropping 0 as UB).
    Min/max of truncating quotients of the corners.
    Empty split yields unconstrained Interval(None, None).
    """
    if a.is_bottom or b.is_bottom:
        return _BOTTOM

    parts: list[tuple[int | None, int | None]] = []

    # Negative divisor region
    if b.lo is None:
        hi_bound = -1 if (b.hi is None or b.hi >= 0) else b.hi
        parts.append((None, hi_bound))
    elif b.lo <= -1:
        hi_bound = -1 if (b.hi is None or b.hi >= 0) else b.hi
        parts.append((b.lo, hi_bound))

    # Positive divisor region
    if b.hi is None:
        lo_bound = 1 if (b.lo is None or b.lo <= 0) else b.lo
        parts.append((lo_bound, None))
    elif b.hi >= 1:
        lo_bound = 1 if (b.lo is None or b.lo <= 0) else b.lo
        parts.append((lo_bound, b.hi))

    if not parts:
        # b can only be 0: UB / unconstrained
        return Interval(None, None)

    if a.lo is None or a.hi is None:
        return Interval(None, None)

    def _trunc_div(x: int, y: int) -> int:
        return -(abs(x) // abs(y)) if (x < 0) ^ (y < 0) else (abs(x) // abs(y))

    quotients: list[int] = []
    for b_lo, b_hi in parts:
        if b_lo is None or b_hi is None:
            return Interval(None, None)
        for x in (a.lo, a.hi):
            for y in (b_lo, b_hi):
                quotients.append(_trunc_div(x, y))

    return Interval(min(quotients), max(quotients))


def mod(a: Interval, b: Interval) -> Interval:
    """C++ integer remainder (result sign follows dividend a).
    
    ARCH §E.4:
    if a.lo >= 0: [0, min(a.hi, max|b| - 1)]
    if a.hi <= 0: [-min(|a.lo|, max|b| - 1), 0]
    otherwise: [-min(|a.lo|, max|b| - 1), min(a.hi, max|b| - 1)]
    """
    if a.is_bottom or b.is_bottom:
        return _BOTTOM

    # Check non-zero divisor values
    if b.lo == 0 and b.hi == 0:
        return Interval(None, None)

    if b.lo is None or b.hi is None:
        return Interval(None, None)

    non_zeros = [abs(x) for x in (b.lo, b.hi) if x != 0]
    if not non_zeros:
        return Interval(None, None)
    max_abs_b = max(abs(b.lo), abs(b.hi))
    bound = max_abs_b - 1

    if a.lo is not None and a.lo >= 0:
        hi = min(a.hi, bound) if a.hi is not None else bound
        return Interval(0, hi)
    elif a.hi is not None and a.hi <= 0:
        abs_lo = abs(a.lo) if a.lo is not None else bound
        lo = -min(abs_lo, bound)
        return Interval(lo, 0)
    else:
        abs_lo = abs(a.lo) if a.lo is not None else bound
        lo = -min(abs_lo, bound)
        hi = min(a.hi, bound) if a.hi is not None else bound
        return Interval(lo, hi)


def cast(a: Interval, target_min: int, target_max: int) -> Interval:
    """Integer cast: exact if range fits target bounds, otherwise target bounds."""
    if a.is_bottom:
        return _BOTTOM
    if a.lo is not None and a.hi is not None and a.lo >= target_min and a.hi <= target_max:
        return a
    return Interval(target_min, target_max)
