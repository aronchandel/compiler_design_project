"""Compiler configuration for cpp2py (Phase 1: minimal)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TargetModel:
    """Target machine model."""
    int_bits: int = 32

    @property
    def int_max(self) -> int:
        return (1 << (self.int_bits - 1)) - 1

    @property
    def int_min(self) -> int:
        return -(1 << (self.int_bits - 1))


@dataclass(frozen=True, slots=True)
class CompilerConfig:
    """Top-level compiler configuration."""
    target: TargetModel = field(default_factory=TargetModel)
    snapshot_dir: str | None = None
