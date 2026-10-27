"""Compiler configuration for cpp2py (Phase 5)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OverflowPolicy(Enum):
    """Signed integer overflow policies per ARCH §E.3."""
    ASSUME_NO_OVERFLOW = "assume_no_overflow"
    WRAP = "wrap"
    TRAP = "trap"


class CompatMode(Enum):
    """Compatibility helper insertion modes per ARCH §E.5."""
    NAIVE = "naive"
    ALWAYS = "always"
    RANGE_GUIDED = "range_guided"


_DEFAULT_LONG_BITS = 32 if sys.platform == "win32" else 64


@dataclass(frozen=True, slots=True)
class TargetModel:
    """Target machine model."""
    char_bits: int = 8
    short_bits: int = 16
    int_bits: int = 32
    long_bits: int = _DEFAULT_LONG_BITS
    long_long_bits: int = 64
    overflow_policy: OverflowPolicy = OverflowPolicy.ASSUME_NO_OVERFLOW
    narrowing: str = "modular"

    @property
    def int_max(self) -> int:
        return (1 << (self.int_bits - 1)) - 1

    @property
    def int_min(self) -> int:
        return -(1 << (self.int_bits - 1))

    @property
    def long_long_max(self) -> int:
        return (1 << (self.long_long_bits - 1)) - 1

    @property
    def long_long_min(self) -> int:
        return -(1 << (self.long_long_bits - 1))

    @property
    def llong_max(self) -> int:
        return self.long_long_max

    @property
    def llong_min(self) -> int:
        return self.long_long_min

    @property
    def char_bit(self) -> int:
        return self.char_bits

    @property
    def schar_min(self) -> int:
        return -(1 << (self.char_bits - 1))

    @property
    def schar_max(self) -> int:
        return (1 << (self.char_bits - 1)) - 1

    @property
    def uchar_max(self) -> int:
        return (1 << self.char_bits) - 1

    @property
    def shrt_min(self) -> int:
        return -(1 << (self.short_bits - 1))

    @property
    def shrt_max(self) -> int:
        return (1 << (self.short_bits - 1)) - 1

    @property
    def ushrt_max(self) -> int:
        return (1 << self.short_bits) - 1

    @property
    def uint_max(self) -> int:
        return (1 << self.int_bits) - 1

    @property
    def long_min(self) -> int:
        return -(1 << (self.long_bits - 1))

    @property
    def long_max(self) -> int:
        return (1 << (self.long_bits - 1)) - 1

    @property
    def ulong_max(self) -> int:
        return (1 << self.long_bits) - 1

    @property
    def ullong_max(self) -> int:
        return (1 << self.long_long_bits) - 1

    def climits_macros(self) -> dict[str, int]:
        """Return mapping of supported <climits> macro names to their resolved integer values."""
        return {
            "CHAR_BIT": self.char_bit,
            "SCHAR_MIN": self.schar_min,
            "SCHAR_MAX": self.schar_max,
            "UCHAR_MAX": self.uchar_max,
            "SHRT_MIN": self.shrt_min,
            "SHRT_MAX": self.shrt_max,
            "USHRT_MAX": self.ushrt_max,
            "INT_MIN": self.int_min,
            "INT_MAX": self.int_max,
            "UINT_MAX": self.uint_max,
            "LONG_MIN": self.long_min,
            "LONG_MAX": self.long_max,
            "ULONG_MAX": self.ulong_max,
            "LLONG_MIN": self.llong_min,
            "LLONG_MAX": self.llong_max,
            "ULLONG_MAX": self.ullong_max,
        }


@dataclass(frozen=True, slots=True)
class CompilerConfig:
    """Top-level compiler configuration."""
    target: TargetModel = field(default_factory=TargetModel)
    compat_mode: CompatMode = CompatMode.RANGE_GUIDED
    assumed_ranges: dict[str, Any] = field(default_factory=dict)
    snapshot_dir: str | None = None
    fold_constants: bool = True
    idiomatic_loops: bool = False
    transform_log_path: str | None = None
    ranges_out: str | None = None
    compat_plan_out: str | None = None
    verify_ir_between_passes: bool = True
