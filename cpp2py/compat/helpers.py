"""Real, importable compatibility helpers per ARCH §E.6.

These helpers implement C++ integer semantics in Python:
- _cpp_div: truncating division
- _cpp_mod: remainder taking sign of dividend
- _wrap_i32 / _wrap_i64: modular two's-complement reduction
- _check_i32 / _check_i64: range verification raising OverflowError
- _Ptr: C++ pointer indirection and aliasing helper

Also provides evaluation-only instrumented variants (Phase 8) to measure
unnecessary helper executions dynamically.
"""

from __future__ import annotations

import os
from typing import Any


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


class _Ptr:
    """Compatibility pointer helper for C++ pointers in Python."""
    __slots__ = ('_target', '_offset')

    def __init__(self, target, offset: int = 0):
        if isinstance(target, _Ptr):
            self._target = target._target
            self._offset = target._offset + offset
        else:
            self._target = target
            self._offset = offset

    def __getitem__(self, idx: int):
        if self._target is None:
            raise RuntimeError("Segmentation fault: dereferencing nullptr")
        return self._target[self._offset + idx]

    def __setitem__(self, idx: int, value):
        if self._target is None:
            raise RuntimeError("Segmentation fault: dereferencing nullptr")
        self._target[self._offset + idx] = value

    def __add__(self, delta: int):
        return _Ptr(self._target, self._offset + delta)

    def __radd__(self, delta: int):
        return _Ptr(self._target, self._offset + delta)

    def __sub__(self, other):
        if isinstance(other, _Ptr):
            if self._target is not other._target:
                raise RuntimeError("Pointer subtraction across different objects")
            return self._offset - other._offset
        return _Ptr(self._target, self._offset - other)

    def __eq__(self, other):
        if other is None:
            return self._target is None
        if not isinstance(other, _Ptr):
            return False
        return self._target is other._target and self._offset == other._offset

    def __ne__(self, other):
        return not self.__eq__(other)

    def __bool__(self):
        return self._target is not None


# --- Phase 8 Evaluation-only Instrumentation ---

_INSTRUMENTATION_COUNTS: dict[str, int] = {
    "total": 0,
    "differs": 0,
    "equals": 0,
    "div_total": 0,
    "div_differs": 0,
    "div_equals": 0,
    "mod_total": 0,
    "mod_differs": 0,
    "mod_equals": 0,
}


def reset_instrumentation() -> None:
    """Reset the evaluation instrumentation counters."""
    global _INSTRUMENTATION_COUNTS
    _INSTRUMENTATION_COUNTS = {
        "total": 0,
        "differs": 0,
        "equals": 0,
        "div_total": 0,
        "div_differs": 0,
        "div_equals": 0,
        "mod_total": 0,
        "mod_differs": 0,
        "mod_equals": 0,
    }


def get_instrumentation_counts() -> dict[str, int]:
    """Return a copy of the evaluation instrumentation counters."""
    return dict(_INSTRUMENTATION_COUNTS)


