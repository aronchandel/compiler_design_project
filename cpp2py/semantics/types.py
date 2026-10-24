"""Type representation for Phase 1 (int only)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntType:
    """Integer type."""
    bits: int = 32

    def __str__(self) -> str:
        return "int"


@dataclass(frozen=True, slots=True)
class VoidType:
    """Void type for function return."""
    def __str__(self) -> str:
        return "void"


@dataclass(frozen=True, slots=True)
class BoolType:
    """Boolean type for condition expressions."""
    def __str__(self) -> str:
        return "bool"
