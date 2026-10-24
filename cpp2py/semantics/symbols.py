"""Symbol table for the cpp2py semantic analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from cpp2py.source import SourceSpan
from cpp2py.semantics.types import IntType, VoidType, BoolType


class SymbolKind(Enum):
    VARIABLE = auto()
    PARAMETER = auto()
    FUNCTION = auto()
    BUILTIN_IO = auto()  # cin, cout, endl


@dataclass(frozen=True, slots=True)
class Symbol:
    """A declared symbol."""
    symbol_id: int
    name: str
    type: IntType | VoidType | BoolType | None
    kind: SymbolKind
    decl_span: SourceSpan | None


@dataclass(frozen=True, slots=True)
class FunctionSymbol:
    """A function signature."""
    name: str
    return_type: IntType | VoidType
    params: tuple[Symbol, ...]
    decl_span: SourceSpan


@dataclass
class SemanticInfo:
    """Side table for semantic analysis results, keyed by AST node_id."""
    symbols_by_node: dict[int, Symbol] = field(default_factory=dict)
    type_by_node: dict[int, IntType | VoidType | BoolType] = field(default_factory=dict)
    functions: dict[str, FunctionSymbol] = field(default_factory=dict)