def _cpp_div_instrumented(a: int, b: int) -> int:
    """Instrumented version of _cpp_div tracking unnecessary invocations."""
    global _INSTRUMENTATION_COUNTS
    _INSTRUMENTATION_COUNTS["total"] += 1
    _INSTRUMENTATION_COUNTS["div_total"] += 1

    if b == 0:
        raise ZeroDivisionError("division by zero")

    cpp_res = -(abs(a) // abs(b)) if (a < 0) ^ (b < 0) else (abs(a) // abs(b))
    try:
        py_res = a // b
        if cpp_res != py_res:
            _INSTRUMENTATION_COUNTS["differs"] += 1
            _INSTRUMENTATION_COUNTS["div_differs"] += 1
        else:
            _INSTRUMENTATION_COUNTS["equals"] += 1
            _INSTRUMENTATION_COUNTS["div_equals"] += 1
    except ZeroDivisionError:
        pass

    return cpp_res


def _cpp_mod_instrumented(a: int, b: int) -> int:
    """Instrumented version of _cpp_mod tracking unnecessary invocations."""
    global _INSTRUMENTATION_COUNTS
    _INSTRUMENTATION_COUNTS["total"] += 1
    _INSTRUMENTATION_COUNTS["mod_total"] += 1

    if b == 0:
        raise ZeroDivisionError("integer modulo by zero")

    cpp_res = a - b * _cpp_div(a, b)
    try:
        py_res = a % b
        if cpp_res != py_res:
            _INSTRUMENTATION_COUNTS["differs"] += 1
            _INSTRUMENTATION_COUNTS["mod_differs"] += 1
        else:
            _INSTRUMENTATION_COUNTS["equals"] += 1
            _INSTRUMENTATION_COUNTS["mod_equals"] += 1
    except ZeroDivisionError:
        pass

    return cpp_res


# Standalone Python source strings embedded directly into generated code

_HELPER_SOURCES: dict[str, str] = {
    "_cpp_div": '''def _cpp_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("integer division by zero")
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

    "_Ptr": '''class _Ptr:
    __slots__ = ('_target', '_offset')
    def __init__(self, target, offset: int = 0):
        if isinstance(target, _Ptr):
            self._target = target._target
            self._offset = target._offset + offset
        else:
            self._target = target
            self._offset = offset
    def __getitem__(self, idx: int):
        if self._target is None:
            raise RuntimeError("Segmentation fault: dereferencing nullptr")
        return self._target[self._offset + idx]
    def __setitem__(self, idx: int, value):
        if self._target is None:
            raise RuntimeError("Segmentation fault: dereferencing nullptr")
        self._target[self._offset + idx] = value
    def __add__(self, delta: int):
        return _Ptr(self._target, self._offset + delta)
    def __radd__(self, delta: int):
        return _Ptr(self._target, self._offset + delta)
    def __sub__(self, other):
        if isinstance(other, _Ptr):
            if self._target is not other._target:
                raise RuntimeError("Pointer subtraction across different objects")
            return self._offset - other._offset
        return _Ptr(self._target, self._offset - other)
    def __eq__(self, other):
        if other is None:
            return self._target is None
        if not isinstance(other, _Ptr):
            return False
        return self._target is other._target and self._offset == other._offset
    def __ne__(self, other):
        return not self.__eq__(other)
    def __bool__(self):
        return self._target is not None''',
}


_INSTRUMENTED_HELPER_SOURCES: dict[str, str] = {
    "_cpp_div": '''_CPP2PY_INSTR_DIV_TOTAL = 0
_CPP2PY_INSTR_DIV_DIFFERS = 0

def _cpp_div(a: int, b: int) -> int:
    global _CPP2PY_INSTR_DIV_TOTAL, _CPP2PY_INSTR_DIV_DIFFERS
    _CPP2PY_INSTR_DIV_TOTAL += 1
    if b == 0:
        raise ZeroDivisionError("division by zero")
    res = -(abs(a) // abs(b)) if (a < 0) ^ (b < 0) else (abs(a) // abs(b))
    try:
        if res != (a // b):
            _CPP2PY_INSTR_DIV_DIFFERS += 1
    except ZeroDivisionError:
        pass
    return res''',

    "_cpp_mod": '''_CPP2PY_INSTR_MOD_TOTAL = 0
_CPP2PY_INSTR_MOD_DIFFERS = 0

def _cpp_mod(a: int, b: int) -> int:
    global _CPP2PY_INSTR_MOD_TOTAL, _CPP2PY_INSTR_MOD_DIFFERS
    _CPP2PY_INSTR_MOD_TOTAL += 1
    if b == 0:
        raise ZeroDivisionError("integer modulo by zero")
    res = a - b * _cpp_div(a, b)
    try:
        if res != (a % b):
            _CPP2PY_INSTR_MOD_DIFFERS += 1
    except ZeroDivisionError:
        pass
    return res''',
}

_INSTRUMENTATION_PRELUDE = '''import os
import atexit
import json

def _dump_cpp2py_instrumentation():
    path = os.environ.get("CPP2PY_INSTR_OUT")
    if path:
        div_tot = globals().get("_CPP2PY_INSTR_DIV_TOTAL", 0)
        div_dif = globals().get("_CPP2PY_INSTR_DIV_DIFFERS", 0)
        mod_tot = globals().get("_CPP2PY_INSTR_MOD_TOTAL", 0)
        mod_dif = globals().get("_CPP2PY_INSTR_MOD_DIFFERS", 0)
        data = {
            "total": div_tot + mod_tot,
            "differs": div_dif + mod_dif,
            "equals": (div_tot + mod_tot) - (div_dif + mod_dif),
            "div_total": div_tot,
            "div_differs": div_dif,
            "div_equals": div_tot - div_dif,
            "mod_total": mod_tot,
            "mod_differs": mod_dif,
            "mod_equals": mod_tot - mod_dif,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

atexit.register(_dump_cpp2py_instrumentation)
'''


def helper_source(kind: str, instrumented: bool = False) -> str:
    """Return Python source code of helper function."""
    if instrumented and kind in _INSTRUMENTED_HELPER_SOURCES:
        return _INSTRUMENTED_HELPER_SOURCES[kind]
    if kind not in _HELPER_SOURCES:
        raise KeyError(f"Unknown helper: {kind}")
    return _HELPER_SOURCES[kind]


def get_instrumentation_prelude() -> str:
    """Return the instrumentation atexit prelude for evaluation runs."""
    return _INSTRUMENTATION_PRELUDE
