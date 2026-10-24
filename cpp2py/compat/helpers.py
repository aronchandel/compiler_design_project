"""Real, importable compatibility helpers per ARCH §E.6.

These helpers implement C++ integer semantics in Python:
- _cpp_div: truncating division
- _cpp_mod: remainder taking sign of dividend
- _wrap_i32 / _wrap_i64: modular two's-complement reduction
- _check_i32 / _check_i64: range verification raising OverflowError
"""

from __future__ import annotations


def _cpp_div(a: int, b: int) -> int:
    """C++ integer division truncating toward zero."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return -(abs(a) // abs(b)) if (a < 0) ^ (b < 0) else (abs(a) // abs(b))


def _cpp_mod(a: int, b: int) -> int:
    """C++ integer remainder: a - b * _cpp_div(a, b)."""
    if b == 0:
        raise ZeroDivisionError("integer modulo by zero")
    return a - b * _cpp_div(a, b)


def _wrap_i32(x: int) -> int:
    """Reduce x modulo 2^32 into [-2^31, 2^31 - 1]."""
    return ((x + 0x80000000) % 0x100000000) - 0x80000000


def _wrap_i64(x: int) -> int:
    """Reduce x modulo 2^64 into [-2^63, 2^63 - 1]."""
    return ((x + 0x8000000000000000) % 0x10000000000000000) - 0x8000000000000000


def _check_i32(x: int) -> int:
    """Return x or raise OverflowError if x is outside 32-bit signed range."""
    if not (-2147483648 <= x <= 2147483647):
        raise OverflowError("32-bit integer overflow")
    return x


def _check_i64(x: int) -> int:
    """Return x or raise OverflowError if x is outside 64-bit signed range."""
    if not (-9223372036854775808 <= x <= 9223372036854775807):
        raise OverflowError("64-bit integer overflow")
    return x


_HELPER_SOURCES: dict[str, str] = {
    "_cpp_div": '''def _cpp_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return -(abs(a) // abs(b)) if (a < 0) ^ (b < 0) else (abs(a) // abs(b))''',

    "_cpp_mod": '''def _cpp_mod(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("integer modulo by zero")
    return a - b * _cpp_div(a, b)''',

    "_wrap_i32": '''def _wrap_i32(x: int) -> int:
    return ((x + 0x80000000) % 0x100000000) - 0x80000000''',

    "_wrap_i64": '''def _wrap_i64(x: int) -> int:
    return ((x + 0x8000000000000000) % 0x10000000000000000) - 0x8000000000000000''',

    "_check_i32": '''def _check_i32(x: int) -> int:
    if not (-2147483648 <= x <= 2147483647):
        raise OverflowError("32-bit integer overflow")
    return x''',

    "_check_i64": '''def _check_i64(x: int) -> int:
    if not (-9223372036854775808 <= x <= 9223372036854775807):
        raise OverflowError("64-bit integer overflow")
    return x''',
}


def helper_source(kind: str) -> str:
    """Return Python source code of helper function."""
    if kind not in _HELPER_SOURCES:
        raise KeyError(f"Unknown helper: {kind}")
    return _HELPER_SOURCES[kind]
