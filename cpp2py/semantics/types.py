"""Type representation for Phase 1 (int only)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntType:
    """The single type in Phase 1."""
    bits: int = 32

    def __str__(self) -> str:
        return "int"
