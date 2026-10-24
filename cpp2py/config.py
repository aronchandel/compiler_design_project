"""Compiler configuration for cpp2py (Phase 5)."""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class TargetModel:
    """Target machine model."""
    int_bits: int = 32
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
