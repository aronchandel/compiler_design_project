"""Symbol table for the cpp2py semantic analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from cpp2py.source import SourceSpan
from cpp2py.semantics.types import IntType


class SymbolKind(Enum):
    VARIABLE = auto()
    BUILTIN_IO = auto()  # cin, cout, endl


@dataclass(frozen=True, slots=True)
class Symbol:
    """A declared symbol."""
    symbol_id: int
    name: str
    type: IntType | None
    kind: SymbolKind
    decl_span: SourceSpan | None


@dataclass
class SemanticInfo:
    """Side table for semantic analysis results, keyed by AST node_id."""
    symbols_by_node: dict[int, Symbol] = field(default_factory=dict)
    type_by_node: dict[int, IntType] = field(default_factory=dict)
